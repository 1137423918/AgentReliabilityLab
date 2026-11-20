"""Concurrent real-file artifact cleanup through Google ADK's public service API.

No model or cloud calls. Thread scheduling is unforced; deterministic regression
coverage belongs in the accompanying upstream tests, not an inferred success rate.
"""

import argparse
import asyncio
import hashlib
import inspect
import json
from pathlib import Path
import time

from google.adk.artifacts.file_artifact_service import FileArtifactService
from google.genai import types


async def run(output: Path, rounds: int) -> bool:
    output.mkdir(parents=True, exist_ok=False)
    results = []
    started = time.monotonic()
    for index in range(rounds):
        root = output / f"round-{index:03d}"
        first = FileArtifactService(root)
        second = FileArtifactService(root)
        scope = {"app_name": "app", "user_id": "user", "session_id": "session"}
        for version in range(3):
            await first.save_artifact(
                **scope, filename="report", artifact=types.Part(text=f"version {version}")
            )
        nested = types.Part(text="preserved nested output")
        await first.save_artifact(**scope, filename="report/details", artifact=nested)
        outcomes = await asyncio.wait_for(
            asyncio.gather(
                first.delete_artifact(**scope, filename="report"),
                second.delete_artifact(**scope, filename="report"),
                return_exceptions=True,
            ),
            timeout=30,
        )
        remaining = await first.list_versions(**scope, filename="report")
        survivor = await second.load_artifact(**scope, filename="report/details")
        errors = [{"type": type(value).__name__, "message": str(value)} for value in outcomes if isinstance(value, BaseException)]
        results.append({"round": index, "errors": errors, "remaining_parent_versions": remaining, "nested_preserved": survivor == nested})
    source = Path(inspect.getfile(FileArtifactService))
    passed = all(not value["errors"] and not value["remaining_parent_versions"] and value["nested_preserved"] for value in results)
    report = {"scope": "Unforced concurrent public-API filesystem cleanup; not model inference or a general reliability rate", "rounds": rounds, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "all_observed_calls_succeeded_and_nested_preserved": passed, "wall_seconds": time.monotonic() - started, "results": results}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}), flush=True)
    print(json.dumps({"rounds_with_errors": sum(bool(v["errors"]) for v in results), "errors": [e for v in results for e in v["errors"]][:8]}), flush=True)
    return passed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.rounds <= 1000:
        parser.error("rounds must be between 1 and 1000")
    return 0 if asyncio.run(run(args.output.resolve(), args.rounds)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
