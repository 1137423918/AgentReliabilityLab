# Completed recovered clean199 model comparison

Fixed Qwen2.5-3B-Instruct revision and the previously saved Full32/Mixed32 adapters; same physical RTX3090, tokenizer,199 ordered cases, prompts, greedy generation, parser and official scoring. This stage performs no training or checkpoint selection. Original no-retry and recovery-v2 failures remain unchanged in [the earlier snapshot](../lora-generation/README.md).

| Variant | Official correct /199 | Official score sum | Reserved attempts | Unknown still charged |
| --- | ---: | ---: | ---: | ---: |
|base|118/199 (59.30%)|119.666667|199|0|
|full32|107/199 (53.77%)|107.000000|201|2|
|mixed32|105/199 (52.76%)|105.000000|199|0|

| Benchmark | Base correct | Full correct | Mixed correct | Cases each |
| --- | ---: | ---: | ---: | ---: |
|bfcl_v3|26|27|27|32|
|apibank|42|32|30|74|
|tooleyes|47|45|44|51|
|toolalpaca|1|2|2|21|
|rotbench|2|1|2|21|

| Variant | No parsed calls | Required-key violation cases | Non-EOS / soft stopped | Known output tokens |
| --- | ---: | ---: | ---: | ---: |
|base|23|3|3|21089|
|full32|34|3|0|11536|
|mixed32|39|3|2|13454|

All three variants now have199 stored scores;597 known results and599 reserved attempts. The two historical Full unknowns at sequences281/284 remain charged, including after their cases later complete. Frozen caps remain603total/201pervariant/3percase; Full uses201. No quality-based rerun/refund or automatic retry. Both later model processes ended normally, owned processes were absent and GPU contexts released.

| Paired comparison | Both correct | Candidate only | Reference only | Both incorrect | Net correct |
| --- | ---: | ---: | ---: | ---: | ---: |
|full32-vs-base|97|10|21|71|-11|
|mixed32-vs-base|93|12|25|69|-13|
|mixed32-vs-full32|100|5|7|87|-2|

Paired rows align ordinal, ID hash, input hash, benchmark and input-token count. Counts describe this fixed known clean set; no general-population significance claim. Official correct/score are compatibility-matching metrics, not full JSON Schema validity, actual tool execution or all22perturbations. The historical P100119/199 result is separate.

Fresh same-device admission and source/model/checkpoint identity checks preceded continuation. Only the terminal, cleaned resource-guard attempt284 was explicitly authorized; all282 known predecessor rows remained byte-equivalent. Full reused83 cached rows and added116; Mixed added199. The exporter only aggregates saved scores, never calls a model or reruns scoring. Earlier12 CPU controls and280 historical cache dispatches are reused evidence with unchanged relevant source, not new tests or independent neural successes.

Full/Mixed adapters each had32 optimizer updates and65536 supervised labels, but this does not equalize all input-token exposure or training compute. Full’s original final in-memory hash verification gap and independent saved-checkpoint replay/failed supervisor record remain disclosed. Clean generation completion does not repair that historical training attestation. No validation-loss-to-task-accuracy inference is made.

[Comparison](comparison.json), [paired cases](paired/), [base](base/case-metrics.jsonl), [Full](full32/case-metrics.jsonl), [Mixed](mixed32/case-metrics.jsonl), [charged attempts](attempt-metadata.json), [protocol and controllers](operator/), [cleanup](cleanup.json), [export hashes](export-manifest.json). Public metadata excludes full prompts/answers/output text/token vectors/weights/process identities/private paths. Raw outputs remain on the server; hashes support lineage and aggregation checks, not independent rescoring of withheld output. Existing24-report model-task corpus stays frozen. Homepage/Profile/Pages unchanged.
