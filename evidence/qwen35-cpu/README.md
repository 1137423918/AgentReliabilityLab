# Qwen3.5-9B protected maintenance CPU pilot

Two predeclared trials of **one public Deep Agents problem**. Both fail with the individual 180-second request timeout, not the 600-second case wall limit. No virtual changes, exported patch or official acceptance in either case. This is not a general repair rate or a causal comparison with the earlier 4B experiments.

| Case | Wall seconds | Persisted model replies / tool results | Outcome |
| --- | ---: | --- | --- |
| Normal | 185.324 | 0 / 0 | OpenAITimeoutError |
| Checkpoint-resume | 376.219 | 2 / 4 | OpenAITimeoutError |

The recovery worker was SIGKILLed after its first checkpoint (one model reply, two read_file results), then resumed to a second reply and two additional read_file results. All four reads are successful; no edit occurred. This observes read-state continuation, not edited-file recovery or completed maintenance.

The native service launched four requests: two completed replies and two cancellations. Normal prompt processing took 172.58 seconds for 2,442 tokens, leaving little of the 180-second client budget. The last request was observed processing 2,048 prompt tokens after 154.67 seconds before cancellation. Completed generation speeds are approximately four tokens/s on this shared four-thread CPU setup; sequential prompt caching precludes a controlled timing comparison. Full usage for cancelled responses is unavailable.

## Files and provenance

- [report.json](report.json): concise outcome, limits, source identities and cleanup.
- [pilot.json](pilot.json): original harness report (paths normalized only).
- [protocol.json](protocol.json), [prelaunch.json](prelaunch.json): declared before generation; protocol SHA `2d9460cb5cb6df17ebe03bb50ef5a61a799363605faaf5b353df4f105ef38890`.
- [native-manifest.json](native-manifest.json): fixed GGUF, template, unchanged official runtime and library identities. `weights_loaded_for_inference: false` describes this inspection step, not the subsequent service run.
- [audit/normal.json](audit/normal.json), [audit/checkpoint-resume.json](audit/checkpoint-resume.json): read-only hydrated final checkpoint summaries; no new generation, full conversations excluded.
- [logs/worker-tests.log](logs/worker-tests.log): 57 project checks, 43 passed / 14 skipped (jsonschema absent). Includes fake-HTTP sampling transport checks, not model success.
- [service/server.log](service/server.log), [service/shutdown.json](service/shutdown.json), [service/stopped.json](service/stopped.json): actual inference and shutdown. Identity-checked operator SIGTERM to launcher, then native child forcibly reaped after its 10-second grace period; child return -9, not a graceful exit. Both processes and listener are absent.
- [logs/inspection-initial.log](logs/inspection-initial.log): first inspection failed because the CLI library directory omitted `/lib`; corrected arguments passed before generation. No failed attempt was erased.
- [artifacts.json](artifacts.json): original/private and public text hashes for the explicit 27-file allowlist; absolute server paths and terminal formatting normalized. Generated summary/README/license are outside this transfer manifest.

Model: third-party `lmstudio-community/Qwen3.5-9B-GGUF` revision `1379f25c6b505a3fc737bd7818cb09389cf807c1`, Q4_K_M, 5,627,044,256 bytes, SHA `cd76ec205963b3b33350093e6904d9de16c4e666fd104e1f632d25c7f15f2a13`. The quantizer names the original Qwen model but not an exact source-weight revision. The fetched original card/config revision is reference metadata, not verified weight lineage. Metadata/model license: [Apache-2.0](metadata/source--LICENSE). Small upstream source previews in audit output retain [Deep Agents MIT](UPSTREAM_LICENSE).

[Full protocol and reproduction](../../docs/qwen35-maintenance.md). No GPU, reference patch, extra retry, extra repair round, or retrospective budget extension was used. Protected acceptance was configured identically to the previous task, but no neural candidate reached it. Historical failures remain unchanged.
