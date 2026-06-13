"""Scoped import-path helpers for generated MMSeg custom modules."""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from typing import Iterable, Iterator


def normalize_import_paths(paths: str | Iterable[str] | None) -> list[str]:
    if paths is None:
        raw_paths: list[str] = []
    elif isinstance(paths, str):
        raw_paths = [paths]
    else:
        raw_paths = list(paths)

    normalized_paths: list[str] = []
    for path in raw_paths:
        if not path:
            continue
        abs_path = os.path.abspath(path)
        if os.path.isdir(abs_path) and abs_path not in normalized_paths:
            normalized_paths.append(abs_path)
    return normalized_paths


@contextmanager
def temporary_sys_path(paths: str | Iterable[str] | None) -> Iterator[list[str]]:
    """Temporarily prepend directories to ``sys.path`` and restore afterwards."""
    added_paths: list[str] = []
    for path in normalize_import_paths(paths):
        if path not in sys.path:
            sys.path.insert(0, path)
            added_paths.append(path)

    try:
        yield added_paths
    finally:
        for path in reversed(added_paths):
            try:
                sys.path.remove(path)
            except ValueError:
                pass
