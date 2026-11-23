# Fixed250 unscored generation study

CPU preflight ready; **no new model predictions or scores at this initial publication**. GPU generation is a separately frozen759attempt experiment,not a rerun of the old199 comparison.

- [CPU report](cpu/results/preflight-report.json), [immutable definition](cpu/results/definition.json), [8 controls](cpu/operator/CPU-controls.log), [input preparation log](cpu/operator/prepare-inputs.log), [CPU supervisor](cpu/operator/run-report.json), [cleanup](cpu/cleanup.json) and [16-payload manifest](cpu/export-manifest.json).
- All250 message/token fingerprints match the prior admission,maximum2,969prompt tokens. Preparation reads no references or model weights. The empty prospective journal was verified before exporting these initial CPU artifacts.
- [Frozen generation protocol](preregistered/protocol.json) and [operator/source manifest](preregistered/manifest.json): three fixed models,250cases each,759/253/2 attempt limits,125NEWcase cooperative segments,greedy42/output1536/soft90seconds,same freshly admitted GPU,resource guards,immutable failures and charged unknowns.
- Four published implementation/test files match CPU-preflighted bytes. The existing GenerationProgress implementation is unchanged; new integration controls are not neural results.

Raw questions,prompts,token vectors,reference answers,model responses and weights remain private. Exact checkpoint identities and request hashes are bound before generation. No online scoring,checkpoint selection,prompt conversion or quality retry. Operator paths are normalized where specified; original/public hashes are distinct. See [scope and metric limits](../../docs/bfcl-transfer-generation.md).


Offline scoring aggregation is frozen separately under `scoring-controls/`: six Linux-server controls pass, eight payload hashes verified, and both new source files match server bytes. No model outputs or scoring feedback were read for these controls. At the controls publication, generation was still in progress and no outputs had been scored. Completion and actual results follow below.


## Completed model generation and offline scoring

All750 fixed results committed before any scoring; all six model supervisors terminal/clean. See [GPU accounting](gpu/results/accounting.json), [token/EOS metadata](gpu/results/generation-cost.json), [offline score report](scoring/results/report.json), [case flags](scoring/results/case-flags.jsonl), and both new export manifests. Four neural/input source files match server bytes; two scoring aggregation sources remain identical to the published six-control preflight. No raw responses, question bodies, token vectors, reference values or weights are exported. The original CPU artifacts remain initial pre-generation evidence.

| 模型 | 工具题200 | irrelevance50 | 等额分层250，仅诊断 |
| --- | ---: | ---: | ---: |
| base | 147/200（73.5%） | 35/50（70.0%） | 182/250（72.8%） |
| reference32 | 150/200（75.0%） | 34/50（68.0%） | 184/250（73.6%） |
| masked32 | 153/200（76.5%） | 34/50（68.0%） | 187/250（74.8%） |

Reference32→Masked32主比较：只Masked正确6题，只Reference正确3题；差值+1.5个百分点，配对精确双侧McNemar p=0.5078125。这是本固定子集的配对描述，不外推总体或跨种子稳定性。当前小预算、单种子结果不足以证明稳定方法收益。

Publication receipts: [before first neural call](pre-first-model-publication.json), [scoring source before first score](pre-score-publication.json), [all model workers terminal before scoring](all-models-terminal-before-scoring.json). All irrelevance credits here arise from decoder failures; explicit empty call lists are zero for all three roles.
