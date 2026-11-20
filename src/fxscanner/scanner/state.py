from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path

from fxscanner.models import Signal


class SeenStore:
    """Remembers alerted signals so the same setup is never reported twice."""

    def __init__(self, path: Path, max_keys: int = 500) -> None:
        self._path = path
        self._max = max_keys
        self._keys: list[str] = self._load()

    def _load(self) -> list[str]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        return [str(k) for k in data] if isinstance(data, list) else []

    def filter_new(self, signals: Sequence[Signal]) -> list[Signal]:
        seen = set(self._keys)
        return [s for s in signals if s.key not in seen]

    def mark_seen(self, signals: Sequence[Signal]) -> None:
        self._keys = (self._keys + [s.key for s in signals])[-self._max :]
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._keys), encoding="utf-8")
        os.replace(tmp, self._path)
