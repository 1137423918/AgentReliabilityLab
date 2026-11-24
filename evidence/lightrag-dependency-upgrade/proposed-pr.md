## Description

Refresh the optional RAGAS evaluation lock entry from 0.4.3 to 0.4.4. The previous version matches [GHSA-95ww-475f-pr4f](https://osv.dev/vulnerability/GHSA-95ww-475f-pr4f); 0.4.4 routes the affected multimodal loader through its shared guarded-fetch implementation.

## Related Issues

Public advisory: GHSA-95ww-475f-pr4f / CVE-2026-6587.

## Changes Made

- Update the RAGAS version and its source/wheel metadata in `uv.lock`, using the existing `ragas>=0.3.7` declaration.
- The remaining 236 package blocks retain their existing contents.

## Checklist

- [x] Tested in a CPU development checkout of `main` at `cf82ba9f1e516c5c9ba95a6c5adfb60489e0ce59`.
- [x] Reviewed the lock diff and verified that it changes only the RAGAS package block.
- [x] Exercised the existing upstream evaluation test suite.
- [x] `pre-commit run --all-files` passed.

## Additional Notes

Both original and candidate locks passed `uv sync --locked --extra api --extra pytest --extra evaluation` and `uv pip check`. The same 21 upstream tests in `tests/evaluation -m offline` passed in both environments, with zero skips and real RAGAS 0.4.3/0.4.4 imports. The existing tests stub judge outputs; this is interface/offline integration validation, without LLM requests or RAG quality claims.

Validation used Python3.11 on Linux CPU; the upstream Evaluation Tests workflow uses Python3.12. Its hosted CI remains a separate check.
