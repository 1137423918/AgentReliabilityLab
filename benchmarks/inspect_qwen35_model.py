"""Verify this experiment's pinned third-party Qwen3.5 GGUF and native runtime.

The fetched original model card is a reference identity, not proof of the exact
source weight revision used by the quantizer. No inference is run here.
"""

import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import sys


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llama-source", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--runtime-manifest", type=Path, required=True)
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--library-directory", type=Path, required=True)
    parser.add_argument("--source-template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Refusing to overwrite a model manifest")
    expected = "cd76ec205963b3b33350093e6904d9de16c4e666fd104e1f632d25c7f15f2a13"
    if args.model.stat().st_size != 5627044256 or digest(args.model) != expected:
        raise ValueError("Quantized weights do not match pinned publisher bytes")
    runtime = json.loads(args.runtime_manifest.read_text())
    if runtime["backend_commit"] != "4783b1145c7073bb809f4c282ff4853cbfe42954":
        raise ValueError("Use this experiment's pinned native runtime")
    if digest(args.server) != runtime["server_sha256"]:
        raise ValueError("Native server hash changed")
    for root, entries in (
        (args.library_directory, runtime["runtime_libraries"]),
        (args.server.parent, runtime["server_bundle"]),
    ):
        for name, expected_hash in entries.items():
            path = Path(name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Runtime paths must be relative")
            if digest(root / path) != expected_hash:
                raise ValueError("Pinned runtime library or bundle changed")
    sys.path.insert(0, str(args.llama_source / "gguf-py"))
    import gguf

    reader = gguf.GGUFReader(args.model)
    architecture = reader.fields["general.architecture"].contents()
    file_type = gguf.LlamaFileType(reader.fields["general.file_type"].contents()).name
    parameters = sum(
        math.prod(int(n) for n in tensor.shape) for tensor in reader.tensors
    )
    template_hash = hashlib.sha256(
        reader.fields["tokenizer.chat_template"].contents().encode()
    ).hexdigest()
    eos = reader.fields["tokenizer.ggml.eos_token_id"].contents()
    if (
        architecture != "qwen35"
        or file_type != "MOSTLY_Q4_K_M"
        or parameters != 8953803264
        or len(reader.tensors) != 427
        or eos != 248046
        or template_hash
        != "a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715"
        or digest(args.source_template) != template_hash
    ):
        raise ValueError("GGUF metadata/template does not match inspected identity")
    result = {
        "model": "Qwen3.5-9B text-only",
        "quantizer_repository": "lmstudio-community/Qwen3.5-9B-GGUF",
        "quantizer_revision": "1379f25c6b505a3fc737bd7818cb09389cf807c1",
        "publisher_claimed_base_model": "Qwen/Qwen3.5-9B",
        "reference_source_metadata_revision": "c202236235762e1c871ad0ccb60c8ee5ba337b9a",
        "exact_quantizer_source_weight_revision": None,
        "backend_commit": runtime["backend_commit"],
        "release_tag": runtime["release_tag"],
        "server_sha256": runtime["server_sha256"],
        "model_sha256": expected,
        "model_bytes": args.model.stat().st_size,
        "runtime_libraries": runtime["runtime_libraries"],
        "server_bundle": runtime["server_bundle"],
        "runtime_artifacts": runtime["runtime_artifacts"],
        "architecture": architecture,
        "file_type": file_type,
        "tensor_count": len(reader.tensors),
        "parameter_count": parameters,
        "tensor_types": dict(
            collections.Counter(x.tensor_type.name for x in reader.tensors)
        ),
        "chat_template_sha256": template_hash,
        "chat_eos_token_id": eos,
        "chat_eos_matches_reference_tokenizer": True,
        "reference_model_config_eos_token_id": 248044,
        "weights_loaded_for_inference": False,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "verified": True,
                "architecture": architecture,
                "parameters": parameters,
                "template_matches_reference": True,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
