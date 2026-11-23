# Review follow-up: late cloud creation cleanup

Formal [Browser Use #6521](https://github.com/browser-use/browser-use/pull/6521), source `a4473544a95100b2b750cdf28e0b7f121be9c46e`. [Current native Actions and review snapshot](pr-state.json), timestamp `2026-11-23T18:29:00.196462+00:00`. No human approval or merge is claimed.

The first review found a valid lifecycle edge: the synchronous stop now retains the creation key for the normal asynchronous stop's final downloads, but a timed-out create finishes through `_stop_late`, which has no download pass. Clear the captured key there after a successful stop. A failed stop keeps its key and live registration for retry. This is an additional cleanup fix within the same download PR.

One parameterized regression models delayed creation with a pending Future and an expired deadline, then explicitly completes that Future. It exercises the actual registered completion callback, actual request/key construction, a model change, immediate successful stop and failed stop followed by successful retry. External HTTP responses and retry sleep are stubbed; no real network timing, paid model, real cloud browser or Chrome is claimed. The same final test bytes fail both cases on the **initial PR commit** `c881c18c60e95d3ef7393cab2b13bf48690cf2e9` and pass both on the final candidate. That is a different baseline from the original download regression's upstream `753d629`; they must not be combined into one baseline score. [Red](logs/baseline-review-regression.log), [green](logs/candidate-review-regression.log), [exact production source](tested-source/candidate/browser_use/browser/browser.py), [tests](tested-source/candidate/tests/ci/test_login.py).

| Linux CPU server check | Result |
| --- | --- |
| New late-stop regression, same 2 cases | initial PR: 2 fail; final: 2 pass |
| Login and browser neighbors, including all original 3 and new 2 cases | 162 passed in 42.00s |
| Complete non-Chrome selection | 969 passed, 3 skipped, 140 deselected, 1 warning in 371.01s (0:06:11) |
| Required pre-commit hooks and project-locked Ruff check/format | pass |
| Project-locked Pyright with repository configuration | pass |

Counts overlap. Skipped/deselected cases do not count as passes. These are deterministic framework checks, not model performance or production cloud validation. The unchanged SDK/lock and new private owned0700 `BH_HOME` are retained; no security checks or system HOME directories are changed. [Final controller](operator/run-report.json), [frozen lock](uv.lock), [cleanup](cleanup.json).

An earlier review-validation profile stopped before regression tests because the controller additionally passed test paths directly to Pyright, beyond the repository's configured scope. It reported 2 existing errors at `test_login.py:551` and `test_login.py:580`; they are retained in [v6](extra-scope-v6/project-pyright.log) and independently reproduced on unchanged review-baseline production source with the exact same test bytes in [control](logs/baseline-extra-test-pyright.log). The official configured check then passed. No type suppressions or unrelated source fixes were added. A never-executed intermediate controller preparation was replaced before launch; no experiment outcomes were modified. All server processes are terminal, with zero owned processes left and no GPU or model use.

The first PR commit's native lint/package/docker/test workflows all passed, including Windows/macOS/Linux and Chrome: [timestamped prior snapshot](prior-native-CI-state.json). Those successes are not silently attributed to the new commit. The final commit's native lint, package, Docker and test workflows all passed, including all six Python/platform matrix jobs and Chrome. The same timestamped snapshot reports zero unresolved review threads and a successful Cubic check; this is not human approval. The earlier in-progress state is retained in [the first-publication snapshot](pr-state-at-first-publication.json). No author reply or manual resolution was sent. The repository's CLA assistant also asks the human contributor to sign its agreement; no legal acceptance is performed by the agent.

[Machine-readable result](report.json), [export original/public hashes](export-manifest.json). The [original evidence](../README.md), original preparation failures, original download regressions and 967-pass run are preserved. Original source is covered by the upstream [MIT license](../upstream-LICENSE.txt).
