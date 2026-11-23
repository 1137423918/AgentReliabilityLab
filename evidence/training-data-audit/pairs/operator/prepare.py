"""Build paired research inputs from pinned Parquets without changing upstream.

Select the same metadata original_id in both train variants and exclude the
released validation IDs. Fingerprint checks are narrower than semantic dedup.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata

import pyarrow
import pyarrow.parquet as pq


def packed(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def key(row):
    value = row["extra_info"].get("original_id")
    if not isinstance(value, str) or not value:
        raise ValueError("Each row requires a nonempty original_id")
    return value


def fingerprints(row):
    text = row["extra_info"]["input"]
    turns = re.findall(r"<user>\s*(.*?)\s*</user>", text, flags=re.S)
    normalized = [" ".join(unicodedata.normalize("NFKC", x).split()) for x in turns]
    return {"prompt": digest(packed(row["prompt"])),
            "prompt_gold": digest(packed([row["prompt"], row["reward_model"]["ground_truth"]])),
            "input": digest(text.encode()),
            "normalized_user_turns": digest(packed(normalized)) if normalized else None}


def prepare(source: Path, output: Path):
    output.mkdir(parents=True, exist_ok=False)
    tables, rows, indices = {}, {}, {}
    for name in ["train", "mixed_train", "test"]:
        tables[name] = pq.ParquetFile(source / (name + ".parquet")).read(use_threads=False)
        rows[name] = tables[name].to_pylist()
        indices[name] = {key(r): i for i,r in enumerate(rows[name])}
        if len(indices[name]) != len(rows[name]):
            raise ValueError("Duplicate metadata original_id in " + name)
    val_ids = set(indices["test"])
    common = sorted((set(indices["train"]) & set(indices["mixed_train"])) - val_ids)
    if not common:
        raise ValueError("No eligible paired training IDs")
    chosen = {name: [indices[name][k] for k in common] for name in ["train", "mixed_train"]}
    chosen["test"] = list(range(len(rows["test"])))
    validation_fingerprints = {name: {f[name] for row in rows["test"] if (f := fingerprints(row))[name] is not None}
                               for name in ["prompt", "prompt_gold", "input", "normalized_user_turns"]}
    checks = {}
    for name in ["train", "mixed_train"]:
        values = [fingerprints(rows[name][i]) for i in chosen[name]]
        checks[name] = {kind: len({v[kind] for v in values if v[kind] is not None} & keys)
                        for kind,keys in validation_fingerprints.items()}
        if any(checks[name].values()):
            # Fail rather than silently change the registered pairing policy.
            raise ValueError("Selected rows still overlap validation fingerprints: " + name)
    manifest, artifacts = [], []
    for name in ["train", "mixed_train", "test"]:
        ids = chosen[name]
        selected_rows = [rows[name][i] for i in ids]
        # Preserve all row content and schema. Only selection and ordering change.
        table = tables[name].take(pyarrow.array(ids, type=pyarrow.int64()))
        dst = output / (name + "-paired.parquet")
        pq.write_table(table, dst, compression="zstd")
        reloaded = pq.ParquetFile(dst).read(use_threads=False).to_pylist()
        if packed(selected_rows) != packed(reloaded):
            raise ValueError("Written Parquet content did not round-trip")
        artifacts.append({"file": dst.name, "bytes": dst.stat().st_size, "sha256": digest(dst.read_bytes()),
                          "rows": len(ids), "canonical_rows_sha256": digest(packed(selected_rows)),
                          "row_content_and_schema_preserved": table.schema == tables[name].schema})
        for position, i in enumerate(ids):
            r = rows[name][i]
            manifest.append({"variant": name, "output_position": position, "source_row": i,
                             "original_id": key(r), "full_row_sha256": digest(packed(r)), **fingerprints(r)})
    selected_ids = set(common)
    report = {"upstream_commit": "111fd3db40491e0d7d8a5ec432b7ac1c6c64b2f1", "pyarrow_version": pyarrow.__version__,
              "policy": "Sorted common nonempty original_id across train and mixed_train, excluding every released test.parquet original_id; validation content/order unchanged.",
              "paired_training_ids": len(common), "validation_rows": len(rows["test"]),
              "excluded": {name: {"validation_id_rows": sum(key(r) in val_ids for r in rows[name]),
                                   "unpaired_non_validation_rows": sum(key(r) not in selected_ids and key(r) not in val_ids for r in rows[name]),
                                   "total_rows": len(rows[name])-len(chosen[name])} for name in ["train", "mixed_train"]},
              "validation_fingerprint_intersections": checks,
              "input_sha256": {name + ".parquet": digest((source/(name+".parquet")).read_bytes()) for name in rows},
              "output_artifacts": artifacts, "source_sha256": digest(Path(__file__).read_bytes()),
              "model_inference": False, "training_run": False, "official_benchmark_modified": False,
              "semantic_deduplication_verified": False,
              "limits": ["Pairing follows released metadata IDs; it is not an independent semantic equivalence proof.",
                         "Exact/normalized fingerprint disjointness does not rule out paraphrases, tool-family overlap or pretraining contamination.",
                         "test.parquet remains the released perturbed validation distribution, not an independent clean validation set.",
                         "Training variants have paired IDs, not automatically equal tokens, update steps, perturbation proportions or effective compute.",
                         "The new Parquets are private research inputs; canonical row hashes support reconstruction despite byte differences across Arrow versions.",
                         "No neural score, trained checkpoint, official benchmark result or GRPO reproduction is produced."]}
    (output/'report.json').write_text(json.dumps(report, indent=2)+"\n")
    (output/'selection-manifest.jsonl').write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in manifest))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    r = prepare(args.source, args.output)
    print(json.dumps({k:r[k] for k in ["paired_training_ids", "validation_rows", "excluded", "validation_fingerprint_intersections", "training_run"]}))


if __name__ == "__main__":
    main()
