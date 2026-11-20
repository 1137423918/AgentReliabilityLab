# Native server-converter replay

**14/14 prompt byte strings and 14/14 complete token arrays match the historical reference audit.** The pinned server shared library's actual `oaicompat_chat_params_parse` is called directly with the original bodies; a separate common-chat rendering branch also matches. One fixed set of 14 requests, no model generation or GPU.

- [report.json](report.json): per-request text/token identity, all 40 runtime hashes, historical input hashes, binary/driver identity and declared process limits.
- [native.jsonl](native.jsonl): all native prompts, common-chat comparison prompts, native prompt parts and complete flattened token arrays. Byte-identical to the server artifact.
- [compile.json](compile.json), [compile log](logs/compile.log), [native log](logs/native.log): final source-bound successful build and vocabulary-only replay.
- [source provenance](backend-source-provenance.json), [package identities](packages.json), [artifacts.json](artifacts.json): official pinned source comparisons, isolated compiler inputs and transfer hashes.
- [initial rejected compile](preflight/stream-json-compile.log): unsupported JSON stream overload, corrected before the successful final run. No inference was attempted by this compile failure.

The existing model and backend were not modified. No inference context or HTTP listener was created. Thinking was disabled, Jinja enabled and the GGUF's own exact template used. Tokenization compares flattened prompt text with `add_special=false, parse_special=true`; this does not measure live slot usage. Native output includes the source/template text under their accompanying [backend](BACKEND_LICENSE), [model template](MODEL_TEMPLATE_LICENSE) and [Deep Agents](UPSTREAM_LICENSE) licenses.

Logical input totals remain 43990 / 11341 / 19054. Equivalence is established only for these captured requests, settings and pinned versions. It does not prove arbitrary templates equivalent or demonstrate model success, cost or inference speed. The historical [context audit](../context-budget/README.md) and its immutable reports retain their original scope; this is a dated follow-up. Existing 74 worker tests were not rerun and these 14 comparisons are not added to that count.

[Implementation, actual command and interpretation](../../docs/native-template.md).
