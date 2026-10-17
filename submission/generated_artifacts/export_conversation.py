"""Export actual visible messages and tool calls from a Codex session log.

Excludes system/developer setup, hidden reasoning and internal telemetry.
Keeps user/assistant text, original image data, calls and tool results verbatim.
The snapshot naturally stops at export time; no history is reconstructed.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    entries = []
    for line in args.source.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        if item["type"] != "response_item":
            continue
        payload = item["payload"]
        kind = payload.get("type")
        if kind == "message" and payload.get("role") in ("user", "assistant"):
            entry = {k: payload[k] for k in ("type", "role", "channel", "content") if k in payload}
        elif kind in ("custom_tool_call", "custom_tool_call_output", "function_call", "function_call_output"):
            entry = {k: payload[k] for k in ("type", "call_id", "name", "input", "arguments", "output", "status") if k in payload}
        else:
            continue
        entries.append({"timestamp": item.get("timestamp"), **entry})
    result = {
        "tool": "Codex desktop",
        "model": "gpt-6.1-sol",
        "date": "2026-10-17",
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Actual visible user/assistant messages, original image attachment, technical tool calls and outputs through export time. Includes failed attempts. Excludes system/developer setup, hidden reasoning and internal telemetry, which are not user conversations.",
        "entries": entries,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {len(entries)} chronological entries.")


if __name__ == "__main__":
    main()
