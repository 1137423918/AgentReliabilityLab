# Dependency review: HKUDS/LightRAG

Snapshot: `v1.5.8` / `7169588d0a27f86d30e5de48c60301a899e61b93`

**Status: scoped_tests_passed**

Target: ragas — ['ragas@0.4.3'] → ['ragas@0.4.4']

| Gate condition | Observed | Required | Matched |
| --- | --- | --- | --- |
| /execution/candidate_prepared | True | True | True |
| /resolution/exit_code | 0 | 0 | True |
| /resolution/original_requirements_changed | False | False | True |
| /coverage/before_registry_complete | True | True | True |
| /coverage/after_registry_complete | True | True | True |
| /target/version_changed | True | True | True |
| /target/remaining_advisory_match_count | 0 | 0 | True |
| /delta/new_package_advisory_match_count | 0 | 0 | True |

Remaining affected registry resolutions: **17**.

Compatibility evidence: **passed_recorded_scope**.

Same 21 test identities in baseline and candidate; Upstream tests/evaluation -m offline,Python3.11;realRAGAS0.4.3/0.4.4imports;upstreamtests mockjudge outputs,noLMqualityclaim. NotfullCI(Python3.12native).

Baseline: {'tests': 21, 'failures': 0, 'errors': 0, 'skipped': 0}; candidate: {'tests': 21, 'failures': 0, 'errors': 0, 'skipped': 0}.

Next action: Review residual advisories and broader CI before a release decision.

Source: [lightrag_1_5_8](https://raw.githubusercontent.com/1137423918/AgentReliabilityLab/8834ce4d1bc9be9a81201478d36b5289044a117e/evidence/lightrag-dependency-upgrade/corpus/lightrag_1_5_8.json)
Report SHA256: `9df0511eb10480f3f76fe45375584f6ac610b6275dfef16374473fdffdfdda65`

Historical locked-resolution evidence, including optional/development dependencies; advisory matches are not proof of exploitability. This workflow does not rescan current dependencies, run the recorded upstream tests, call a model, or approve deployment.
