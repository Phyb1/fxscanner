from __future__ import annotations

from pathlib import Path

import pytest

from fxscanner.config import BrokerProfile, ConfigError, HubConfig
from fxscanner.env import read_env


def write_env(text: str) -> None:
    Path(".env").write_text(text, encoding="utf-8")


def test_reads_from_dotenv_in_current_directory() -> None:
    write_env("FXT_A=hello\n")
    assert read_env("FXT_A") == "hello"


def test_missing_file_and_missing_key_return_none() -> None:
    assert read_env("FXT_NOPE") is None
    write_env("OTHER=1\n")
    assert read_env("FXT_NOPE") is None


def test_real_environment_beats_the_file(monkeypatch: pytest.MonkeyPatch) -> None:
    write_env("FXT_B=from-file\n")
    monkeypatch.setenv("FXT_B", "from-env")
    assert read_env("FXT_B") == "from-env"


def test_quoted_value_keeps_special_characters() -> None:
    write_env('FXT_PW="p&ss^w%rd#1 x"\n')
    assert read_env("FXT_PW") == "p&ss^w%rd#1 x"


def test_blank_value_counts_as_unset() -> None:
    write_env("FXT_C=\n")
    assert read_env("FXT_C") is None


def test_explicit_env_file_path(tmp_path: Path) -> None:
    other = tmp_path / "other.env"
    other.write_text("FXT_D=x\n", encoding="utf-8")
    assert read_env("FXT_D", other) == "x"
    assert read_env("FXT_D") is None


def test_broker_credentials_from_dotenv() -> None:
    write_env('T_LOGIN=580643\nT_PASS="a&b"\n')
    profile = BrokerProfile(name="b", server="s", login_env="T_LOGIN", password_env="T_PASS")
    assert profile.credentials() == (580643, "a&b")


def test_broker_credentials_missing_mentions_dotenv() -> None:
    profile = BrokerProfile(name="b", server="s", login_env="T_LOGIN2", password_env="T_PASS2")
    with pytest.raises(ConfigError, match=r"\.env"):
        profile.credentials()


def test_non_numeric_login_is_a_clear_error() -> None:
    write_env("T_LOGIN3=abc\nT_PASS3=x\n")
    profile = BrokerProfile(name="b", server="s", login_env="T_LOGIN3", password_env="T_PASS3")
    with pytest.raises(ConfigError, match="number"):
        profile.credentials()


def test_hub_secret_from_dotenv() -> None:
    write_env("FXT_HUB=s3cret\n")
    assert HubConfig(base_url="https://x", secret_env="FXT_HUB").secret() == "s3cret"
