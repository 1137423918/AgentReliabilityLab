"""Compare fixed historical reference prompts with a native, vocabulary-only chat path."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess

POLICIES = ["sequential_200", "literal_grep_then_span", "python_outline_then_symbols"]
BODY_KEYS = {"model", "stream", "messages", "max_completion_tokens", "presence_penalty",
             "seed", "temperature", "tools", "top_p", "top_k", "min_p", "repeat_penalty"}


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def child_limits():
    os.nice(19)
    resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (90, 90))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["input", "model", "native", "library-dir", "runtime-dir", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    historical = json.loads((args.input / "report.json").read_text())
    assert sha(args.model) == historical["model_sha256"]
    libraries = json.loads((args.input / "runtime.json").read_text())["native_library_sha256"]
    for name, digest in libraries.items():
        directory = args.runtime_dir if name in {"libstdc++.so.6", "libgcc_s.so.1"} else args.library_dir
        assert sha(directory / name) == digest, name
    cases, refs, inputs = [], [], {}
    for policy in POLICIES:
        path = args.input / policy / "requests.json"
        inputs[str(path.relative_to(args.input))] = sha(path)
        requests = json.loads(path.read_text())
        recorded = next(p for p in historical["policies"] if p["policy"] == policy)["requests"]
        assert len(requests) == len(recorded)
        for i, request in enumerate(requests):
            body = request["body"]
            assert set(body) == BODY_KEYS and body["stream"] is False
            assert body["messages"][-1]["role"] in {"user", "tool"}
            assert all(m["role"] in {"system", "user", "assistant", "tool"} for m in body["messages"])
            wire = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
            assert len(wire) == request["wire_bytes"]
            assert hashlib.sha256(wire).hexdigest() == request["wire_sha256"]
            prefix = args.input / policy / f"prefix-{i}.txt"
            assert sha(prefix) == recorded[i]["prefix_sha256"]
            inputs[str(prefix.relative_to(args.input))] = sha(prefix)
            cases.append({"id": f"{policy}/{i}", "body": body})
            refs.append(prefix.read_bytes())
    assert len(cases) == 14
    old_tokens_path = args.input / "native-token-ids.jsonl"
    old_tokens = [json.loads(line) for line in old_tokens_path.read_text().splitlines()]
    assert len(old_tokens) == len(cases)
    inputs[old_tokens_path.name] = sha(old_tokens_path)
    write(args.output / "cases.json", cases)
    env = dict(os.environ, LD_LIBRARY_PATH=f"{args.runtime_dir.resolve()}:{args.library_dir.resolve()}",
               CUDA_VISIBLE_DEVICES="", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
    with (args.output / "native.jsonl").open("wb") as out, (args.output / "native.log").open("wb") as err:
        result = subprocess.run([str(args.native.resolve()), str(args.model.resolve()),
                                 str((args.output / "cases.json").resolve())],
                                env=env, stdout=out, stderr=err, timeout=120,
                                preexec_fn=child_limits)
    assert result.returncode == 0, result.returncode
    native = [json.loads(line) for line in (args.output / "native.jsonl").read_text().splitlines()]
    assert len(native) == len(cases)
    rows = []
    for case, reference, old_ids, observed in zip(cases, refs, old_tokens, native):
        assert observed["id"] == case["id"]
        assert hashlib.sha256(observed["template"].encode()).hexdigest() == historical["template_sha256"]
        prompt = observed["prompt"].encode()
        assert "".join(p["text"] for p in observed["parts"]) == observed["prompt"]
        common = next((i for i, pair in enumerate(zip(reference, prompt)) if pair[0] != pair[1]), min(len(reference), len(prompt)))
        rows.append({"id": case["id"], "bytes_equal": prompt == reference,
                     "server_matches_common_chat": observed["prompt"] == observed["common_chat_prompt"],
                     "token_ids_equal": observed["flattened_parse_special_tokens"] == old_ids,
                     "reference_bytes": len(reference), "native_bytes": len(prompt),
                     "reference_tokens": len(old_ids),
                     "native_flattened_tokens": len(observed["flattened_parse_special_tokens"]),
                     "reference_sha256": hashlib.sha256(reference).hexdigest(),
                     "native_sha256": hashlib.sha256(prompt).hexdigest(),
                     "common_prefix_bytes": common, "format": observed["format"],
                     "native_parts": len(observed["parts"]),
                     "input_parts": sum(p["is_input"] for p in observed["parts"]),
                     "reference_at_difference": reference[common:common + 160].decode(errors="replace"),
                     "native_at_difference": prompt[common:common + 160].decode(errors="replace")})
    report = {"scope": "Replay of 14 fixed historical requests through the pinned shared library's actual oaicompat_chat_params_parse and common-chat renderer, with vocabulary-only model loading. No HTTP listener, inference context, generation, or observed inference usage.",
              "backend_commit": "4783b1145c7073bb809f4c282ff4853cbfe42954",
              "model_sha256": historical["model_sha256"], "template_sha256": historical["template_sha256"],
              "native_binary_sha256": sha(args.native), "libraries_sha256": libraries,
              "historical_inputs_sha256": inputs,
              "driver_sha256": sha(Path(__file__)),
              "inference_context_created": False, "gpu_used": False,
              "limits": {"address_space_gib": 4, "cpu_seconds": 90, "wall_seconds": 120, "nice": 19},
              "rows": rows, "identical_bytes": sum(r["bytes_equal"] for r in rows),
              "identical_token_arrays": sum(r["token_ids_equal"] for r in rows)}
    write(args.output / "report.json", report)
    print(json.dumps({k: report[k] for k in ["identical_bytes", "identical_token_arrays", "inference_context_created", "gpu_used"]}))


if __name__ == "__main__":
    main()
