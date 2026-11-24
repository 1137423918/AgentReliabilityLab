# Dependency review: PrefectHQ/fastmcp

Snapshot: `v2.12.4` / `b96e6ebbb269a241801554383671ba9f2876901e`

**Status: scoped_tests_passed**

Target: authlib — ['authlib@1.6.1'] → ['authlib@1.9.10']

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

Remaining affected registry resolutions: **16**.

Compatibility evidence: **passed_recorded_scope**.

Same 279 test identities in baseline and candidate; Historical FastMCP2.12.4 upstream auth/client-auth/HTTP-auth selection; same279cases, not full repository CI or production approval.

Baseline: {'tests': 279, 'failures': 0, 'errors': 0, 'skipped': 0}; candidate: {'tests': 279, 'failures': 0, 'errors': 0, 'skipped': 0}.

Next action: Review residual advisories and broader CI before a release decision.

Source: [fastmcp_2_12_4](https://raw.githubusercontent.com/1137423918/AgentReliabilityLab/2323416f27bccfe22b8d419562af11128059f75b/evidence/dependency-upgrade/corpus/fastmcp_2_12_4.json)
Report SHA256: `f9c57052b1bbf0370183c132b45eefe682fb19b528c724b4223fe4c53f4b0b5a`

Historical locked-resolution evidence, including optional/development dependencies; advisory matches are not proof of exploitability. This workflow does not rescan current dependencies, run the recorded upstream tests, call a model, or approve deployment.
