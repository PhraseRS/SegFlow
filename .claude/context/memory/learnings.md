# Learnings

- For MMSeg test/inference subprocesses, keep only the project root in `PYTHONPATH`; load generated project modules such as `custom_rs_dataset.py` by explicit file path before `Config.fromfile()` / model initialization.
- Keep inference and model-test work in `QThread`/subprocess flows; validate project custom module file paths before starting long-running work so the UI can fail fast with a clear message.
- For runtime language changes, retain the active `QTranslator` for its full lifetime and rebuild the top-level window after switching catalogs so constructor-created child widgets are translated consistently; migrate project/UI state before closing the old window.
- Legacy PySide6 widgets may contain untranslated constructor literals even when a catalog entry exists; an application-level top-window Show event filter can translate common widget properties and runtime dialogs while gradual `tr()` cleanup continues.
- A custom partial `QTranslator` must return `sourceText` for missing JSON keys; delegating to the base implementation returns an empty string and can blank labels, menus, and buttons.
