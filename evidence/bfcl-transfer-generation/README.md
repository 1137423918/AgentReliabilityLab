# Fixed250 unscored generation study

CPU preflight ready; **no new model predictions or scores at this initial publication**. GPU generation is a separately frozen759attempt experiment,not a rerun of the old199 comparison.

- [CPU report](cpu/results/preflight-report.json), [immutable definition](cpu/results/definition.json), [8 controls](cpu/operator/CPU-controls.log), [input preparation log](cpu/operator/prepare-inputs.log), [CPU supervisor](cpu/operator/run-report.json), [cleanup](cpu/cleanup.json) and [16-payload manifest](cpu/export-manifest.json).
- All250 message/token fingerprints match the prior admission,maximum2,969prompt tokens. Preparation reads no references or model weights. The empty prospective journal was verified before exporting these initial CPU artifacts.
- [Frozen generation protocol](preregistered/protocol.json) and [operator/source manifest](preregistered/manifest.json): three fixed models,250cases each,759/253/2 attempt limits,125NEWcase cooperative segments,greedy42/output1536/soft90seconds,same freshly admitted GPU,resource guards,immutable failures and charged unknowns.
- Four published implementation/test files match CPU-preflighted bytes. The existing GenerationProgress implementation is unchanged; new integration controls are not neural results.

Raw questions,prompts,token vectors,reference answers,model responses and weights remain private. Exact checkpoint identities and request hashes are bound before generation. No online scoring,checkpoint selection,prompt conversion or quality retry. Operator paths are normalized where specified; original/public hashes are distinct. See [scope and metric limits](../../docs/bfcl-transfer-generation.md).


Offline scoring aggregation is frozen separately under `scoring-controls/`: six Linux-server controls pass, eight payload hashes verified, and both new source files match server bytes. No model outputs or scoring feedback were read for these controls. The actual three-role generation is in progress; all750 outputs must be committed before offline scoring.
