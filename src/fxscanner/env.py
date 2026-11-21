from __future__ import annotations

from pathlib import Path

from decouple import Config, RepositoryEmpty, RepositoryEnv, UndefinedValueError

DEFAULT_ENV_FILE = ".env"


def read_env(name: str, env_file: Path | None = None) -> str | None:
    """Look up a setting: real environment variable first, then the ``.env`` file.

    The file is looked up in the current directory (where you run ``fxscan``) unless
    ``env_file`` is given. Quote values containing special characters:
    ``FUSION_MT5_PASSWORD="p&ss^word#1"``. Returns None when unset or blank.
    """
    path = env_file or Path(DEFAULT_ENV_FILE)
    repository = RepositoryEnv(str(path)) if path.is_file() else RepositoryEmpty()
    try:
        value = str(Config(repository)(name))
    except UndefinedValueError:
        return None
    return value or None
