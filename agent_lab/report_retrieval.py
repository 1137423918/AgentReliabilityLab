"""Rank report *metadata* without reading evidence, gold answers or file paths.

BM25 is a lexical baseline, not semantic verification. A selected report still
requires a normal MCP read receipt. The caller can always request the full
catalog; a zero-match search never manufactures evidence or fills with guesses.
"""

from collections import Counter
import json
import math
import re


STOP_WORDS = frozenset(
    "a an and are as at be been by can did do does for from has have how i in is "
    "it its of on or our that the their these this to was were what when which "
    "with would you your against about into only not than then there those".split()
)


def terms(text):
    """Split camel/snake identifiers and ordinary English without stemming."""
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    text = re.sub(r"([A-Z])([A-Z][a-z])", r"\1 \2", text)
    return [
        token
        for token in re.findall(r"[^\W_]+", text.casefold(), re.UNICODE)
        if token not in STOP_WORDS
    ]


def encoded(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def rank_reports(catalog, query, *, policy="bm25", max_reports=4, max_bytes=4096):
    """Return whole catalog entries under a serialized UTF-8 response budget.

    ID, description and advertised pointer names are the *only* indexed text.
    Standard BM25 uses k1=1.2/b=0.75, with each unique query term counted once.
    The overlap baseline counts the same unique terms with no IDF/length weight.
    Ties use the stable report ID, not the manifest order. No corpus-specific
    weights, labels, answer values, model calls or hidden file access are used.
    """
    if policy not in {"bm25", "overlap"}:
        raise ValueError("Unknown report ranking policy")
    if not isinstance(query, str) or not 1 <= len(query) <= 4096:
        raise ValueError("Query must contain1 to4096 characters")
    if type(max_reports) is not int or not 1 <= max_reports <= 32:
        raise ValueError("Choose1 to32 report results")
    if type(max_bytes) is not int or not 512 <= max_bytes <= 8192:
        raise ValueError("Choose512 to8192 serialized result bytes")
    reports = catalog["reports"]
    if not isinstance(reports, list) or not 1 <= len(reports) <= 32:
        raise ValueError("Expected a bounded report metadata list")
    ids = set()
    counters = []
    for row in reports:
        if (
            set(row) != {"id", "description", "fields"}
            or not isinstance(row["id"], str)
            or row["id"] in ids
            or not isinstance(row["description"], str)
            or not isinstance(row["fields"], list)
            or any(not isinstance(f, str) for f in row["fields"])
        ):
            raise ValueError("Expected distinct report metadata, not evidence values")
        ids.add(row["id"])
        counters.append(
            Counter(terms(" ".join([row["id"], row["description"], *row["fields"]])))
        )
    query_terms = set(terms(query))
    df = Counter(term for counts in counters for term in counts)
    lengths = [sum(c.values()) for c in counters]
    average = sum(lengths) / len(lengths)
    ranked = []
    for row, counts, length in zip(reports, counters, lengths):
        matches = sorted(query_terms & counts.keys())
        score = float(len(matches))
        if policy == "bm25":
            score = (
                sum(
                    math.log(1 + (len(reports) - df[t] + 0.5) / (df[t] + 0.5))
                    * counts[t]
                    * 2.2
                    / (counts[t] + 1.2 * (0.25 + 0.75 * length / average))
                    for t in matches
                )
                if average
                else 0.0
            )
        if score > 0:
            ranked.append((score, row["id"], row, matches))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    response = {
        "snapshot": catalog["snapshot"],
        "reports": [],
        "search": {
            "policy": policy,
            "matched_reports": len(ranked),
            "catalog_reports": len(reports),
            "returned_reports": 0,
            "omitted_for_bytes": 0,
            "ranking": [],
            "metadata_is_evidence": False,
            "full_catalog_query": "*",
        },
    }
    for score, report_id, row, matches in ranked:
        if len(response["reports"]) >= max_reports:
            break
        candidate = {
            **response,
            "reports": [*response["reports"], row],
            "search": {
                **response["search"],
                "returned_reports": len(response["reports"]) + 1,
                "ranking": [
                    *response["search"]["ranking"],
                    {
                        "id": report_id,
                        "score": round(score, 6),
                        "matched_terms": matches,
                    },
                ],
            },
        }
        if len(encoded(candidate).encode()) > max_bytes:
            response["search"]["omitted_for_bytes"] += 1
            continue
        response = candidate
    # Updating a counter can add a digit after a previously exact-fit result.
    while len(encoded(response).encode()) > max_bytes and response["reports"]:
        response["reports"].pop()
        response["search"]["ranking"].pop()
        response["search"]["returned_reports"] -= 1
        response["search"]["omitted_for_bytes"] += 1
    if len(encoded(response).encode()) > max_bytes:
        raise ValueError("Search metadata alone exceeds response budget")
    return response
