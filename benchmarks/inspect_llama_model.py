"""Inspect and hash this lab's derived Qwen3 GGUF before launching inference.

Use gguf-py from the pinned, verified llama.cpp source archive. Model weights and
runtime libraries remain external artifacts; this creates only a fresh manifest.
"""

import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import sys


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llama-source", type=Path, required=True)
    parser.add_argument("--model-directory", type=Path, required=True)
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--library-directory", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Refusing to overwrite an existing manifest")
    artifacts = json.loads(args.artifacts.read_text())
    if artifacts["source_commit"] != "4783b1145c7073bb809f4c282ff4853cbfe42954":
        raise ValueError("Use this experiment's pinned llama.cpp source")
    sys.path.insert(0, str(args.llama_source / "gguf-py"))
    import gguf

    model = args.model_directory / "model-q4_k_m.gguf"
    reader = gguf.GGUFReader(model)
    architecture = reader.fields["general.architecture"].contents()
    file_type = gguf.LlamaFileType(reader.fields["general.file_type"].contents()).name
    parameters = sum(
        math.prod(int(n) for n in tensor.shape) for tensor in reader.tensors
    )
    template = reader.fields["tokenizer.chat_template"].contents()
    template_hash = hashlib.sha256(template.encode()).hexdigest()
    if (
        architecture != "qwen3"
        or file_type != "MOSTLY_Q4_K_M"
        or parameters != 4022468096
        or len(reader.tensors) != 398
        or template_hash
        != "64f85b198065d0fba2a81f37e10ed68161ce2c19a754c7100e67e0ca2ee9c326"
        or reader.fields["tokenizer.ggml.eos_token_id"].contents() != 151645
    ):
        raise ValueError("Derived model metadata or embedded template does not match")
    f16 = args.model_directory / "model-f16.gguf"
    result = {
        "model": "Qwen/Qwen3-4B-Instruct-2507",
        "source_revision": "cdbee75f17c01a7cc42f958dc650907174af0554",
        "backend": "ggml-org/llama.cpp",
        "release_tag": artifacts["release_tag"],
        "backend_commit": artifacts["source_commit"],
        "precision": "GGUF Q4_K_M derived from FP16 conversion of fixed BF16 source; no importance matrix",
        "server_sha256": digest(args.server),
        "model_sha256": digest(model),
        "model_bytes": model.stat().st_size,
        "f16_model_sha256": digest(f16),
        "f16_model_bytes": f16.stat().st_size,
        "architecture": architecture,
        "file_type": file_type,
        "tensor_count": len(reader.tensors),
        "parameter_count": parameters,
        "tensor_types": dict(
            collections.Counter(t.tensor_type.name for t in reader.tensors)
        ),
        "chat_template_sha256": template_hash,
        "chat_template_matches_fixed_hf_tokenizer": True,
        "eos_token_id": 151645,
        "runtime_libraries": {
            n: digest(args.library_directory / n)
            for n in ["libstdc++.so.6", "libgcc_s.so.1"]
        },
        "server_bundle": {
            str(p.relative_to(args.server.parent)): digest(p)
            for p in sorted(args.server.parent.glob("*.so*"))
            if p.is_file()
        },
        "runtime_artifacts": artifacts,
        "weights_loaded_for_inference": False,
    }
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": "verified",
                "model_bytes": result["model_bytes"],
                "model_sha256": result["model_sha256"],
                "template_matches": True,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
