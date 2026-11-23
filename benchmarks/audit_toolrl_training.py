"""Inspect pinned training Parquets; report exact overlap without training.

This does not infer full semantic deduplication from identifiers or negative
hash matches. Original data and official benchmark scoring stay unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path
import re
import unicodedata

import pyarrow
import pyarrow.parquet as pq


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def normalize(text):
    return " ".join(unicodedata.normalize("NFKC", text).split())


def decode(value):
    return json.loads(value) if isinstance(value, str) else value


def audit(source: Path, output: Path):
    # Output must be a fresh directory. Read all input data without rewriting it.
    output.mkdir(parents=True, exist_ok=False)
    manifests, files, groups, diagnostics = [], [], {}, []
    counts = {"train": 3905, "mixed_train": 4000, "test": 79}
    for name, expected in counts.items():
        path = source / "training/data" / (name + ".parquet")
        parquet = pq.ParquetFile(path)
        table = parquet.read(use_threads=False)
        rows = table.to_pylist()
        original_ids, perturbations, categories, split_markers = Counter(), Counter(), Counter(), Counter()
        index = {key: {} for key in ["original_id", "prompt_sha256", "prompt_gold_sha256", "user_turns_sha256", "input_sha256"]}
        mismatches = Counter()
        for row_number, row in enumerate(rows):
            prompt, info, reward = row["prompt"], row["extra_info"], row["reward_model"]
            original = str(info.get("original_id") or "")
            original_ids[original] += 1
            perturbation = info.get("perturbation") or {}
            perturbations[str(perturbation.get("type"))] += 1
            categories[str(perturbation.get("mdp_category"))] += 1
            split_markers[str(info.get("split"))] += 1
            if len(prompt) != 2 or [x.get("role") for x in prompt] != ["system", "user"]:
                mismatches["two_message_system_user_shape"] += 1
            if len(prompt) == 2:
                if prompt[0]["content"] != info.get("instruction"):
                    mismatches["instruction_copy"] += 1
                if prompt[1]["content"] != info.get("input"):
                    mismatches["input_copy"] += 1
            if reward.get("ground_truth") != info.get("output"):
                mismatches["output_copy"] += 1
            input_text = str(info.get("input") or "")
            user_turns = re.findall(r"<user>\s*(.*?)\s*</user>", input_text, flags=re.S)
            fields = {"original_id": original, "prompt_sha256": sha(encode(prompt)),
                      "prompt_gold_sha256": sha(encode([prompt, reward.get("ground_truth")])),
                      "input_sha256": sha(input_text.encode()),
                      "user_turns_sha256": sha(encode([normalize(x) for x in user_turns])) if user_turns else ""}
            for key, value in fields.items():
                if value:
                    index[key].setdefault(value, []).append(row_number)
            manifests.append({"file": name + ".parquet", "row": row_number, **fields,
                              "ground_truth_sha256": sha(str(reward.get("ground_truth") or "").encode()),
                              "perturbation_type": perturbation.get("type"),
                              "mdp_category": perturbation.get("mdp_category"),
                              "full_row_sha256": sha(encode(row))})
        groups[name] = index
        files.append({"file": str(path.relative_to(source)), "sha256": sha(path.read_bytes()),
                      "bytes": path.stat().st_size, "rows": len(rows), "expected_rows": expected,
                      "matches_published_count": len(rows) == expected,
                      "schema": str(table.schema), "original_ids_nonempty_unique": len(set(original_ids)-{""}),
                      "empty_original_id_rows": original_ids.get("", 0),
                      "duplicate_original_id_rows_beyond_first": sum(v-1 for k,v in original_ids.items() if k),
                      "duplicate_exact_prompt_rows_beyond_first": sum(len(v)-1 for v in index["prompt_sha256"].values()),
                      "perturbation_types": dict(perturbations), "mdp_categories": dict(categories),
                      "split_markers": dict(split_markers), "mirror_or_shape_mismatches": dict(mismatches)})
    comparisons = []
    for left, right in itertools.combinations(counts, 2):
        item = {"left": left, "right": right, "overlap": {}}
        for key in groups[left]:
            shared = sorted(set(groups[left][key]) & set(groups[right][key]))
            item["overlap"][key] = {"distinct_shared_keys": len(shared),
                                    "left_rows": sum(len(groups[left][key][k]) for k in shared),
                                    "right_rows": sum(len(groups[right][key][k]) for k in shared)}
            for value in shared:
                diagnostics.append({"left": left, "right": right, "match": key, "key": value,
                                    "left_rows": groups[left][key][value], "right_rows": groups[right][key][value]})
        comparisons.append(item)
    # This comparison is a narrow screen: equal normalized user turn strings
    # can flag candidates, but different toolkits/answers can make them distinct.
    clean_path = source / "hf_data/datasets/api_eval/clean.jsonl"
    evaluation_users = {}
    for line in clean_path.read_text().splitlines():
        sample = json.loads(line)
        if "multi_turn" in sample.get("category", ""):
            continue
        users = [normalize(x["content"]) for x in decode(sample["conversation"]) if x["role"] == "user"]
        key = sha(encode(users))
        evaluation_users.setdefault(key, []).append(sample["id"])
    screen = {}
    for name in counts:
        shared = sorted(set(groups[name]["user_turns_sha256"]) & set(evaluation_users))
        screen[name] = {"distinct_shared_user_sequences": len(shared),
                        "training_or_validation_rows": sum(len(groups[name]["user_turns_sha256"][k]) for k in shared),
                        "evaluation_records": sum(len(evaluation_users[k]) for k in shared)}
        for key in shared:
            diagnostics.append({"left": name, "right": "official_clean_single_turn", "match": "normalized_user_sequence_only",
                                "key": key, "left_rows": groups[name]["user_turns_sha256"][key], "evaluation_ids": evaluation_users[key]})
    report = {"upstream_commit": "111fd3db40491e0d7d8a5ec432b7ac1c6c64b2f1", "pyarrow_version": pyarrow.__version__,
              "files": files, "comparisons": comparisons, "official_clean_user_sequence_screen": screen,
              "official_clean_file_sha256": sha(clean_path.read_bytes()),
              "audit_source_sha256": sha(Path(__file__).read_bytes()),
              "model_inference": False, "training_run": False, "new_split_created": False,
              "full_semantic_family_mapping_verified": False,
              "training_evaluation_disjointness_verified": False,
              "interpretation": ["test.parquet is the released training-time validation file, not the official 3721-case benchmark.",
                                 "Exact prompt or prompt+gold matches are literal reuse; shared metadata IDs alone require provenance interpretation.",
                                 "Equal normalized user turns alone are screening candidates, not proof of identical tasks/toolkits/answers.",
                                 "Zero matches under these fingerprints does not prove absence of semantic contamination or pretraining overlap.",
                                 "No input is changed; no new training split, neural baseline or paper reproduction is claimed."]}
    (output / "report.json").write_text(json.dumps(report, indent=2)+"\n")
    (output / "record-manifest.jsonl").write_text("".join(json.dumps(x, sort_keys=True)+"\n" for x in manifests))
    (output / "overlap-details.jsonl").write_text("".join(json.dumps(x, sort_keys=True)+"\n" for x in diagnostics))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.source, args.output)
    print(json.dumps({"rows": {x["file"]: x["rows"] for x in result["files"]}, "comparisons": result["comparisons"],
                      "official_clean_screen": result["official_clean_user_sequence_screen"], "training_run": False}))
    raise SystemExit(0 if all(x["matches_published_count"] and not x["mirror_or_shape_mismatches"] for x in result["files"]) else 2)


if __name__ == "__main__":
    main()
