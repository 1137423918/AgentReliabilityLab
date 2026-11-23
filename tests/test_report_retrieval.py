"""Report selection controls; real application diagnostics live in benchmarks."""

import copy
import unittest

from agent_lab.report_retrieval import encoded, rank_reports, terms


def catalog(*rows):
    return {"snapshot": "a" * 40, "reports": list(rows)}


def row(report_id, description, fields=None):
    return {"id": report_id, "description": description, "fields": fields or ["/state"]}


class ReportRetrievalTests(unittest.TestCase):
    def test_identifier_tokens_and_repeated_query_terms(self):
        self.assertEqual(
            terms("MCPServer same_path Full32"),
            ["mcp", "server", "same", "path", "full32"],
        )
        c = catalog(row("x", "MCP server"), row("y", "different report"))
        self.assertEqual(rank_reports(c, "MCP"), rank_reports(c, "MCP MCP MCP"))

    def test_idf_changes_ranking_against_overlap_baseline(self):
        c = catalog(
            row("a", "common common common shared"),
            row("b", "rare"),
            row("c", "common shared"),
            row("d", "common shared"),
            row("e", "common shared"),
        )
        self.assertEqual(
            rank_reports(c, "common shared rare", policy="overlap")["reports"][0]["id"],
            "a",
        )
        self.assertEqual(rank_reports(c, "common shared rare")["reports"][0]["id"], "b")

    def test_ties_are_stable_across_manifest_order(self):
        a, b = row("a", "same"), row("b", "same")
        self.assertEqual(
            rank_reports(catalog(b, a), "same"), rank_reports(catalog(a, b), "same")
        )

    def test_zero_match_never_fills_with_unrelated_reports(self):
        value = rank_reports(catalog(row("a", "different")), "unknown")
        self.assertEqual(value["reports"], [])
        self.assertEqual(value["search"]["matched_reports"], 0)
        self.assertEqual(value["search"]["full_catalog_query"], "*")

    def test_whole_rows_and_multibyte_byte_bound(self):
        c = catalog(
            *(row("r" + str(i), "target " + "证据" * i * 20) for i in range(1, 20))
        )
        for cap in [512, 768, 1024, 2048, 4096]:
            value = rank_reports(c, "target", max_reports=32, max_bytes=cap)
            self.assertLessEqual(len(encoded(value).encode()), cap)
            self.assertEqual(value["search"]["returned_reports"], len(value["reports"]))
            self.assertTrue(all(r in c["reports"] for r in value["reports"]))

    def test_does_not_read_files_use_answers_or_mutate_metadata(self):
        c = catalog(row("report", "deletion", ["/failed", "/passed"]))
        original = copy.deepcopy(c)
        value = rank_reports(c, "deletion")
        self.assertEqual(c, original)
        self.assertEqual(value["reports"], original["reports"])
        self.assertFalse(value["search"]["metadata_is_evidence"])
        with self.assertRaises(ValueError):
            rank_reports(
                catalog({**c["reports"][0], "values": {"/failed": 3}}), "deletion"
            )

    def test_invalid_queries_bounds_and_duplicate_ids(self):
        c = catalog(row("report", "deletion"))
        for kwargs in [
            {"max_reports": True},
            {"max_reports": 33},
            {"max_bytes": 511},
            {"policy": "unknown"},
        ]:
            with self.assertRaises(ValueError):
                rank_reports(c, "deletion", **kwargs)
        for query in [None, "", "x" * 4097]:
            with self.assertRaises(ValueError):
                rank_reports(c, query)
        with self.assertRaises(ValueError):
            rank_reports(catalog(*c["reports"], *c["reports"]), "deletion")


if __name__ == "__main__":
    unittest.main()
