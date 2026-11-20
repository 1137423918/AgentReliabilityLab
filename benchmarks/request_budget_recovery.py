"""Real-repository transport-budget recovery using a declared fake HTTP model."""

import argparse
import hashlib
import json
import os
import select
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def wait_checkpoint(process, trace, deadline):
    buffered = b""
    while time.monotonic() < deadline:
        if select.select([process.stdout], [], [], 1)[0]:
            data = os.read(process.stdout.fileno(), 65536)
            if not data:
                break
            buffered += data
            while b"\n" in buffered:
                line, buffered = buffered.split(b"\n", 1)
                trace.write(line + b"\n")
                trace.flush()
                event = json.loads(line)
                if event.get("stage") == "checkpoint":
                    return event
        if process.poll() is not None:
            break
    raise RuntimeError(
        "Reference case exited or exceeded declared case wall before checkpoint"
    )


def reap(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=15)


def run_case(repo, task_path, directory, plan, protocol):
    directory.mkdir()
    run = directory / "run"
    observations = []
    errors = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            try:
                assert self.path == "/v1/chat/completions"
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                body = json.loads(raw)
                done = len([m for m in body["messages"] if m["role"] == "tool"])
                message = {
                    "role": "assistant",
                    "content": "Operator reference patch prepared.",
                }
                if done < len(plan):
                    step = plan[done]
                    message = {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "reference-" + str(done),
                                "type": "function",
                                "function": {
                                    "name": step["tool"],
                                    "arguments": json.dumps(step["args"]),
                                },
                            }
                        ],
                    }
                observations.append(
                    {
                        "request_body_sha256": sha(raw),
                        "request_body_bytes": len(raw),
                        "completed_tool_results": done,
                    }
                )
                response = {
                    "id": "explicit-reference-fixture",
                    "object": "chat.completion",
                    "created": 1,
                    "model": body["model"],
                    "choices": [
                        {
                            "index": 0,
                            "message": message,
                            "finish_reason": "tool_calls"
                            if done < len(plan)
                            else "stop",
                        }
                    ],
                }
                encoded = json.dumps(response).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            except Exception as error:
                errors.append(repr(error))
                self.send_error(500, "Reference fixture failed")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    environment = dict(
        os.environ,
        AGENT_LAB_MODEL_URL=f"http://127.0.0.1:{server.server_port}/v1",
        AGENT_LAB_MODEL_KEY="explicit-reference-fixture",
    )
    argv = [
        sys.executable,
        "-m",
        "agent_lab.worker",
        "--repo",
        str(repo),
        "--task",
        str(task_path),
        "--run-dir",
        str(run),
    ]
    deadline = time.monotonic() + protocol["case_wall_seconds"]
    interrupted = None
    before = None
    try:
        if directory.name == "checkpoint-sigkill":
            with (
                (directory / "interrupted.stdout.jsonl").open("wb") as trace,
                (directory / "interrupted.stderr.log").open("wb") as err,
            ):
                process = subprocess.Popen(
                    argv + ["--hold-after", "checkpoint"],
                    env=environment,
                    cwd=ROOT,
                    stdout=subprocess.PIPE,
                    stderr=err,
                    start_new_session=True,
                )
                try:
                    interrupted = wait_checkpoint(process, trace, deadline)
                    assert interrupted["tool_results"] == 1
                    before = json.loads((run / "model-requests.json").read_text())
                    assert len(before["reservations"]) == 1
                finally:
                    reap(process)
                    process.stdout.close()
                assert process.returncode == -9
                write_json(directory / "ledger-before-kill.json", before)
        with (
            (directory / "stdout.jsonl").open("wb") as stdout,
            (directory / "stderr.log").open("wb") as err,
        ):
            process = subprocess.Popen(
                argv,
                env=environment,
                cwd=ROOT,
                stdout=stdout,
                stderr=err,
                start_new_session=True,
            )
            try:
                code = process.wait(timeout=max(1, deadline - time.monotonic()))
            finally:
                reap(process)
        assert code == 0, "Reference failed; inspect retained worker/verification logs"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert not thread.is_alive() and not errors, errors
    result = json.loads((run / "result.json").read_text())
    ledger = json.loads((run / "model-requests.json").read_text())
    assert result["status"] == "ready_for_review" and result["tool_results"] == 2
    assert len(observations) == len(ledger["reservations"]) == 3
    assert [r["completed_tool_results"] for r in observations] == [0, 1, 2]
    for captured, reserved in zip(observations, ledger["reservations"]):
        assert all(
            captured[k] == reserved[k]
            for k in ("request_body_sha256", "request_body_bytes")
        )
    assert result["model_request_budget_snapshot"]["reserved_requests"] == 3
    if before is not None:
        assert before["identity"] == ledger["identity"]
    logs = [(run / f"verification-{i}.log").read_text() for i in range(4)]
    assert (
        "113 passed" in logs[1]
        and "119 passed" in logs[2]
        and '"passed": 28' in logs[3]
    )
    row = {
        "case": directory.name,
        "worker_returncode": code,
        "model_inference": False,
        "operator_plan": True,
        "interrupted": interrupted,
        "http_requests": observations,
        "result": result,
        "budget_journal": ledger,
        "same_ledger_after_resume": before is None
        or before["identity"] == ledger["identity"],
    }
    write_json(directory / "report.json", row)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    protocol_path = ROOT / "benchmarks/request_budget_protocol.json"
    protocol = json.loads(protocol_path.read_text())
    reference = json.loads((ROOT / protocol["reference_plan"]).read_text())
    task = json.loads((ROOT / protocol["acceptance_from"]).read_text())
    assert task["base_commit"] == reference["base_commit"] == protocol["subject_commit"]
    task["required_features"].append("model_request_budget_v1")
    task["prompt"] = (
        "Operator fixed HTTP tool-plan control for request budget and recovery; not model inference or autonomous repair."
    )
    task["evaluation_notes"] = protocol["scope"]
    task["model"] = {
        "mode": "local-openai",
        "model": "fixture-maintenance-plan",
        "revision": "operator-plan-v1",
        "max_output_tokens": 256,
        "timeout_seconds": 10,
        "seed": 42,
        "request_budget": protocol["limits"],
    }
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "protocol.json", protocol)
    write_json(args.output / "task.private.json", task)
    rows = [
        run_case(
            repo,
            (args.output / "task.private.json").resolve(),
            args.output / name,
            reference["model"]["plan"],
            protocol,
        )
        for name in protocol["cases"]
    ]
    assert len({r["result"]["patch_sha256"] for r in rows}) == 1
    assert rows[0]["http_requests"] == rows[1]["http_requests"]
    report = {
        "scope": protocol["scope"],
        "model_inference": False,
        "operator_plan": True,
        "protocol_sha256": sha(protocol_path.read_bytes()),
        "same_patch": True,
        "same_request_bodies": True,
        "cases": rows,
        "source_sha256": {
            n: sha((ROOT / n).read_bytes())
            for n in [
                "agent_lab/worker.py",
                "agent_lab/models.py",
                "agent_lab/repair.py",
                "agent_lab/request_budget.py",
                "tests/test_request_budget.py",
                "benchmarks/request_budget_recovery.py",
            ]
        },
        "limitations": protocol["limitations"],
    }
    write_json(args.output / "report.json", report)
    print(
        json.dumps(
            {
                "stage": "complete",
                "same_patch": True,
                "same_request_bodies": True,
                "requests_per_case": 3,
                "reference_cases": len(rows),
                "model_inference": False,
            }
        )
    )


if __name__ == "__main__":
    main()
