"""Build the small budget wheel from the canonical Agent Lab source files."""

import argparse
import hashlib
import json
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
    modules = ["request_budget.py", "storage.py", "async_request_budget.py"]
    with tempfile.TemporaryDirectory(prefix="agentlab-budget-build-") as directory:
        staging = Path(directory)
        source = staging / "src/durable_agent_budget"
        source.mkdir(parents=True)
        for name in modules:
            shutil.copyfile(root / "agent_lab" / name, source / name)
        shutil.copyfile(package / "__init__.py", source / "__init__.py")
        shutil.copyfile(package / "pyproject.toml", staging / "pyproject.toml")
        subprocess.run(
            [sys.executable, "-m", "pip", "wheel", "--no-deps",
             "--no-build-isolation", "--wheel-dir", str(output), str(staging)],
            check=True,
        )
    wheels = list(output.glob("agentlab_durable_budget-0.1.0-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("Expected one budget wheel in the output directory.")
    wheel = wheels[0]
    sources = {}
    with zipfile.ZipFile(wheel) as archive:
        for name in modules:
            raw = (root / "agent_lab" / name).read_bytes()
            if archive.read("durable_agent_budget/" + name) != raw:
                raise RuntimeError("Wheel source differs: " + name)
            sources[name] = hashlib.sha256(raw).hexdigest()
    receipt = {"wheel": wheel.name, "bytes": wheel.stat().st_size,
               "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
               "source_sha256": sources, "all_module_bytes_identical": True}
    (output / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
