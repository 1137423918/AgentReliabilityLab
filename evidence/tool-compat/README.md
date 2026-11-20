# Declared-tool compatibility and a fresh failed roundtrip

The CPU service now offers explicit `json-object-compat` framing and validates
request-declared names and parameters. Default native framing remains available.

- **14 parser checks pass**; the worker without optional CPU dependencies skips
  these 14 checks. These are separate from the previously published 33 core tests.
- **Two fresh neural generations**: first, a valid `read_file /sample.py` call was
  parsed and the executor read a new, fixed, read-only fixture once. The second
  response was literal text `None`, so the predeclared exact-content roundtrip
  criterion **failed** (`roundtrip_verified=false`, driver exit 1).
- The followup's reconstructed native prompt contains the actual fixture marker
  once inside a tool response and has 250 tokens, matching inference usage.
  This tokenizer-only check does not explain why the model returned `None`.

[Report, provenance and hashes](report.json) · [Predeclared protocol](protocol.json)
· [Fresh failed trial](outputs/cpu-tool-roundtrip-20261120/report.json)
· [Rendered followup](outputs/cpu-tool-roundtrip-20261120/rendered-followup.json)
· [14 parser checks](parser-tests.log) · [Earlier literal-marker regression](literal-marker-before.log)
· [Protocol and reproduction](../../docs/tool-format-compat.md)

Actual inference used archived service source `883db1b…` in
`code/cpu-tool-compat/benchmarks/`. After stopping that model, one additional parser
edge case was fixed: literal native tags inside a complete JSON string. The new
test fails on the archived model-tested service and passes on the final candidate.
The final 14 checks also replay both fresh generated outputs. Current source is
archived separately under `sources/`; no additional inference is claimed for this
boundary change. The report identifies both source hashes.

This short explicitly prompted fixture is not a maintenance benchmark, a model
repair result, or a checkpoint-recovery test. The previous four no-patch attempts
remain unchanged. A new task listing virtual file paths is prepared but unrun.
Both requests avoided time limits; this does not establish a model capability
bound or general throughput result. The owned model service was identity-checked
and stopped; exit 143 was intentional SIGTERM cleanup.

Full request bodies here contain only the public test fixture and tool schema,
with no credentials. Private workspace paths in logs are replaced. Original and
public hashes are recorded separately. No model weights, private maintenance
conversations, checkpoint databases or worktrees are included.
