"""Build a standalone wheel with byte-identical canonical evidence modules."""

import argparse
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    root = package.parents[1]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if list(output.glob("*.whl")):
        raise RuntimeError("Use a new output directory; do not overwrite a wheel")
    modules = ["evidence_audit.py", "evidence_service.py", "evidence_mcp.py"]
    with tempfile.TemporaryDirectory(prefix="agentlab-evidence-build-") as directory:
        staging = Path(directory)
        source = staging / "src/agentlab_evidence"
        source.mkdir(parents=True)
        for name in modules:
            shutil.copyfile(root / "agent_lab" / name, source / name)
        for name in ["__init__.py", "__main__.py"]:
            shutil.copyfile(package / name, source / name)
        shutil.copyfile(package / "pyproject.toml", staging / "pyproject.toml")
        env = dict(os.environ, SOURCE_DATE_EPOCH="1795219200")
        subprocess.run(
            [sys.executable, "-c", "import sys; from setuptools.build_meta import build_wheel; build_wheel(sys.argv[1])", str(output)],
            cwd=staging, env=env, check=True,
        )
    wheels = list(output.glob("agentlab_evidence-0.1.0-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("Expected one evidence wheel")
    wheel = wheels[0]
    sources = {}
    with zipfile.ZipFile(wheel) as archive:
        for name in modules:
            raw = (root / "agent_lab" / name).read_bytes()
            if archive.read("agentlab_evidence/" + name) != raw:
                raise RuntimeError("Wheel source differs: " + name)
            sources[name] = hashlib.sha256(raw).hexdigest()
        metadata = BytesParser().parsebytes(archive.read("agentlab_evidence-0.1.0.dist-info/METADATA"))
        entry_points = archive.read("agentlab_evidence-0.1.0.dist-info/entry_points.txt").decode()
    receipt = {
        "wheel": wheel.name, "bytes": wheel.stat().st_size,
        "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "source_sha256": sources, "all_canonical_module_bytes_identical": True,
        "requires_dist": metadata.get_all("Requires-Dist"),
        "entry_points": entry_points,
        "installed_or_executed": False,
    }
    (output / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
