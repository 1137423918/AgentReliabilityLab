"""Verify a materialized model snapshot against pinned canonical file metadata."""

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath


def verify(directory, canonical):
    root = directory.resolve()
    names = [item["path"] for item in canonical["files"]]
    if not names or len(names) != len(set(names)):
        raise ValueError("Canonical file names must be nonempty and unique")
    records = []
    for item in canonical["files"]:
        name = PurePosixPath(item["path"])
        if name.is_absolute() or ".." in name.parts or str(name) != item["path"]:
            raise ValueError("Canonical paths must be ordinary relative paths")
        path = root / str(name)
        if (
            path.is_symlink()
            or not path.is_file()
            or not path.resolve().is_relative_to(root)
        ):
            raise ValueError(f"Expected a materialized ordinary file: {name}")
        size = path.stat().st_size
        if size != item["size"]:
            raise ValueError(f"File size mismatch: {name}")
        sha256 = hashlib.sha256()
        git_blob = hashlib.sha1(f"blob {size}\0".encode())
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                sha256.update(block)
                git_blob.update(block)
        actual256, actual_blob = sha256.hexdigest(), git_blob.hexdigest()
        if item.get("sha256"):
            if actual256 != item["sha256"]:
                raise ValueError(f"SHA-256 mismatch: {name}")
        elif item.get("git_blob_sha1"):
            if actual_blob != item["git_blob_sha1"]:
                raise ValueError(f"Git blob hash mismatch: {name}")
        else:
            raise ValueError(f"No canonical content hash: {name}")
        records.append(
            {
                "path": str(name),
                "size": size,
                "sha256": actual256,
                "git_blob_sha1": actual_blob,
            }
        )
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        raw = args.canonical.read_bytes()
        canonical = json.loads(raw)
        records = verify(args.model_dir, canonical)
        result = {
            "model": canonical["model"],
            "revision": canonical["revision"],
            "validated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "canonical_manifest_sha256": hashlib.sha256(raw).hexdigest(),
            "total_bytes": sum(item["size"] for item in records),
            "files": records,
        }
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(result, indent=2) + "\n")
        temporary.replace(args.output)
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "verified",
                "files": len(records),
                "bytes": result["total_bytes"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
