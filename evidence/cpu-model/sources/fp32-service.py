"""Resource-bounded CPU baseline using pinned local weights and their chat template.

Experimental OpenAI-compatible subset for this lab's non-streaming tool loop.
This runs real model.generate; no scripted responses or external API fallback.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import resource
import signal
import socket
import sys
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def messages_for_template(messages):
    result = []
    for original in messages:
        message = dict(original)
        if message.get("role") not in ("system", "user", "assistant", "tool"):
            raise ValueError("Unsupported message role")
        content = message.get("content") or ""
        if not isinstance(content, str):
            raise ValueError("This CPU baseline accepts text-only messages")
        message["content"] = content
        if message.get("tool_calls"):
            calls = []
            for original_call in message["tool_calls"]:
                call = dict(original_call)
                function = dict(call["function"])
                if isinstance(function["arguments"], str):
                    function["arguments"] = json.loads(function["arguments"])
                if not isinstance(function["arguments"], dict):
                    raise ValueError("Tool arguments must be JSON objects")
                call["function"] = function
                calls.append(call)
            message["tool_calls"] = calls
        result.append(message)
    return result


def parse_output(text, eos):
    content = text.rstrip()
    while eos and content.endswith(eos):
        content = content[: -len(eos)].rstrip()
    matches = list(re.finditer(r"<tool_call>\s*(.*?)\s*</tool_call>", content, re.S))
    if content.count("<tool_call>") != len(matches):
        return content, [], "incomplete_tool_call"
    calls = []
    try:
        for match in matches:
            value = json.loads(match.group(1))
            arguments = value["arguments"]
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            if not isinstance(value["name"], str) or not isinstance(arguments, dict):
                raise ValueError("Invalid generated tool call")
            calls.append(
                {
                    "id": "call_" + uuid.uuid4().hex,
                    "type": "function",
                    "function": {
                        "name": value["name"],
                        "arguments": json.dumps(arguments, ensure_ascii=False),
                    },
                }
            )
    except (ValueError, KeyError, TypeError):
        return content, [], "invalid_tool_json"
    remaining = re.sub(
        r"<tool_call>\s*.*?\s*</tool_call>", "", content, flags=re.S
    ).strip()
    return remaining, calls, None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--model-alias", default="agentlab-qwen3-4b")
    parser.add_argument("--port", type=int, default=18843)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--wall-seconds", type=int, default=2400)
    parser.add_argument("--request-seconds", type=int, default=180)
    parser.add_argument("--generation-seconds", type=int, default=170)
    args = parser.parse_args()
    if not 1 <= args.threads <= 4 or not 1 <= args.wall_seconds <= 2400:
        parser.error("Use 1–4 threads and a wall limit of at most 2400 seconds")
    if not 1 <= args.generation_seconds < args.request_seconds <= 180:
        parser.error("Generation must end before the at-most-180-second request limit")
    args.output.mkdir(parents=True)
    manifest = json.loads(
        (args.model_dir / "agentlab-download-validated.json").read_text()
    )
    if manifest["revision"] != args.revision:
        raise ValueError("The pinned local model revision does not match")
    meminfo = dict(
        line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines()
    )
    available = int(meminfo["MemAvailable"].split()[0]) * 1024
    cpus = len(os.sched_getaffinity(0))
    load = os.getloadavg()
    preflight = {
        "available_memory_bytes": available,
        "available_cpus": cpus,
        "load": load,
    }
    save(args.output / "resources.json", preflight)
    if available < 64 * 1024**3 or load[0] > cpus - args.threads:
        save(
            args.output / "rejected.json",
            {"reason": "insufficient_cpu_headroom", "model_loaded": False},
        )
        return 3
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", args.port)) == 0:
            raise RuntimeError("The task-specific inference port is already occupied")
    os.nice(max(0, 19 - os.getpriority(os.PRIO_PROCESS, 0)))
    resource.setrlimit(resource.RLIMIT_AS, (48 * 1024**3, 48 * 1024**3))
    for key in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ[key] = str(args.threads)
    os.environ.update(
        CUDA_VISIBLE_DEVICES="",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        TOKENIZERS_PARALLELISM="false",
    )
    started = time.monotonic()
    state = {"model_loaded": False, "request": None}

    def log(value):
        value = {
            "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            **value,
        }
        with (args.output / "events.jsonl").open("a") as stream:
            stream.write(json.dumps(value, ensure_ascii=False) + "\n")
            stream.flush()
        print(json.dumps(value, ensure_ascii=False), flush=True)

    def watchdog():
        while True:
            time.sleep(0.5)
            current = state["request"]
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
            reason = None
            if time.monotonic() - started > args.wall_seconds:
                reason = "service_wall_limit"
            elif (
                current and time.monotonic() - current["started"] > args.request_seconds
            ):
                reason = "request_wall_limit"
            elif rss > 36 * 1024**3:
                reason = "rss_limit"
            if reason:
                log(
                    {
                        "stage": "guard_stopped_service",
                        "reason": reason,
                        "model_loaded": state["model_loaded"],
                    }
                )
                os._exit(124)

    def stop(signum, frame):
        raise SystemExit(128 + signum)

    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, stop)
    threading.Thread(target=watchdog, daemon=True).start()
    log(
        {
            "stage": "loading",
            "device": "cpu",
            "dtype": "float32",
            "threads": args.threads,
        }
    )
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    tokenizer = AutoTokenizer.from_pretrained(
        args.model_dir, local_files_only=True, trust_remote_code=False
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.model_dir,
        local_files_only=True,
        trust_remote_code=False,
        dtype=torch.float32,
        attn_implementation="sdpa",
    ).eval()
    assert next(model.parameters()).device.type == "cpu"
    state["model_loaded"] = True
    provenance = {
        "pid": os.getpid(),
        "pid_start_ticks": Path(f"/proc/{os.getpid()}/stat")
        .read_text()
        .rsplit(")", 1)[1]
        .split()[19],
        "device": "cpu",
        "dtype": str(next(model.parameters()).dtype),
        "threads": torch.get_num_threads(),
        "nice": os.getpriority(os.PRIO_PROCESS, 0),
        "model": manifest["model"],
        "revision": args.revision,
        "parameter_count": sum(p.numel() for p in model.parameters()),
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "address_space_limit_gib": 48,
        "peak_rss_limit_gib": 36,
        "wall_seconds": args.wall_seconds,
        "request_seconds": args.request_seconds,
        "generation_seconds": args.generation_seconds,
        "context_limit": 32768,
        "max_new_tokens": 1536,
        "port": args.port,
        "service_source_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "chat_template_sha256": hashlib.sha256(
            tokenizer.chat_template.encode()
        ).hexdigest(),
    }
    save(args.output / "service.json", provenance)

    class Handler(BaseHTTPRequestHandler):
        def send_json(self, code, value):
            encoded = json.dumps(value, ensure_ascii=False).encode()
            try:
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if self.path == "/v1/models":
                self.send_json(
                    200,
                    {
                        "object": "list",
                        "data": [{"id": args.model_alias, "object": "model"}],
                    },
                )
            else:
                self.send_json(404, {"error": "Not found"})

        def do_POST(self):
            request_id = uuid.uuid4().hex
            begin = time.monotonic()
            state["request"] = {"id": request_id, "started": begin}
            try:
                if self.path != "/v1/chat/completions":
                    raise ValueError("Unsupported endpoint")
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= 2 * 1024 * 1024:
                    raise ValueError("Invalid request size")
                self.connection.settimeout(5)
                body = json.loads(self.rfile.read(length))
                if body.get("stream") or body["model"] != args.model_alias:
                    raise ValueError(
                        "Only the declared non-streaming model is supported"
                    )
                if (
                    body.get("tool_choice") not in (None, "auto")
                    or body.get("temperature", 0) != 0
                ):
                    raise ValueError(
                        "Only automatic tools and greedy decoding are supported"
                    )
                limit = body.get("max_completion_tokens", body.get("max_tokens", 1536))
                if type(limit) is not int or not 1 <= limit <= 1536:
                    raise ValueError("Output budget must be 1–1536 tokens")
                save(args.output / f"{request_id}.request.json", body)
                messages = messages_for_template(body["messages"])
                inputs = tokenizer.apply_chat_template(
                    messages,
                    tools=body.get("tools"),
                    add_generation_prompt=True,
                    return_dict=True,
                    return_tensors="pt",
                )
                input_count = inputs["input_ids"].shape[-1]
                if input_count + limit > 32768:
                    raise ValueError(
                        "Input and output exceed the declared context limit"
                    )
                log(
                    {
                        "stage": "generation_started",
                        "id": request_id,
                        "prompt_tokens": input_count,
                        "max_new_tokens": limit,
                    }
                )
                torch.manual_seed(int(body.get("seed", 42)))
                with torch.inference_mode():
                    output = model.generate(
                        **inputs,
                        max_new_tokens=limit,
                        do_sample=False,
                        max_time=args.generation_seconds,
                        pad_token_id=tokenizer.eos_token_id,
                    )
                generated = output[0, input_count:]
                raw = tokenizer.decode(generated, skip_special_tokens=False)
                (args.output / f"{request_id}.text").write_text(raw)
                content, calls, parse_error = parse_output(raw, tokenizer.eos_token)
                elapsed = time.monotonic() - begin
                truncated = (
                    len(generated) >= limit or elapsed >= args.generation_seconds
                )
                message = {"role": "assistant", "content": content or None}
                if calls:
                    message["tool_calls"] = calls
                response = {
                    "id": "cpu-" + request_id,
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": args.model_alias,
                    "choices": [
                        {
                            "index": 0,
                            "message": message,
                            "finish_reason": "length"
                            if truncated
                            else "tool_calls"
                            if calls
                            else "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": input_count,
                        "completion_tokens": len(generated),
                        "total_tokens": input_count + len(generated),
                    },
                }
                save(args.output / f"{request_id}.response.json", response)
                log(
                    {
                        "stage": "generated",
                        "id": request_id,
                        "prompt_tokens": input_count,
                        "completion_tokens": len(generated),
                        "seconds": round(elapsed, 3),
                        "tool_calls": len(calls),
                        "parse_error": parse_error,
                        "limit_reached": truncated,
                    }
                )
                self.send_json(200, response)
            except Exception as error:
                (args.output / f"{request_id}.error.log").write_text(
                    traceback.format_exc()
                )
                log(
                    {
                        "stage": "request_error",
                        "id": request_id,
                        "error_type": type(error).__name__,
                    }
                )
                self.send_json(
                    400 if isinstance(error, ValueError) else 500,
                    {
                        "error": {
                            "type": type(error).__name__,
                            "message": "CPU baseline request failed; inspect the private trace",
                        }
                    },
                )
            finally:
                state["request"] = None

        def log_message(self, *args):
            pass

    with HTTPServer(("127.0.0.1", args.port), Handler) as server:
        log({"stage": "ready", "model_loaded": True, **provenance})
        server.serve_forever(poll_interval=0.5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
