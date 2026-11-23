# Matched fixed-reason loss-mask study

**Both GPU arms completed32updates/1,333logical forwards and all final checks; controller exit0,owned processes0,ownGPUcontext absent.** Historical failed Full training and old generation/accounting remain unchanged. New generation evaluation has not been allocated or run.

CPU controls and the GPU protocol were first published at `e271b338633809cfcc772e2cc11885bd7c52624e`, before starting this model run. The initial preregistration remains unchanged; the GPU results below were added after terminal success.

[Verified result summary](result-summary.json) combines the terminal counts and NLL; it and the checkpoint archive receipt are separate metadata artifacts outside the original export manifests.

- [CPU schedule audit](cpu/results/plan-audit.json): identical3,700 input rows/order; Full32 reference65,536 vs masked54,187 active labels,774 segments/573,843 input exposures each,zero empty segments.
- [CPU controller record](cpu/operator/run-report.json), [6 numerical controls](cpu/operator/CPU-numerics.log), [schedule log](cpu/operator/schedule-audit.log), [runtime identity](cpu/operator/runtime-identity.log), [CPU protocol](cpu/operator/protocol.json) and [cleanup](cpu/cleanup.json).
- [CPU export manifest](cpu/export-manifest.json) binds all14 payloads. Three published Python files match these server-tested/preflighted source bytes; the training entry itself still requires real GPU canaries and end-to-end validation. CPU tests cover target selection/loss/gradient semantics and actual data scheduling, not 3B training.
- [Frozen GPU protocol](preregistered/protocol.json): separate matched experiment,1,333 forward reservations/32updates per arm,zero generation allocation,initial parameter fingerprints,real-model canaries/final reload,resource guards and retained unknown charges.
- [GPU operator source and provenance](preregistered/manifest.json). Operator paths are normalized where specified; original/public hashes are distinct. Source/runtime guards reused from prior verified runs do not make this new GPU study passed before execution.
- [GPU controller](gpu/operator/training-report.json), [Reference report](gpu/reference/report.json), [Masked report](gpu/masked/report.json), [Reference journal](gpu/reference/events.jsonl), [Masked journal](gpu/masked/events.jsonl), [cleanup](gpu/cleanup.json) and [40-payload export manifest](gpu/export-manifest.json). Each journal records1,333reserved/completed forwards,774completed backward segments,32reserved/completed updates,4checkpoint commits,zero unknowns andzero malformed lines.
- Per-case before/after dev/validation NLL files are included in each arm folder. Case order,counts,target-token totals and weighted sums were independently checked. Unmasked validation NLL is0.297588 forReference and0.671653 forMasked; this is not generated tool-call accuracy.
- [Stable private checkpoint archive receipt](checkpoint-archive-receipt.json): both final checkpoints copied and every file verified,private tensor/optimizer/RNG bodies excluded. This receipt is a separate metadata artifact,not one of the40 GPU-export payloads.

Both arms share initial adapter/frozen-parameter fingerprints. Final adapter parameter fingerprints: Reference `32d58200e02f4d53035c1b123b0b68df0d0e028272265d2f4666cef3b25d1424`; Masked `0a89d8fe7dae49a9ad574bc803eed69b8a0fbc79d102b46e2f48b8073a68e461`. Each matches its own reloaded checkpoint. This does not repair the historical Full run or imply cross-run bitwise training reproducibility.

Neither the CUDA training controller nor the Python entry alone is a scheduler reservation or hostile-code sandbox. The training entry rejects a CPU-preflight protocol. Checkpoints,optimizer states,token vectors,targets,new evaluation answers and credentials remain private. No automatic retry/resume,checkpoint selection,quality retry or changes to old199 outcomes/caps.

See [method and current status](../../docs/fixed-reason-ablation.md). Fixed32 reference/mask groups preserve full inputs and differ in supervision; effective labels and vocabulary projection cost differ. Teacher-forced NLL is not generated tool-call accuracy.
