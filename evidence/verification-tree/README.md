# Verification descendants: reproduce, bind, reap

A verification command could spawn a new-session child, exit successfully, and leave that child running. Original source408cd3ab reproduced this on the authorized Linux server; the probe was stopped. The new direct process-boundary checks both fail on the original supervisor.

The isolated Linux supervisor now uses PR_SET_CHILD_SUBREAPER before launching the command. Orphaned descendants, including double-forked children and new sessions, become its children. After the leader terminates it kills and reaps only its unreaped direct children, repeating as more descendants are adopted. The supervisor keeps the worker lock until cleanup completes. This does not depend on pidfd bindings or signal arbitrary PIDs from a system-wide snapshot.

A first candidate passed its two direct checks but failed three worker integration checks. Worker intentionally removes PYTHONPATH from the verification environment; python -m then resolved an older installed supervisor. The final worker starts the absolute verification.py file already loaded by itself. Verification commands still receive the filtered environment. Initial failure logs and candidate sources remain under attempt-1/.

## Server validation

- Original baseline: two new checks fail, as expected.
- Final focused group:5 pass, including strengthened existing timeout, worker SIGKILL/resume and normal leader-exit checks with new-session children.
- Complete suite:108 pass, zero skipped; the focused group and two new tests are included, not added to that count. Unittest 319.701s, controller phase wall 322.778s.
- New checks cover double-fork adoption/reaping and preservation of an unrelated process during timeout cleanup. Test probe readiness is atomic and failure cleanup checks its unique argv marker.
- No neural model, GPU, new upstream acceptance or autonomous repair result. Raw controller model_requests=0 denotes no real neural/provider requests; fake model HTTP services are exercised by the suite and their traffic is not claimed to be zero. Existing reports and dated portfolio snapshot retain their historical counts.

Every execution used four CPU cores/nice19, private ext4 state and fixed source hashes. Sampled16GiB tree RSS/12GiB available-memory guards and600s phase limits did not trigger; no observed owned process remained after final phase cleanup. Sampling is observational, not a claim about every transient process or unique-memory use.

## Boundaries

Linux only for descendant adoption; other Unix retains the original process-group cleanup. Procfs/subreaper setup must succeed before launching a Linux verifier. This is lifecycle management, not a hostile-process sandbox. External service managers/namespaces and killing the supervisor itself are not covered. SIGKILL cannot immediately end uninterruptible kernel waits: cleanup may keep the lock while waiting rather than report premature completion. Those OS failure modes were not fault-injected.

[Linux subreaper semantics](https://man7.org/linux/man-pages/man2/PR_SET_CHILD_SUBREAPER.2const.html) · [waitpid child/reaping semantics](https://man7.org/linux/man-pages/man2/waitpid.2.html)

See protocol.json, report.json, reproduction.json, normal/ and attempt-1/ for exact source identities and normalized raw logs. Private root paths are replaced in public logs; original bytes and original/public SHA256 remain in manifests. No checkpoint databases or environment secrets are collected.
