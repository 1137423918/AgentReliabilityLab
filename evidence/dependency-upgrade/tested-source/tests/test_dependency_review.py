"""Upgrade-review failure controls, without invoking network/package managers."""

import unittest

from agent_lab.dependency_review import (
    choose_target,
    compare_candidate,
    inventory,
    scanner_findings,
)


def locked(versions):
    return inventory(
        {
            "package": [
                {
                    "name": name,
                    "version": version,
                    "source": {"registry": "https://pypi.org/simple"},
                }
                for name, version in versions
            ]
        },
        {
            "project": {
                "name": "sample",
                "dependencies": ['direct>=1; python_version >= "3.11"'],
                "optional-dependencies": {"web": ["optional>=1"]},
            },
            "dependency-groups": {"dev": ["dev>=1", {"include-group": "checks"}]},
        },
    )


def scanner(versions, findings):
    return {
        "results": [
            {
                "source": {"type": "lockfile", "path": "uv.lock"},
                "packages": [
                    {
                        "package": {
                            "name": name,
                            "version": version,
                            "ecosystem": "PyPI",
                        },
                        "vulnerabilities": [{"id": v} for v in findings.get(name, [])],
                        "groups": [{"ids": [v]} for v in findings.get(name, [])],
                    }
                    for name, version in versions
                ],
            }
        ]
    }


class DependencyReviewTests(unittest.TestCase):
    def test_all_resolutions_and_conditional_direct_requirement_are_retained(self):
        result = locked(
            [("Direct", "1"), ("direct", "2"), ("optional", "1"), ("dev", "1")]
        )
        self.assertEqual(len(result["packages"]), 4)
        self.assertEqual(
            result["packages"]["direct@1"]["declarations"][0]["requirement"],
            'direct>=1; python_version >= "3.11"',
        )
        self.assertEqual(
            result["packages"]["optional@1"]["declarations"][0]["group"], "extra:web"
        )
        self.assertEqual(
            result["packages"]["dev@1"]["declarations"][0]["group"], "group:dev"
        )

    def test_editable_root_is_reported_separately_from_registry_dependencies(self):
        for locked_version, scanned_version in [("1", "1"), (None, "")]:
            with self.subTest(
                locked_version=locked_version, scanned_version=scanned_version
            ):
                versions = [("direct", "1")]
                catalog = locked(versions)
                catalog["nonregistry_entries"].append(
                    {
                        "name": "sample",
                        "version": locked_version,
                        "source": {"editable": "."},
                    }
                )
                result = scanner_findings(
                    scanner(
                        versions + [("sample", scanned_version)],
                        {"sample": ["ROOT-ID"]},
                    ),
                    catalog,
                )
                self.assertTrue(result["registry_coverage_complete"])
                self.assertEqual(result["affected_resolutions"], 0)
                self.assertEqual(
                    result["nonregistry_scanner_records"][0]["scanner_advisory_ids"],
                    ["ROOT-ID"],
                )
                self.assertFalse(
                    result["nonregistry_scanner_records"][0]["source_bytes_audited"]
                )

    def test_missing_scanner_packages_prevents_target_selection(self):
        versions = [("direct", "1"), ("transitive", "1")]
        result = scanner_findings(
            scanner(versions[:1], {"direct": ["GHSA-example"]}), locked(versions)
        )
        self.assertEqual(result["missing_registry_resolutions"], ["transitive@1"])
        self.assertFalse(result["registry_coverage_complete"])
        self.assertIsNone(choose_target(result))

    def test_empty_or_malformed_scan_is_not_a_clean_bill(self):
        for document in [{}, {"results": None}, {"results": [{"packages": None}]}]:
            with self.subTest(document=document), self.assertRaises(ValueError):
                scanner_findings(document, locked([("direct", "1")]))
        empty = scanner_findings({"results": []}, locked([("direct", "1")]))
        self.assertFalse(empty["registry_coverage_complete"])
        self.assertFalse(empty["deployment_or_reachability_verified"])

    def test_foreign_packages_and_unaccounted_advisories_are_rejected(self):
        versions = [("direct", "1")]
        foreign = scanner([("foreign", "1")], {})
        omitted = scanner(versions, {"direct": ["GHSA-example"]})
        omitted["results"][0]["packages"][0]["groups"] = []
        for document in [foreign, omitted]:
            with self.subTest(document=document), self.assertRaises(ValueError):
                scanner_findings(document, locked(versions))

    def test_fixed_target_policy_prefers_declarations_over_larger_transitive_group(
        self,
    ):
        versions = [("direct", "1"), ("transitive", "1")]
        result = scanner_findings(
            scanner(versions, {"direct": ["A"], "transitive": ["B", "C"]}),
            locked(versions),
        )
        self.assertEqual(choose_target(result), "direct@1")

    def compare(self, before_versions, after_versions, before_findings, after_findings):
        a, b = locked(before_versions), locked(after_versions)
        before = scanner_findings(scanner(before_versions, before_findings), a)
        after = scanner_findings(scanner(after_versions, after_findings), b)
        return compare_candidate(before, after, "direct", a, b)

    def test_target_fix_does_not_imply_all_dependencies_or_release_are_ready(self):
        result = self.compare(
            [("direct", "1"), ("other", "1")],
            [("direct", "2"), ("other", "1")],
            {"direct": ["A"], "other": ["B"]},
            {"other": ["B"]},
        )
        self.assertTrue(result["ready_for_integration_tests"])
        self.assertFalse(result["all_dependency_findings_cleared"])
        self.assertFalse(result["release_approved"])
        self.assertFalse(result["compatibility_tests_run"])

    def test_same_advisory_on_a_new_package_is_a_new_finding(self):
        result = self.compare(
            [("direct", "1"), ("other", "1")],
            [("direct", "2"), ("other", "2")],
            {"direct": ["A"]},
            {"other": ["A"]},
        )
        self.assertEqual(result["new_advisory_ids"], [])
        self.assertEqual(
            result["new_advisory_matches"], [{"package": "other", "advisory_id": "A"}]
        )
        self.assertFalse(result["ready_for_integration_tests"])

    def test_unchanged_target_cannot_be_reported_as_an_upgrade(self):
        result = self.compare(
            [("direct", "1")], [("direct", "1")], {"direct": ["A"]}, {}
        )
        self.assertFalse(result["target_version_changed"])
        self.assertFalse(result["ready_for_integration_tests"])


if __name__ == "__main__":
    unittest.main()
