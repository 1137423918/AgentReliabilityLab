"""Probe actual LFX checkpoint serialization through a reopened SQLite store.

Finite values must round-trip. Non-finite values must be explicitly dropped so
the graph can recompute them, rather than silently restoring a genuine None.
Use the matching LFX environment; this does not install dependencies.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
from pathlib import Path


async def probe(repo: Path, output: Path) -> int:
    import lfx.graph.checkpoint.schema as subject
    from lfx.graph.checkpoint.schema import (
        GraphCheckpoint,
        VertexCheckpointData,
        deserialize_value,
        serialize_value,
        wire_has_opaque_drop,
    )
    from lfx.schema.data import Data
    from lfx.services.durable.sqlite_checkpoints import SqliteCheckpointStore

    source = Path(subject.__file__).resolve()
    expected = (repo / "src/lfx/src/lfx/graph/checkpoint/schema.py").resolve()
    if source != expected:
        raise RuntimeError("Imported LFX checkpoint source does not match --repo")
    output.mkdir(parents=True, exist_ok=False)
    db = output / "checkpoint.sqlite"
    rows = []
    for name, number in [
        ("nan", float("nan")),
        ("positive_infinity", float("inf")),
        ("negative_infinity", float("-inf")),
        ("finite", 3.25),
    ]:
        for form in ("scalar", "nested", "model"):
            value = (
                number if form == "scalar" else {"scores": [number]}
                if form == "nested" else Data(data={"score": number})
            )
            wire = serialize_value(value)
            checkpoint = GraphCheckpoint(
                run_id=f"{name}-{form}",
                vertex_results={
                    "producer": VertexCheckpointData(
                        vertex_id="producer", built=True, built_object=wire,
                    ),
                },
            )
            await SqliteCheckpointStore(db).save(checkpoint)
            loaded = await SqliteCheckpointStore(db).load(checkpoint.checkpoint_id)
            if loaded is None:
                raise RuntimeError("Saved checkpoint was not found")
            stored_wire = loaded.vertex_results["producer"].built_object
            restored = deserialize_value(stored_wire)
            actual = (
                restored if form == "scalar" or restored is None
                else restored["scores"][0] if form == "nested"
                else restored.data.get("score")
            )
            dropped = wire_has_opaque_drop(wire)
            stored_drop = wire_has_opaque_drop(stored_wire)
            faithful = isinstance(actual, float) and (
                math.isnan(actual) if math.isnan(number) else actual == number
            )
            safe = (
                faithful and not dropped and not stored_drop
                if math.isfinite(number) else dropped and stored_drop
            )
            rows.append({
                "number": name, "form": form, "before_repr": repr(number),
                "after_repr": repr(actual), "after_type": type(actual).__name__,
                "explicit_drop_before_store": dropped,
                "explicit_drop_after_store": stored_drop,
                "faithful_numeric_round_trip": faithful,
                "checkpoint_policy_safe": safe,
            })
    report = {
        "scope": "LFX tagged value -> GraphCheckpoint -> SQLite save/reopen/load",
        "not_a_graph_execution_or_model_benchmark": True,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "rows": rows,
        "safe_cases": sum(row["checkpoint_policy_safe"] for row in rows),
        "total_cases": len(rows),
    }
    text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    (output / "report.json").write_text(text)
    print(text, end="")
    return 0 if all(row["checkpoint_policy_safe"] for row in rows) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    return asyncio.run(probe(args.repo.resolve(), args.output.resolve()))


if __name__ == "__main__":
    raise SystemExit(main())
