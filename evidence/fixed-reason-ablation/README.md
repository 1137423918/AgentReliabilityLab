# Matched fixed-reason loss-mask study

CPU preflight completed; GPU training protocol declared separately. **No GPU training or generation results are included in this initial evidence publication.** Historical failed Full training and old generation/accounting remain unchanged.

- [CPU schedule audit](cpu/results/plan-audit.json): identical3,700 input rows/order; Full32 reference65,536 vs masked54,187 active labels,774 segments/573,843 input exposures each,zero empty segments.
- [CPU controller record](cpu/operator/run-report.json), [6 numerical controls](cpu/operator/CPU-numerics.log), [schedule log](cpu/operator/schedule-audit.log), [runtime identity](cpu/operator/runtime-identity.log), [CPU protocol](cpu/operator/protocol.json) and [cleanup](cpu/cleanup.json).
- [CPU export manifest](cpu/export-manifest.json) binds all14 payloads. Three published Python files match these server-tested/preflighted source bytes; the training entry itself still requires real GPU canaries and end-to-end validation. CPU tests cover target selection/loss/gradient semantics and actual data scheduling, not 3B training.
- [Frozen GPU protocol](preregistered/protocol.json): separate matched experiment,1,333 forward reservations/32updates per arm,zero generation allocation,initial parameter fingerprints,real-model canaries/final reload,resource guards and retained unknown charges.
- [GPU operator source and provenance](preregistered/manifest.json). Operator paths are normalized where specified; original/public hashes are distinct. Source/runtime guards reused from prior verified runs do not make this new GPU study passed before execution.

Neither the CUDA training controller nor the Python entry alone is a scheduler reservation or hostile-code sandbox. The training entry rejects a CPU-preflight protocol. Checkpoints,optimizer states,token vectors,targets,new evaluation answers and credentials remain private. No automatic retry/resume,checkpoint selection,quality retry or changes to old199 outcomes/caps.

See [method and current status](../../docs/fixed-reason-ablation.md). Fixed32 reference/mask groups preserve full inputs and differ in supervision; effective labels and vocabulary projection cost differ. Teacher-forced NLL is not generated tool-call accuracy.
