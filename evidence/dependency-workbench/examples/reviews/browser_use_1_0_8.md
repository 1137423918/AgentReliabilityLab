# Dependency review: browser-use/browser-use

Snapshot: `1.0.8` / `753d629d76eb2b670f4cf467f3355bbe750f6845`

**Status: blocked**

Target: pillow — ['pillow@12.3.0'] → ['pillow@12.3.0']

| Gate condition | Observed | Required | Matched |
| --- | --- | --- | --- |
| /execution/candidate_prepared | True | True | True |
| /resolution/exit_code | 0 | 0 | True |
| /resolution/original_requirements_changed | False | False | True |
| /coverage/before_registry_complete | True | True | True |
| /coverage/after_registry_complete | True | True | True |
| /target/version_changed | False | True | False |
| /target/remaining_advisory_match_count | 62 | 0 | False |
| /delta/new_package_advisory_match_count | 0 | 0 | True |

Remaining affected registry resolutions: **2**.

Compatibility evidence: **not_recorded**.

Next action: Resolve the failed upgrade conditions before integration testing.

Source: [browser_use_1_0_8](https://raw.githubusercontent.com/1137423918/AgentReliabilityLab/2323416f27bccfe22b8d419562af11128059f75b/evidence/dependency-upgrade/corpus/browser_use_1_0_8.json)
Report SHA256: `b307542f7839db871e6f5d7e4e1c09e72889a4219ecc8752621328fff920d9e4`

Historical locked-resolution evidence, including optional/development dependencies; advisory matches are not proof of exploitability. This workflow does not rescan current dependencies, run the recorded upstream tests, call a model, or approve deployment.
