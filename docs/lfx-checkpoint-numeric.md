# Non-finite numeric state in durable LFX checkpoints

LFX's durable graph checkpoint must either restore a built value faithfully or mark it opaque so resume can recompute the producer. In the pinned Langflow release branch, NaN and positive/negative infinity can instead become JSON `null` while the wire envelope still claims a restorable value. A dependent consumer then receives `None` from a producer that is still marked built.

## Reproduction and repair

The subject is `langflow-ai/langflow`, `release-1.14.0`, base `4d3b965c658ae147f3204b0a17bbb63b1f4f722e`. The baseline has nine observed silent numeric changes: three non-finite values in scalar, nested-container and LFX Data forms. Three finite controls round-trip correctly. The probe uses the actual tagged encoder, `GraphCheckpoint` and `SqliteCheckpointStore`, closes/reopens the store, and checks both values and explicit drop markers. It is not itself a graph execution benchmark.

Data's JSON model dump can already replace a non-finite value before the durable writer sees it. Merely validating the dump, or checking its final JSON syntax, does not catch that loss. The repair checks raw model fields before dumping, rejects non-finite scalar floats, and checks strict JSON after dumping to catch serializer-introduced values. It reuses the existing opaque-drop/recompute policy without adding a wire type or changing general API output serialization.

A separate regression builds connected numeric producer/consumer components using `.set()`, executes the producer, writes a checkpoint to a real SQLite database, reopens it and calls `Graph.resume_from_checkpoint`. The non-finite cases must unbuild the producer and finish with the expected numeric consumer output; the finite producer remains built. Numeric values are supplied as strings in component configuration, so the flow definition itself remains JSON-safe and can reproduce the original value.

## Observed focused validation

The final new test file fails **12 checks and passes two finite controls** on the original source. The candidate passes the complete checkpoint and durable-service test directories: **105 passed, five existing deprecation warnings**, including all 14 new checks. This is one Linux/Python configuration, not the full monorepo CI matrix. The same public SQLite driver changes from 3/12 policy-safe cases on the original (only finite controls) to 12/12 on the candidate. These 12 probes are not added to the 105 test count.

An initial candidate run incorrectly treated `_call_order` as an accumulating invocation counter; that test assumption was corrected to check actual numeric producer and consumer outputs. The final baseline was rerun with the final test file. An early broad run lacked sparse-checkout benchmark scripts; that failure remains in preflight evidence. Broad checks and upstream review status are reported separately.

The broad graph + durable run has 682 passes, three failures, six skips and one expected failure. Two catalog identity failures also fail on the unmodified base; a three-second scheduler timeout passes isolated checks on both variants but remains unresolved in the broad run. These results are preserved, not relabeled as green.

The candidate branch has not been pushed and **no Langflow PR exists**: GitHub rejected release-branch import for missing `workflow` token scope. The four-file repair changes no workflow files. A local validated commit is recorded, and the reviewable patch is public; expanded permission is pending. See the [publication receipt](../evidence/lfx-checkpoint-numeric/upstream-status.json).

## Run on a CPU server

Use a dedicated checkout and environment. All recorded execution was on the authorized Linux server's CPU, Python 3.13.18, without model inference, provider credentials or GPU allocation.

```sh
cd /path/to/langflow
uv sync --frozen --package lfx --group dev
DO_NOT_TRACK=true uv run --no-sync --package lfx pytest \
  src/lfx/tests/unit/graph/checkpoint src/lfx/tests/unit/services/durable -q
DO_NOT_TRACK=true uv run --no-sync --package lfx python \
  /path/to/AgentReliabilityLab/benchmarks/lfx_checkpoint_numeric.py \
  --repo /path/to/langflow --output /tmp/fresh-lfx-numeric-probe
```

The probe creates a new output directory and refuses to import a different checkout than `--repo`. Do not publish its SQLite database. Public evidence contains text reports, source hashes, package versions, logs and the patch; private server paths are normalized and original/public hashes are kept separately.

## Boundaries

This checks native Python floats in the checkpoint encoder's containers and model fields. It is not a proof that arbitrary custom model serializers are lossless, that every numeric library's scalar type is supported, or that older checkpoints whose values have already become `null` can be repaired. Recomputing a producer can repeat its side effects; this does not add exactly-once execution. Models whose serializers would intentionally encode a non-finite raw field in another form are conservatively dropped too.

The change is a checkpoint/storage reliability contribution, not a new Agent runtime adapter or a successful autonomous model repair. Test counts overlap and are not added together. Upstream CI/review and merge state remain distinct from server validation.

[Results and evidence](../evidence/lfx-checkpoint-numeric/README.md).

Sources: [pinned checkpoint encoder](https://github.com/langflow-ai/langflow/blob/4d3b965c658ae147f3204b0a17bbb63b1f4f722e/src/lfx/src/lfx/graph/checkpoint/schema.py), [SQLite checkpoint store](https://github.com/langflow-ai/langflow/blob/4d3b965c658ae147f3204b0a17bbb63b1f4f722e/src/lfx/src/lfx/services/durable/sqlite_checkpoints.py), [contribution guide and release target](https://github.com/langflow-ai/langflow/blob/4d3b965c658ae147f3204b0a17bbb63b1f4f722e/CONTRIBUTING.md).
