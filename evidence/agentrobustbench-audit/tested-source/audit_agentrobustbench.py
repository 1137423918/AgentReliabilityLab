"""Audit pinned evaluation inputs and scorer boundaries without model inference.

Gold-derived controls below are evaluator diagnostics, never model predictions.
No upstream code is changed, no evaluation record becomes training data, and
no semantic family mapping is inferred from IDs alone.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

UPSTREAM_COMMIT = "111fd3db40491e0d7d8a5ec432b7ac1c6c64b2f1"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode(value):
    return json.loads(value) if isinstance(value, str) else value


def required_candidates(sample, call):
    name = call.get("name") or call.get("Action")
    return [set(t.get("parameters", {}).get("required", []))
            for t in decode(sample["tools"]) if t.get("name") == name]


def audit(root: Path, output: Path) -> dict:
    data_dir = root / "hf_data/datasets/api_eval"
    scorer_path = root / "leaderboard/scoring/eval_results.py"
    spec = importlib.util.spec_from_file_location("frozen_official_scorer", scorer_path)
    scorer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)
    rows, file_rows, clean, ids = [], [], [], {}
    methods = Counter()
    for path in sorted(data_dir.glob("*.jsonl")):
        raw = path.read_bytes()
        samples = [json.loads(line) for line in raw.splitlines() if line.strip()]
        eligible = []
        seen = set()
        for line_number, sample in enumerate(samples, 1):
            if sample["id"] in seen:
                raise ValueError(f"Duplicate ID within {path.name}")
            seen.add(sample["id"])
            multi = "multi_turn" in sample.get("category", "")
            for field in ["conversation", "tools", "golden_answers", "eval_config", "source", "perturbation"]:
                decode(sample[field])
            if not multi:
                eligible.append(sample)
                methods[decode(sample["eval_config"])["method"]] += 1
            rows.append({"file": path.name, "line": line_number, "id": sample["id"],
                         "benchmark": sample["benchmark"], "category": sample["category"],
                         "single_turn_eligible": not multi,
                         "record_sha256": digest(json.dumps(sample, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())})
        ids[path.stem] = {s["id"] for s in eligible}
        if path.stem == "clean":
            clean = eligible
        file_rows.append({"file": str(path.relative_to(root)), "sha256": digest(raw),
                          "bytes": len(raw), "records": len(samples),
                          "single_turn": len(eligible), "multi_turn_skipped": len(samples)-len(eligible)})

    controls = []
    for sample in clean:
        cfg, gold = decode(sample["eval_config"]), decode(sample["golden_answers"])
        if sample["benchmark"] != "bfcl_v3" or cfg["method"] != "exact_match" or not gold:
            continue
        # Isolate controls for which reference arguments satisfy at least one
        # matching tool's declared top-level required keys. This is not full
        # JSON Schema validation or proof of tool execution.
        refs = [{"name": g.get("name") or g.get("Action"),
                 "parameters": g.get("parameters") or g.get("arguments") or g.get("Action_Input") or {}} for g in gold]
        candidates = [required_candidates(sample, g) for g in refs]
        if not all(cs and any(req <= set(g["parameters"]) for req in cs)
                   for cs, g in zip(candidates, refs)):
            continue
        empty = [{"name": g["name"], "parameters": {}} for g in refs]
        known_missing = any(cs and all(bool(req) for req in cs) for cs in candidates)
        if not known_missing:
            continue
        base = {"benchmark": sample["benchmark"], "eval_config": cfg, "golden_answers": gold}
        original = scorer.score_record(dict(base, prediction={"tool_calls": refs}))
        ablated = scorer.score_record(dict(base, prediction={"tool_calls": empty}))
        controls.append({"id": sample["id"], "reference_control_official_correct": original["correct"],
                         "empty_argument_control_official_correct": ablated["correct"],
                         "empty_argument_control_missing_declared_required_keys": known_missing,
                         "scope": "gold-derived clean BFCL diagnostic; no model or real tool execution"})

    static_count = sum(x["records"] for x in file_rows)
    eligible_count = sum(x["single_turn"] for x in file_rows)
    skipped_count = static_count-eligible_count
    expectations = {"static_2718": static_count == 2718, "single_turn_2527": eligible_count == 2527,
                    "multi_turn_191": skipped_count == 191, "clean_199": len(clean) == 199,
                    "official_runtime_case_count_1194": len(clean)*6 == 1194,
                    "declared_full_scope_3721": eligible_count+len(clean)*6 == 3721}
    report = {"upstream_repository": "https://github.com/WillChow66/AgentRobustBench",
              "upstream_commit": UPSTREAM_COMMIT, "scorer_sha256": digest(scorer_path.read_bytes()),
              "data_files": file_rows, "observed_static_records": static_count,
              "observed_static_single_turn": eligible_count, "observed_skipped_multi_turn": skipped_count,
              "clean_single_turn": len(clean), "declared_runtime_cases_not_executed": len(clean)*6,
              "upstream_count_expectations": expectations, "single_turn_eval_methods": dict(methods),
              "exact_ID_overlap_with_clean": {k: {"matched": len(v & ids["clean"]), "unmatched": len(v-ids["clean"])} for k,v in ids.items()},
              "semantic_family_mapping_verified": False, "training_parquets_audited": False,
              "training_evaluation_disjointness_verified": False, "evaluation_data_used_for_training": False,
              "diagnostic_control_count": len(controls),
              "reference_controls_official_correct": sum(x["reference_control_official_correct"] for x in controls),
              "empty_argument_controls_official_correct": sum(x["empty_argument_control_official_correct"] for x in controls),
              "empty_argument_controls_missing_required_keys": sum(x["empty_argument_control_missing_declared_required_keys"] for x in controls),
              "model_inference": False, "training_run": False, "GPU_used": False,
              "benchmark_accuracy_measured": False,
              "limitations": ["Gold-derived evaluator controls are not neural predictions or benchmark accuracy.",
                              "The official BFCL matcher intentionally tolerates omitted arguments; this audit does not alter or relabel its metric.",
                              "Required-key presence is narrower than full JSON Schema validity or successful real tool execution.",
                              "Runtime perturbations are only counted from the published construction, not executed.",
                              "Shared IDs reveal exact reuse, not a complete semantic family mapping; no new train/test split is claimed.",
                              "Training Parquets and train/evaluation leakage require a separate audit before any training."]}
    output.mkdir(parents=True, exist_ok=False)
    (output / "report.json").write_text(json.dumps(report, indent=2)+"\n")
    (output / "record-manifest.jsonl").write_text("".join(json.dumps(row, sort_keys=True)+"\n" for row in rows))
    (output / "scorer-controls.json").write_text(json.dumps(controls, indent=2)+"\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.source, args.output)
    print(json.dumps({k: report[k] for k in ["observed_static_records", "observed_static_single_turn",
                    "observed_skipped_multi_turn", "diagnostic_control_count", "reference_controls_official_correct",
                    "empty_argument_controls_official_correct", "model_inference"]}))
    raise SystemExit(0 if all(report["upstream_count_expectations"].values()) else 2)


if __name__ == "__main__":
    main()
