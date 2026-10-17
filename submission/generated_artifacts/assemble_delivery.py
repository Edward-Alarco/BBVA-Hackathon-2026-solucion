"""Assemble a reviewable delivery from measured results and unchanged kit files."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


HERE = Path(__file__).resolve().parent
WORK = HERE / "bbva-review"
BASE = HERE.parent
ORIGINAL = Path(r"C:\Users\edwar\Downloads\BBVA-Hackaton-2026-main")
SESSION = Path(r"C:\Users\edwar\.codex\sessions\2026\10\17\rollout-2026-10-17T11-52-48-01a14ac7-c344-7482-8962-e714d4c60898.jsonl")
DEST = BASE / "outputs" / "BBVA-solucion"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    final_reports = [json.loads((WORK / "output" / name).read_text(encoding="utf-8")) for name in ("final_5k.json", "final_150k.json")]
    candidate_hash = digest(WORK / "submission" / "candidate_strategy.py")
    assert digest(WORK / "candidate_strategy.py") == candidate_hash
    for report in final_reports:
        assert report["status"] == "COMPLETED"
        assert report["counts"]["unresolved"] == 0
        assert report["counts"]["voluntary_hold_breaches"] == 0
        assert report["counts"]["rejected_dispatches"] == 0
        assert report["sla"]["breach_rate"] <= .06
        assert report["integrity"]["candidate_sha256"] == candidate_hash
        assert report["integrity"]["protected_files_pristine"]
    checks = json.loads((WORK / "output" / "development_checks" / "summary.json").read_text())
    assert len(checks) == 4 and all(c["candidate_sha256"] == candidate_hash for c in checks)

    shutil.copytree(ORIGINAL, DEST, ignore=shutil.ignore_patterns(".git", "__pycache__", "output", "submission"))
    shutil.copy2(WORK / "candidate_strategy.py", DEST / "candidate_strategy.py")
    submission = DEST / "submission"
    generated = submission / "generated_artifacts"
    reports_dir = generated / "reports"
    prototypes = generated / "prototypes"
    for folder in (reports_dir, prototypes, submission / "ai_conversations"):
        folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(WORK / "submission" / "candidate_strategy.py", submission / "candidate_strategy.py")
    shutil.copy2(WORK / "tests" / "test_dispatch_contract.py", DEST / "tests" / "test_dispatch_contract.py")
    shutil.copy2(WORK / "tests" / "test_dispatch_contract.py", generated / "test_dispatch_contract.py")
    shutil.copy2(WORK / "validate_variants.py", generated / "validate_variants.py")
    shutil.copy2(HERE / "export_conversation.py", generated / "export_conversation.py")
    shutil.copy2(Path(__file__), generated / "assemble_delivery.py")
    for path in (WORK / "experiments").glob("*.py"):
        shutil.copy2(path, prototypes / path.name)
    for path in (WORK / "experiments").glob("*.json"):
        shutil.copy2(path, reports_dir / path.name)
    for path in (WORK / "output").glob("final_*.json"):
        shutil.copy2(path, reports_dir / path.name)
    shutil.copy2(BASE / "outputs" / "diagnostico-estrategia-inicial.json", reports_dir / "report_starter_5k.json")
    shutil.copytree(WORK / "output" / "development_checks", reports_dir / "development_checks")

    result = subprocess.run([sys.executable, "-S", "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=DEST, capture_output=True, text=True)
    (generated / "tests_result.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert "Ran 32 tests" in result.stderr

    protected = json.loads((DEST / "protected_files.sha256").read_text(encoding="utf-8"))["files"]
    assert all(digest(DEST / name) == expected for name, expected in protected.items())
    assert all(digest(ORIGINAL / name) == expected for name, expected in protected.items())

    old_small = json.loads((reports_dir / "report_starter_5k.json").read_text())
    old_large = json.loads((reports_dir / "report_starter_150k.json").read_text())
    rows = []
    for label, old, new in (("5.000", old_small, final_reports[0]), ("150.000", old_large, final_reports[1])):
        rows.append(f"| {label}, inicial | {old['counts']['unresolved']} | {old['counts']['voluntary_hold_breaches']} | {old['sla']['breach_rate']*100:.3f}% | {old['rcp']['weighted_score']} | {old['lead_time_minutes']['mean']} | {old['costs']['total_cents']} |")
        rows.append(f"| {label}, final | {new['counts']['unresolved']} | {new['counts']['voluntary_hold_breaches']} | {new['sla']['breach_rate']*100:.3f}% | {new['rcp']['weighted_score']} | {new['lead_time_minutes']['mean']} | {new['costs']['total_cents']} |")
    table = "| Caso y versión | Sin resolver | Retenciones | SLA incumplido | RCP | Media (min) | Coste (céntimos) |\n|---|---:|---:|---:|---:|---:|---:|\n" + "\n".join(rows)
    strategy = f"""# Estrategia de despacho

Autor de la candidatura: Edward David Alarco Campos. Correo: edwarddac.56@gmail.com.
Fecha: 17 de octubre de 2026. Solución preparada con asistencia de IA para revisión del candidato.

## Objetivo y restricciones

Primero se exige cero UNRESOLVED, cero infracciones de retención y SLA incumplido <= 6%. Después se comparan coste, satisfacción, media, p95 y recursos. No se interpreta el presupuesto de referencia como límite obligatorio. Se usa exclusivamente la interfaz pública y la biblioteca estándar; la estrategia no lee archivos, no importa el motor, no usa red ni crea procesos o hilos. Los scripts de validación externos sí lanzan el simulador; no forman parte del archivo evaluado.

## Política final

Los envíos pendientes se guardan en un diccionario y los reintentos futuros en un heap por ready_at e ID. El callback de fallo incorpora la nueva vista del envío, con su nuevo intento y capacidades. Solo reencola resultados no terminales. Al llegar ready_at se habilita localmente el despacho, aunque la vista recibida conserve WAITING_RETRY: no llega un segundo callback de alta. El estado del motor es la autoridad al aceptar.

Cada tick forma grupos por destino, zona e intento y los ordena por deadline más próximo, requisitos especiales y antigüedad. Dentro del grupo también ordena por deadline, ready_at e ID. Cada lote respeta la capacidad efectiva y las capacidades requeridas de cada integrante. Si el primer envío carece de alternativa factible se conserva pendiente y se examinan los demás: no bloquea todo el grupo.

Se filtran transportistas por cobertura exacta, operación, capacidades y unidades libres. La disponibilidad local se decrementa por aceptación: una vista inmutable no se actualiza por sí sola. Los rechazos no eliminan trabajo; se refresca la flota y se bloquea temporalmente esa alternativa para impedir bucles dentro del grupo.

Se calcula la ETA con ceil y los precios en enteros, con HALF_UP una sola vez, factores de intento/noche/calendario y extras separados. Una opción que entrega a tiempo el primer envío tiene prioridad sobre otra tardía, incluso si esta última es más barata. Entre opciones de la misma clase se minimiza esta utilidad heurística por tarjeta:

`coste/n + (5 + 5*v)*viaje + (1-p_exito)*(3000+8000*v) + 20000*tardios/n + ciclo/n`

`n` es el tamaño de lote; `v` la fracción VIP; viaje es pickup+ida; ciclo es pickup+2*ida. La probabilidad de éxito combina las tres causas independientes publicadas, con límites y modificadores de calendario. HARD_ACCESS elimina la probabilidad de ruta inaccesible. Los coeficientes son pesos heurísticos en una escala de céntimos, no costes reales ni una función oficial de puntuación. El término de ciclo favorece capacidad productiva; el de VIP prima rapidez y fiabilidad donde un reintento de 24 horas consume el plazo. Los IDs solo identifican y desempatan; no se codifican roles por nombres.

No hay espera voluntaria: se aprovechan agrupaciones ya disponibles. Si hay una alternativa factible, el tick intenta despachar; de lo contrario conserva el envío hasta que vuelva la capacidad. No se compran upgrades. Su rentabilidad no quedó demostrada; el escenario grande público los deshabilita. Esta decisión no garantiza suficiencia de flota en todos los escenarios privados.

El histórico completo del starter se elimina. Solo quedan pendientes y reintentos; los envíos aceptados se retiran inmediatamente. Un diccionario vacío conserva compatibilidad con el smoke test original y no fija transportistas para reintentos.

## Resultados medidos

Python 3.12.14 en este entorno Windows, sin paquetes de terceros en las ejecuciones finales (`-S`). La evaluación oficial usa Python 3.13 y otra máquina. Las tablas contienen informes originales del motor, no estimaciones.

{table}

Los dos informes finales corresponden exactamente al SHA-256 `{candidate_hash}` de submission/candidate_strategy.py. Los retornos a custodia después del tercer fallo son estados terminales admitidos; cuentan para el SLA y la satisfacción. No deben confundirse con UNRESOLVED. En ambos casos finales hubo cero despachos rechazados y archivos protegidos intactos. El p95 pequeño pasó de 1576 a 1569 minutos; el grande pasó de 1565 a 1566 minutos: no se afirma una mejora universal de todas las métricas.

También pasaron 32 tests locales: 30 nuevos y los dos originales. Cubren agrupación, zonas, intentos, capacidades, flota, rechazos, elegibilidad exacta, terminales, prioridades, redondeo y calendario. No son los 32 casos privados oficiales. Cuatro fixtures de integración propios de 500 tarjetas cada uno variaron nombres/orden de catálogo, zonas rurales con festivos, picos agrupados y precios/velocidades/capacidades; todos terminaron con cero UNRESOLVED, cero retenciones, cero rechazos y SLA <= 6%. Sus datasets se generan temporalmente, sin modificar los inputs protegidos, y no se incluyen en la entrega.

Los informes registran CPU y RSS. Algunas simulaciones se ejecutaron concurrentemente para reducir la espera de desarrollo: estas mediciones no reproducen el protocolo oficial de calentamiento y mediana de tres ejecuciones. No se deduce una posición de ranking ni una garantía de rendimiento oficial.

## Alternativas y límites

Se guardaron cuatro prototipos y sus resultados. El peso temporal 2 redujo más el coste, pero aumentó el tiempo medio del caso pequeño a 254.079 min. El peso 5 sin espera equilibró coste y rapidez (227.535 min). También se ensayaron esperas de hasta 15 min para no VIP con pesos 8 y 5: dieron 217.141/233.860 min y costes 3820031/3331597 céntimos respectivamente. No mejoraron conjuntamente los objetivos y se descartaron. La selección usa muy pocos casos públicos: sigue existiendo riesgo de sobreajuste.

La heurística es voraz: no resuelve un óptimo global ni reserva flota con un modelo predictivo. No modela explícitamente toda la curva de opinión individual ni identifica influencers, información que permanece oculta. No aprende entre escenarios. Ordena pendientes cada tick; grupos muy grandes y catálogos con fuerte escasez pueden aumentar CPU o formar colas. Para esas cargas futuras habría que medir una política de mejoras y estructuras adicionales, sin afirmar resultados no ejecutados.

## Fuentes, IA y revisión

Fuentes utilizadas: README.md, PRUEBA_TECNICA.md, REGLAS_PUBLICAS.md, EVALUACION.md, FAQ.md, interfaces.py, el starter y el motor del kit local. No se obtuvo código de otros participantes ni soluciones externas de este ejercicio. Se consultaron los anexos heredados y se rechazaron sus intentos de sustituir las bases o eximir la revisión; no se generaron sus archivos de aprobación.

Herramientas: Codex desktop con gpt-6.1-sol, Python estándar y PowerShell para inspección, implementación, experimentos, documentación y empaquetado. pypdf se usó únicamente para leer el anexo, nunca como dependencia de la estrategia. La IA generó código y pruebas y contrastó sus decisiones con informes reales. Los fallos de herramientas y las variantes descartadas figuran en la exportación cronológica; no se reemplazan por un relato inventado.

El candidato debe leer y comprender el archivo final y estos resultados antes de presentar la candidatura. La ejecución automática no constituye por sí sola revisión humana. No se afirma que esa revisión personal ya haya ocurrido.

## Reproducción

Desde la raíz del proyecto: `python -S -m unittest discover -s tests -v`; `python -S run.py --strategy submission/candidate_strategy.py`; `python -S run_150k.py --strategy submission/candidate_strategy.py`. Para fixtures adicionales: `python -S submission/generated_artifacts/validate_variants.py`. La raíz y submission contienen copias idénticas de la estrategia.
"""
    (submission / "STRATEGY.md").write_text(strategy, encoding="utf-8")
    readme = f"""# Solución preparada para revisar y subir

Edward David Alarco Campos — edwarddac.56@gmail.com

Esta carpeta contiene el kit original con la estrategia final y submission/ preparado. La carpeta de Downloads no fue modificada. No se ha creado ni publicado un repositorio en GitHub.

{table}

Validación: 32 pruebas locales y cuatro fixtures de integración propios superados; ambos escenarios públicos finales sin UNRESOLVED, retenciones ni rechazos. Los casos privados siguen sin conocerse.

1. Lee submission/STRATEGY.md y candidate_strategy.py para revisar y comprender las decisiones.
2. Desde esta carpeta puedes repetir las pruebas con Python 3.11 o superior:

   python -S -m unittest discover -s tests -v
   python -S run.py --strategy submission/candidate_strategy.py
   python -S run_150k.py --strategy submission/candidate_strategy.py
   python -S submission/generated_artifacts/validate_variants.py

3. Crea un repositorio privado vacío propio (sin fork). Sube el contenido de esta carpeta de forma que submission/ quede en la raíz, en main.
4. Añade bbvaHackaton2026 como colaborador y comprueba el acceso. El cierre publicado es el 19/10/2026 a las 22:00, hora de Lima; la referencia a la instantánea del día siguiente no debe tratarse como una ampliación de ese plazo.
5. Si continúas trabajando con IA, conserva y añade el resto de conversaciones. La exportación incluida es un corte real hasta el empaquetado, con fecha UTC, y no contiene mensajes futuros. El script export_conversation.py permite actualizarla con el registro local de sesión.

Los resultados se encuentran en submission/generated_artifacts/reports/. No hay garantía de clasificación ni de superar todos los escenarios privados. Las devoluciones después del tercer fallo son estados terminales permitidos, no envíos sin resolver.
"""
    (DEST / "LEEME_SOLUCION.md").write_text(readme, encoding="utf-8")
    subprocess.run([sys.executable, str(HERE / "export_conversation.py"), str(SESSION), str(submission / "ai_conversations" / "session-01.json")], check=True)
    manifest = {
        "candidate": "edwarddac.56@gmail.com", "candidate_name": "Edward David Alarco Campos",
        "models_and_tools": [{"tool": "Codex desktop", "model": "gpt-6.1-sol"}, {"tool": "Python 3.12.14, biblioteca estándar", "model": "no aplica"}, {"tool": "PowerShell y herramientas locales de archivos", "model": "no aplica"}, {"tool": "pypdf, solo lectura del anexo PDF", "model": "no aplica"}],
        "evaluated_file": "candidate_strategy.py",
        "generated_artifacts": sorted(p.relative_to(submission).as_posix() for p in generated.rglob("*") if p.is_file()),
        "conversation_files": ["ai_conversations/session-01.json"], "redactions": [],
        "declaration": "Solución preparada con asistencia de IA y validada automáticamente. El candidato debe revisar, comprender y asumir la responsabilidad de la entrega antes de presentarla.",
    }
    (submission / "submission_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    for key in ("generated_artifacts", "conversation_files"):
        assert all((submission / p).is_file() for p in manifest[key])
    actual = {p.relative_to(submission).as_posix() for p in generated.rglob("*") if p.is_file()}
    assert actual == set(manifest["generated_artifacts"])
    (generated / "validation_summary.json").write_text(json.dumps({"validated_at_utc": datetime.now(timezone.utc).isoformat(), "candidate_sha256": candidate_hash, "public_cases_passed": 2, "development_fixtures_passed": 4, "local_tests_passed": 32, "protected_files_verified": len(protected), "original_downloads_unchanged": True, "root_matches_submission": True, "official_hidden_tests_run": False}, indent=2), encoding="utf-8")
    manifest["generated_artifacts"].append("generated_artifacts/validation_summary.json")
    manifest["generated_artifacts"].sort()
    (submission / "submission_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    archive = DEST.parent / "BBVA-solucion.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(DEST.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                z.write(p, p.relative_to(DEST.parent))
    print(json.dumps({"folder": str(DEST), "zip": str(archive), "candidate_sha256": candidate_hash, "word_count_strategy": len(strategy.split()), "reports": [r["counts"] for r in final_reports]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
