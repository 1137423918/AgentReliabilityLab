# Explicit whole-paper input

`intake.json` identifies exact LightRAG v3 and MiniRAG v3 PDFs on arXiv. Place matching downloaded `lightrag.pdf` and `minirag.pdf` beside it on your compute server, then use `agentlab-research prepare-pdf --manifest intake.json --output /tmp/new-paper-input`. Full PDFs and extracted text are not redistributed in this repository.

The application does not fetch URLs; the local operator declares the source. Use the artifact SHA256 values recorded in the [workflow evidence](../../evidence/paper-library/input-provenance.json) to reproduce this run. These fixed 2025 versions exercise the paper workflow; they are not presented as the latest Agent papers or a blind retrieval evaluation.
