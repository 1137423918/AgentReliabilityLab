"""Account for full request prefixes in three operator-planned retrieval controls.

The HTTP service is explicitly a tool-plan fixture, not an LLM. Native GGUF
vocabulary tokenization counts reference-rendered chat prefixes without weights
or inference. Plans and supplied symbol boundaries are not autonomous search.
"""

import argparse
import ast
import copy
import hashlib
import importlib.metadata
import itertools
import json
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jinja2.sandbox import ImmutableSandboxedEnvironment
from langchain_core.messages import ToolMessage
from deepagents.backends.utils import file_data_to_string
from agent_lab.worker import agent_phase, initial_files


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def json_write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def render(body, template):
    messages = copy.deepcopy(body["messages"])
    for message in messages:
        message["content"] = message.get("content") or ""
        for call in message.get("tool_calls", []):
            function = call["function"]
            if isinstance(function.get("arguments"), str):
                function["arguments"] = json.loads(function["arguments"])
    # The pinned source control contains no native chat control tokens in user
    # text. Do not accidentally count user text as privileged template markers.
    for message in messages:
        assert not re.search(r"<\|[^>]+\|>|</?think>", message["content"])
    environment = ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True)
    environment.filters["tojson"] = lambda value: json.dumps(value, ensure_ascii=False)

    def fail(message):
        raise ValueError(message)

    environment.globals["raise_exception"] = fail
    return environment.from_string(template).render(
        messages=messages, tools=body.get("tools", []),
        add_generation_prompt=True, enable_thinking=False,
        bos_token="", eos_token="<|im_end|>",
    )


def plan(policy, completed, virtual_path, goals, bounds):
    step = len(completed)
    if policy == "sequential_200":
        if step * 200 >= bounds[1]:
            return None
        return {"tool": "read_file", "args": {
            "file_path": virtual_path, "offset": step * 200, "limit": 200,
        }}
    if policy == "literal_grep_then_span":
        if step < len(goals):
            return {"tool": "grep", "args": {
                "pattern": "def " + goals[step] + "(", "path": virtual_path,
                "output_mode": "content",
            }}
        if step == len(goals):
            return {"tool": "read_file", "args": {
                "file_path": virtual_path, "offset": bounds[0] - 1,
                "limit": bounds[1] - bounds[0] + 1,
            }}
        return None
    if not completed:
        return {"tool": "inspect_python", "args": {"file_path": virtual_path, "limit": 120}}
    if step <= len(goals):
        outline = json.loads(completed[0]["content"])
        assert outline["status"] == "ok" and outline["next_offset"] is None
        entry = next(item for item in outline["items"] if item["name"] == goals[step - 1])
        return {"tool": "inspect_python", "args": {
            "file_path": virtual_path, "symbol_id": entry["id"], "limit": 120,
            "expected_sha256": outline["source_sha256"],
        }}
    return None


def run_control(policy, task, repo, destination, protocol, targets, source):
    destination.mkdir()
    requests = []
    errors = []
    goals = protocol["operator_supplied_goals"]
    bounds = min(t.lineno for t in targets), max(t.end_lineno for t in targets)
    virtual_path = "/" + protocol["source_file"]

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            try:
                assert self.path == "/v1/chat/completions"
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                body = json.loads(raw)
                requests.append({"body": body, "wire_bytes": len(raw), "wire_sha256": sha(raw)})
                completed = [m for m in body["messages"] if m["role"] == "tool"]
                next_step = plan(policy, completed, virtual_path, goals, bounds)
                message = {"role": "assistant", "content": "Operator retrieval control finished."}
                if next_step is not None:
                    assert next_step["tool"] in {t["function"]["name"] for t in body["tools"]}
                    message["content"] = ""
                    message["tool_calls"] = [{
                        "id": "control-" + str(len(completed)), "type": "function",
                        "function": {"name": next_step["tool"], "arguments": json.dumps(next_step["args"])},
                    }]
                response = {"id": "explicit-fixture", "object": "chat.completion", "created": 1,
                    "model": body["model"], "choices": [{"index": 0, "message": message,
                    "finish_reason": "tool_calls" if next_step else "stop"}]}
                encoded = json.dumps(response).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            except Exception as error:
                errors.append(repr(error))
                self.send_error(500, "Operator fixture failed")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with patch.dict(os.environ, {
            "AGENT_LAB_MODEL_URL": f"http://127.0.0.1:{server.server_port}/v1",
            "AGENT_LAB_MODEL_KEY": "explicit-loopback-fixture",
        }):
            state = agent_phase(repo, destination, task, task["files"], None)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
    assert not thread.is_alive() and not errors, errors
    expected_files = initial_files(repo, task, task["files"])
    assert set(state["files"]) == set(expected_files)
    assert all(file_data_to_string(state["files"][name]) == file_data_to_string(value)
               for name, value in expected_files.items())
    observed = {}
    replies = [m for m in state["messages"] if isinstance(m, ToolMessage)]
    for reply in replies:
        assert reply.status != "error", reply.content
        if reply.name == "inspect_python":
            page = json.loads(reply.content)
            assert page["status"] == "ok" and page["next_offset"] is None
            if page["mode"] == "source":
                observed.update({line["line"]: line["text"] for line in page["items"]})
        if reply.name == "read_file":
            header, separator, body = reply.content.partition("\n")
            compact = re.fullmatch(r"@@ lines (\d+)-(\d+) of (\d+) \|.*@@", header)
            if compact:
                start, end, total = map(int, compact.groups())
                lines = body.split("\n")
                assert separator and 1 <= start <= end <= total
                assert len(lines) == end - start + 1, "Compact read header/body disagree"
                observed.update({start + i: line for i, line in enumerate(lines)})
                continue
            for line in reply.content.splitlines():
                match = re.match(r"^\s*(\d+)(?:  |\t|:\t)(.*)$", line)
                if match:
                    observed[int(match[1])] = match[2]
    source_lines = source.splitlines()
    expected = {n: source_lines[n - 1] for node in targets for n in range(node.lineno, node.end_lineno + 1)}
    assert all(observed.get(n) == text for n, text in expected.items()), "Target source coverage is incomplete"
    assert len(requests) == len(replies) + 1
    json_write(destination / "requests.json", requests)
    return requests, {
        "policy": policy, "model_inference": False, "tool_calls": len(replies),
        "target_lines": len(expected), "all_target_lines_verbatim": True,
        "virtual_files_unchanged": True,
        "tool_response_utf8_bytes": sum(len(m.content.encode()) for m in replies),
        "http_request_bytes": sum(r["wire_bytes"] for r in requests),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol_path = ROOT / "benchmarks/context_budget_protocol.json"
    protocol = json.loads(protocol_path.read_text())
    assert file_sha(args.model) == protocol["model_sha256"]
    assert file_sha(args.template) == protocol["template_sha256"]
    template = args.template.read_text()
    repo = args.repo.resolve()
    task = json.loads((ROOT / protocol["task"]).read_text())
    assert task["base_commit"] == protocol["subject_commit"]
    source = file_data_to_string(initial_files(repo, task, task["files"])["/" + protocol["source_file"]])
    tree = ast.parse(source)
    targets = [next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
               for name in protocol["operator_supplied_goals"]]
    args.output.mkdir(parents=True, exist_ok=False)
    json_write(args.output / "protocol.json", protocol)
    outputs = []
    prompts = []
    for policy in protocol["policies"]:
        spec = copy.deepcopy(task)
        if policy == "python_outline_then_symbols":
            spec["required_features"].append("python_source_v1")
        destination = args.output / policy
        destination.mkdir()
        requests, row = run_control(policy, spec, repo, destination / "run", protocol, targets, source)
        row["requests"] = []
        for i, request in enumerate(requests):
            body = request["body"]
            text = render(body, template)
            path = destination / f"prefix-{i}.txt"
            path.write_text(text)
            prompts.append(path)
            row["requests"].append({
                "request_index": i, "wire_bytes": request["wire_bytes"],
                "wire_sha256": request["wire_sha256"], "prefix_sha256": sha(text.encode()),
                "prefix_bytes": len(text.encode()), "message_count": len(body["messages"]),
                "system_text_bytes": sum(len(m["content"].encode()) for m in body["messages"] if m["role"] == "system"),
                "tool_schema_json_bytes": len(json.dumps(body.get("tools", []), ensure_ascii=False).encode()),
                "tool_count": len(body.get("tools", [])),
            })
        outputs.append(row)
    with (args.output / "native-tokenizer.stderr.log").open("wb") as errors:
        result = subprocess.run([str(args.tokenizer.resolve()), str(args.model.resolve()), *map(str, prompts)],
                                capture_output=False, stdout=subprocess.PIPE, stderr=errors, timeout=120)
    (args.output / "native-token-ids.jsonl").write_bytes(result.stdout)
    assert result.returncode == 0, "Native vocabulary tokenizer failed; see stderr"
    token_rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(token_rows) == len(prompts)
    all_ids = iter(token_rows)
    for row in outputs:
        previous = []
        for request in row["requests"]:
            ids = next(all_ids)
            common = sum(1 for _ in itertools.takewhile(lambda pair: pair[0] == pair[1], zip(previous, ids)))
            request.update(reference_prefix_tokens=len(ids), prompt_only_lcp_tokens=common,
                           prompt_only_nonshared_tokens=len(ids) - common)
            previous = ids
        row.update(
            first_request_tokens=row["requests"][0]["reference_prefix_tokens"],
            final_context_tokens=row["requests"][-1]["reference_prefix_tokens"],
            logical_input_tokens=sum(r["reference_prefix_tokens"] for r in row["requests"]),
            prompt_only_nonshared_tokens=sum(r["prompt_only_nonshared_tokens"] for r in row["requests"]),
            final_with_generation_reserve_fits=(len(previous) + protocol["generation_reserve"] <= protocol["context_window"]),
        )
    report = {
        "scope": protocol["scope"], "protocol_sha256": file_sha(protocol_path),
        "source_sha256": sha(source.encode()), "model_sha256": protocol["model_sha256"],
        "template_sha256": protocol["template_sha256"], "tokenizer_binary_sha256": file_sha(args.tokenizer),
        "source_files_sha256": {str(p.relative_to(ROOT)): file_sha(p) for p in [
            ROOT / "agent_lab/worker.py", ROOT / "agent_lab/models.py", ROOT / "agent_lab/source_tools.py",
            Path(__file__), ROOT / "benchmarks/tokenize_vocab.c"]},
        "versions": {name: importlib.metadata.version(name) for name in [
            "deepagents", "langchain-openai", "langgraph", "jinja2"]},
        "policies": outputs, "rendering": protocol["rendering"], "limitations": protocol["limitations"],
        "inference": False, "gpu": False, "patch_generated": False, "acceptance_run": False,
    }
    json_write(args.output / "report.json", report)
    print(json.dumps({"stage": "complete", "policies": [{k: row[k] for k in [
        "policy", "tool_calls", "first_request_tokens", "final_context_tokens", "logical_input_tokens"]} for row in outputs]}))


if __name__ == "__main__":
    main()
