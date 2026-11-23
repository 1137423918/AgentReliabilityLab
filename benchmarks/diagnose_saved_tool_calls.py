"""Read-only secondary diagnostics on a fixed generation-progress snapshot.

This does not import the model runner or scorer. Only four pinned pure upstream
functions and the loader field-name constant are extracted using the AST.
The ledger and full predictions remain private. Output is allowlisted metadata.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_lab.tool_schema import contracts_for_tools, diagnose_calls  # noqa: E402


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def load_upstream(path):
    source = path.read_text()
    tree = ast.parse(source)
    functions = {"_maybe_json_loads", "load_samples", "_normalize_tool_schema", "is_multi_turn"}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in functions]
    constants = [node for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_NESTED_FIELDS" for t in node.targets)]
    assert {n.name for n in nodes} == functions and len(constants) == 1
    ns = {"json": json, "Path": Path, "Any": Any, "Dict": Dict, "List": List}
    exec(compile(ast.Module(body=constants+nodes, type_ignores=[]), str(path), "exec"), ns)
    hashes = {n.name: sha(ast.get_source_segment(source, n).encode()) for n in nodes}
    return ns, hashes


def aggregate(rows):
    out = {"cases": len(rows), "stored_official_correct": sum(r["stored_official_score"]["correct"] for r in rows), "views": {}}
    for view in ("raw", "upstream_fc_projection"):
        cases, calls, keywords, keyword_cases, cross = Counter(), Counter(), Counter(), Counter(), Counter()
        for row in rows:
            d = row["diagnostics"][view]
            cases[d["status"]] += 1
            cross[(str(row["stored_official_score"]["correct"]).lower()+"/"+d["status"])] += 1
            seen = set()
            for call in d["calls"]:
                calls[call["status"]] += 1
                keywords.update(call["violations"])
                seen.update(call["violations"])
            keyword_cases.update(seen)
        out["views"][view] = {"case_statuses": dict(sorted(cases.items())), "call_statuses": dict(sorted(calls.items())), "violation_occurrences": dict(sorted(keywords.items())), "cases_by_violation_keyword": dict(sorted(keyword_cases.items())), "stored_official_correct_cross_case_status": dict(sorted(cross.items()))}
    return out


def run(args):
    started = time.monotonic()
    protocol_raw = args.protocol.read_bytes()
    protocol = json.loads(protocol_raw)
    # Pin input and implementation before opening the saved prediction values.
    assert sha(args.ledger.read_bytes()) == protocol["ledger_sha256"]
    root = args.upstream
    for rel, expected in protocol["upstream_source_sha256"].items():
        assert sha((root/rel).read_bytes()) == expected, rel
    for rel, expected in protocol["analysis_source_sha256"].items():
        assert sha((args.source/rel).read_bytes()) == expected, rel
    versions = {n: importlib.metadata.version(n) for n in protocol["versions"]}
    assert versions == protocol["versions"], versions
    runner, function_hashes = load_upstream(root/"scripts/run_eval.py")
    assert function_hashes == protocol["extracted_function_sha256"]
    normalize = runner["_normalize_tool_schema"]
    # Projection controls use synthetic values, before private predictions.
    alias_schema = {"type": "dict", "properties": {k: {"type": k} for k in ["dict", "tuple", "list", "any", "str", "int", "float", "bool", "list(str)"]}}
    before = encoded(alias_schema)
    projected = normalize(alias_schema)
    assert projected["type"] == "object"
    assert [v["type"] for v in projected["properties"].values()] == ["object", "array", "array", "string", "string", "integer", "number", "boolean", "list(str)"]
    assert encoded(alias_schema) == before
    data = root/"hf_data/datasets/api_eval/clean.jsonl"
    samples = [s for s in runner["load_samples"](data) if not runner["is_multi_turn"](s)]
    assert len(samples) == 199 and len({s["id"] for s in samples}) == 199
    contracts = {}
    inventory = []
    for index, sample in enumerate(samples, 1):
        views = {view: contracts_for_tools(sample["tools"], projection) for view, projection in [("raw", None), ("upstream_fc_projection", normalize)]}
        contracts[index] = views
        inventory.append({"case_index": index, "id_sha256": sha(sample["id"].encode()), "sample_sha256": sha(encoded(sample)), "benchmark": sample["benchmark"], "tool_count": len(sample["tools"]), "views": {view: {"schema_statuses": dict(sorted(Counter(c.status for cs in view_contracts.values() for c in cs).items())), "duplicate_names": sum(len(cs)>1 for cs in view_contracts.values())} for view, view_contracts in views.items()}})
    # No runner/scorer import, parsing of raw model text, neural call or write to
    # original artifacts occurs below this boundary.
    state_raw = args.ledger.read_bytes()
    assert sha(state_raw) == protocol["ledger_sha256"]
    state = json.loads(state_raw)
    assert len(state["attempts"]) == 284 and len(state["results"]) == 282
    assert state["owner_sha256"] == protocol["definition_owner_sha256"]
    rows = []
    for key, item in sorted(state["results"].items(), key=lambda pair: (pair[0].split(":")[0], int(pair[0].split(":")[1]))):
        role, index = key.split(":")
        index = int(index)
        assert role in ("base", "full32") and 1 <= index <= 199
        row = item["row"]
        sample = samples[index-1]
        assert row["id"] == sample["id"] and row["benchmark"] == sample["benchmark"]
        assert row["sample_sha256"] == sha(encoded(sample))
        prediction = row["prediction"]
        score = row["official_score"]
        assert type(score["correct"]) is bool
        rows.append({"variant": role, "case_index": index, "id_sha256": sha(sample["id"].encode()), "sample_sha256": sha(encoded(sample)), "benchmark": sample["benchmark"], "stored_official_score": {"correct": score["correct"], "score": score["score"]}, "prediction_sha256": sha(encoded(prediction)), "stored_generation_error_present": bool(prediction.get("error")), "diagnostics": {view: diagnose_calls(prediction.get("tool_calls"), cs) for view, cs in contracts[index].items()}})
    by_role = {role: [r for r in rows if r["variant"] == role] for role in ("base", "full32", "mixed32")}
    assert [len(by_role[r]) for r in ("base", "full32", "mixed32")] == [199, 83, 0]
    matched = sorted(set(r["case_index"] for r in by_role["base"]) & set(r["case_index"] for r in by_role["full32"]))
    assert matched == list(range(1, 84))
    paired = {"case_count": len(matched), "selection": "Interrupted prefix 1..83, not random; descriptive only; no full199 Full or Mixed claim", "views": {}}
    for view in ("raw", "upstream_fc_projection"):
        counts = Counter()
        for index in matched:
            pair = {role: next(r for r in by_role[role] if r["case_index"] == index) for role in ("base", "full32")}
            valid = {role: pair[role]["diagnostics"][view]["status"] == "all_calls_schema_valid" for role in pair}
            counts[("base_valid" if valid["base"] else "base_not_valid")+"/"+("full_valid" if valid["full32"] else "full_not_valid")] += 1
        paired["views"][view] = dict(sorted(counts.items()))
    summary = {"scope": protocol["scope"], "protocol_sha256": sha(protocol_raw), "upstream_extracted_function_sha256": function_hashes, "versions": versions, "input_tools": sum(s["tool_count"] for s in inventory), "inventory_views": {}, "all_known_by_variant": {role: aggregate(part) for role, part in by_role.items()}, "matched_prefix_by_variant": {role: aggregate([r for r in by_role[role] if r["case_index"] in matched]) for role in ("base", "full32")}, "paired": paired, "by_benchmark": {role: {benchmark: aggregate([r for r in part if r["benchmark"] == benchmark]) for benchmark in sorted({r["benchmark"] for r in part})} for role, part in by_role.items()}}
    for view in ("raw", "upstream_fc_projection"):
        c = Counter()
        for item in inventory:
            c.update(item["views"][view]["schema_statuses"])
        summary["inventory_views"][view] = dict(sorted(c.items()))
    assert summary["input_tools"] == 879
    assert summary["all_known_by_variant"]["base"]["stored_official_correct"] == 118
    assert sha(args.ledger.read_bytes()) == protocol["ledger_sha256"]
    for rel, expected in protocol["upstream_source_sha256"].items():
        assert sha((root/rel).read_bytes()) == expected
    args.output.mkdir(exist_ok=False)
    (args.output/"summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n")
    for name, values in [("case-diagnostics.jsonl", rows), ("schema-inventory.jsonl", inventory)]:
        (args.output/name).write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True)+"\n" for r in values))
    receipt = {"protocol_sha256": sha(protocol_raw), "ledger_before_sha256": sha(state_raw), "ledger_after_sha256": sha(args.ledger.read_bytes()), "input_and_source_unchanged": True, "attempts": 284, "known_results": 282, "unknown_attempts": 2, "new_neural_calls": 0, "official_scorer_calls": 0, "raw_output_parser_calls": 0, "wall_seconds": round(time.monotonic()-started, 3), "output_sha256": {p.name: sha(p.read_bytes()) for p in sorted(args.output.iterdir())}}
    (args.output/"analysis-receipt.json").write_text(json.dumps(receipt, indent=2)+"\n")
    print(json.dumps({"receipt": receipt, "inventory_views": summary["inventory_views"], "all_known_by_variant": summary["all_known_by_variant"], "paired": paired}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for option in ("upstream", "ledger", "source", "protocol", "output"):
        parser.add_argument("--"+option, type=Path, required=True)
    run(parser.parse_args())
