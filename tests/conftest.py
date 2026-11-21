from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run each test in an empty folder so a developer's real .env is never read."""
    monkeypatch.chdir(tmp_path)
