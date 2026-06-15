# Learnings

- For MMSeg test/inference subprocesses, keep only the project root in `PYTHONPATH`; load generated project modules such as `custom_rs_dataset.py` by explicit file path before `Config.fromfile()` / model initialization.
- Keep inference and model-test work in `QThread`/subprocess flows; validate project custom module file paths before starting long-running work so the UI can fail fast with a clear message.
