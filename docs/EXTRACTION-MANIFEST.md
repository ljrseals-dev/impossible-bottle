# Nested archive extraction manifest

- Source repository archive: `impossible-bottle-pipeline.tar-3.gz`
- Extraction root: `pipeline/artifacts/`
- Nested `.tar.gz` archives extracted: 12 levels
- Remaining `.tar.gz` archives under `pipeline/`: 0 (verified against the branch tree)
- Extracted files remain in their original nested directory structure to avoid overwriting same-named files from different archive layers.
- The original compressed archive files were removed after each successful extraction.
- Extraction was performed on `extract/impossible-bottle-pipeline`; `main` was not modified.

The nested archives contained repeated project trees with differing file contents and sizes. They have been retained as separate directory levels rather than merged or deduplicated without a content audit.
