"""A bounded real-model tool roundtrip on a read-only integration fixture.

Requires an explicitly started local model service. This is an interoperability
check, not a maintenance task, model quality benchmark or autonomous repair.
"""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import time
import urllib.request
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:18843/v1/chat/completions")
    args = parser.parse_args()
    endpoint = urlsplit(args.url)
    if endpoint.scheme != "http" or endpoint.hostname not in (
        "127.0.0.1",
        "localhost",
        "::1",
    ):
        raise ValueError("An explicit loopback HTTP service is required")
    args.output.mkdir(parents=True)
    # Only this fresh fixture is available to the executor. Never interpret model
    # paths as host paths or execute a generated command.
    fixture = args.output / "fixture.py"
    fixture.write_text('roundtrip_marker = "content_748291"\n')
    expected = fixture.read_text()
    body = copy.deepcopy(json.loads(args.diagnostic.read_text())["request"])
    if body.get("max_completion_tokens") != 128:
        raise ValueError("The recorded diagnostic must retain its output budget")
    report = {
        "scope": "Fresh neural generation and one read-only fixture tool roundtrip; not maintenance",
        "first_request_matches_recorded_diagnostic": True,
        "first_request_sha256": hashlib.sha256(
            json.dumps(body, sort_keys=True).encode()
        ).hexdigest(),
        "fixture_sha256": hashlib.sha256(expected.encode()).hexdigest(),
        "driver_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "model_requests": 0,
        "tool_executions": 0,
        "roundtrip_verified": False,
        "maintenance_score": False,
        "error": None,
    }

    def save(name, value):
        (args.output / name).write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n"
        )

    def request(index):
        save(f"{index}.request.json", body)
        started = time.monotonic()
        wire = json.dumps(body).encode()
        request = urllib.request.Request(
            args.url, data=wire, headers={"Content-Type": "application/json"}
        )
        report["model_requests"] += 1
        with urllib.request.urlopen(request, timeout=180) as response:
            value = json.loads(response.read())
        save(f"{index}.response.json", value)
        report[f"request_{index}_seconds"] = round(time.monotonic() - started, 3)
        return value["choices"][0]

    try:
        first = request(0)
        message = first["message"]
        calls = message.get("tool_calls", [])
        if first["finish_reason"] != "tool_calls" or len(calls) != 1:
            raise ValueError("Expected exactly one complete tool call")
        call = calls[0]
        function = call["function"]
        if function["name"] != "read_file" or json.loads(function["arguments"]) != {
            "file_path": "/sample.py"
        }:
            raise ValueError(
                "The requested tool is outside the read-only fixture scope"
            )
        result = fixture.read_text()
        report["tool_executions"] = 1
        save(
            "tool-result.json",
            {"tool_call_id": call["id"], "name": "read_file", "content": result},
        )
        body["messages"].extend(
            [
                message,
                {"role": "tool", "tool_call_id": call["id"], "content": result},
                {
                    "role": "user",
                    "content": "Return only the complete file contents from that tool result. Do not call another tool.",
                },
            ]
        )
        body["metadata"] = {"agentlab_phase": "tool_roundtrip_followup_not_maintenance"}
        final = request(1)
        final_message = final["message"]
        report["roundtrip_verified"] = (
            final["finish_reason"] == "stop"
            and not final_message.get("tool_calls")
            and (final_message.get("content") or "").strip() == expected.strip()
        )
        if not report["roundtrip_verified"]:
            raise ValueError(
                "Final response did not reproduce the actual tool result exactly"
            )
    except Exception as error:
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        save("report.json", report)
    print(json.dumps(report), flush=True)
    return 0 if report["roundtrip_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
