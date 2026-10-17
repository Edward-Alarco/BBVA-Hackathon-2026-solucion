"""Worker aislado que ejecuta exclusivamente ``candidate_strategy.py``."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
import importlib.util
import multiprocessing
import os
from pathlib import Path
import sys
import time
import traceback
from typing import Any, Callable


class WorkerError(RuntimeError):
    status = "STRATEGY_ERROR"


class WorkerOOM(WorkerError):
    status = "OOM"


class WorkerTimeout(WorkerError):
    status = "TIMEOUT"


class _RemoteCarrierService:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def _call(self, method: str, args: tuple[Any, ...]) -> Any:
        self.connection.send(("SERVICE", method, args))
        kind, payload = self.connection.recv()
        if kind == "SERVICE_RESULT":
            return payload
        raise RuntimeError(str(payload))

    def snapshot(self):
        return self._call("snapshot", ())

    def dispatch_batch(self, carrier_id: str, shipment_ids):
        return self._call("dispatch_batch", (carrier_id, tuple(shipment_ids)))


def _worker_main(connection: Any, candidate_path: str, interfaces_dir: str) -> None:
    try:
        sys.path.insert(0, interfaces_dir)
        sys.path.insert(0, str(Path(candidate_path).parent))
        spec = importlib.util.spec_from_file_location("log8092_submission", candidate_path)
        if spec is None or spec.loader is None:
            raise ImportError("no se pudo cargar candidate_strategy.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        strategy_class = getattr(module, "CandidateStrategy")
        strategy = strategy_class(_RemoteCarrierService(connection))
        connection.send(("READY", None))
        while True:
            message = connection.recv()
            kind = message[0]
            if kind == "STOP":
                connection.send(("STOPPED", None))
                return
            if kind != "CALL":
                raise RuntimeError(f"mensaje desconocido: {kind}")
            _, method, args = message
            try:
                result = getattr(strategy, method)(*args)
                connection.send(("RESULT", result))
            except BaseException:
                connection.send(("ERROR", traceback.format_exc(limit=20)))
    except EOFError:
        return
    except BaseException:
        try:
            connection.send(("BOOT_ERROR", traceback.format_exc(limit=20)))
        except BaseException:
            pass


def _windows_process_metrics(pid: int) -> tuple[int, float]:
    if os.name != "nt":
        return 0, 0.0
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    PROCESS_VM_READ = 0x0010
    handle = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, False, pid
    )
    if not handle:
        return 0, 0.0
    try:
        class PMC(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ]
        counters = PMC()
        counters.cb = ctypes.sizeof(counters)
        rss = 0
        if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            rss = int(counters.PeakWorkingSetSize)
        creation = ctypes.c_ulonglong()
        exit_time = ctypes.c_ulonglong()
        kernel = ctypes.c_ulonglong()
        user = ctypes.c_ulonglong()
        cpu = 0.0
        if ctypes.windll.kernel32.GetProcessTimes(
            handle, ctypes.byref(creation), ctypes.byref(exit_time), ctypes.byref(kernel), ctypes.byref(user)
        ):
            cpu = (kernel.value + user.value) / 10_000_000
        return rss, cpu
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _unix_process_metrics(pid: int) -> tuple[int, float]:
    try:
        status = Path(f"/proc/{pid}/status").read_text()
        peak_line = next(line for line in status.splitlines() if line.startswith("VmHWM:"))
        rss = int(peak_line.split()[1]) * 1024
        fields = Path(f"/proc/{pid}/stat").read_text().split()
        ticks = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
        return rss, (int(fields[13]) + int(fields[14])) / ticks
    except (OSError, StopIteration, ValueError):
        return 0, 0.0


@dataclass(slots=True)
class WorkerClient:
    candidate_path: Path
    interfaces_path: Path
    timeout_seconds: float = 30.0
    peak_rss_bytes: int = 0
    cpu_seconds: float = 0.0
    _process: Any = field(init=False, default=None, repr=False)
    _connection: Any = field(init=False, default=None, repr=False)
    _service: Any = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        self.candidate_path = self.candidate_path.resolve()
        self.interfaces_path = self.interfaces_path.resolve()

    def _sample(self) -> None:
        if self._process is None or self._process.pid is None:
            return
        rss, cpu = (
            _windows_process_metrics(self._process.pid)
            if os.name == "nt" else _unix_process_metrics(self._process.pid)
        )
        self.peak_rss_bytes = max(self.peak_rss_bytes, rss)
        self.cpu_seconds = max(self.cpu_seconds, cpu)

    def start(self, service: Any) -> None:
        self._service = service
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe()
        self._connection = parent
        self._process = context.Process(
            target=_worker_main,
            args=(child, str(self.candidate_path), str(self.interfaces_path.parent)),
            name="log8092-candidate",
        )
        self._process.start()
        self._await("READY")

    def _handle_service(self, method: str, args: tuple[Any, ...]) -> None:
        assert self._connection is not None and self._service is not None
        try:
            if method == "snapshot":
                result = self._service.snapshot()
            elif method == "dispatch_batch":
                result = self._service.dispatch_batch(*args)
            else:
                raise RuntimeError(f"servicio no permitido: {method}")
            self._connection.send(("SERVICE_RESULT", result))
        except BaseException:
            self._connection.send(("SERVICE_ERROR", traceback.format_exc(limit=10)))

    def _await(self, expected: str) -> Any:
        assert self._connection is not None and self._process is not None
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            self._sample()
            if self._connection.poll(0.02):
                kind, *payload = self._connection.recv()
                value = payload[0] if payload else None
                if kind == "SERVICE":
                    method, args = payload
                    self._handle_service(method, args)
                    continue
                if kind == expected:
                    return value
                if kind in {"ERROR", "BOOT_ERROR"}:
                    raise WorkerError(str(value))
                raise WorkerError(f"respuesta inesperada del worker: {kind}")
            if not self._process.is_alive():
                code = self._process.exitcode
                if code in {-9, -11, 137}:
                    raise WorkerOOM(f"worker finalizo por limite de memoria ({code})")
                raise WorkerError(f"worker finalizo inesperadamente ({code})")
        self._process.terminate()
        raise WorkerTimeout(f"hook excedio {self.timeout_seconds:.1f} s")

    def call(self, method: str, *args: Any) -> Any:
        assert self._connection is not None
        self._connection.send(("CALL", method, args))
        return self._await("RESULT")

    def close(self) -> None:
        if self._process is None:
            return
        try:
            self._sample()
            if self._process.is_alive() and self._connection is not None:
                self._connection.send(("STOP",))
                try:
                    self._await("STOPPED")
                except WorkerError:
                    pass
        finally:
            if self._process.is_alive():
                self._process.terminate()
            self._process.join(timeout=2)
            self._sample()
