from __future__ import annotations

import json
from pathlib import Path

import pytest
from helpers import bullish_engulfing_ltf, uptrend_htf

from fxscanner.adapters.fake import FakeSource
from fxscanner.cli import scan_once
from fxscanner.config import AppConfig, HubConfig, RiskConfig, StrategyConfig
from fxscanner.models import Side, Signal
from fxscanner.publish.client import HubAuthError, HubClient
from fxscanner.publish.publisher import Publisher
from fxscanner.publish.signing import sign
from fxscanner.scanner.state import SeenStore


def make_signal(key_time: int = 1000) -> Signal:
    return Signal(
        "EURUSD", Side.BUY, 1.098, 1.0945, 1.105, 35.0, 2.0, "engulfing", key_time, 1.0947, 1.0953
    )


class FakeTransport:
    """Scripted transport: each call pops the next outcome (status code or exception)."""

    def __init__(self, *outcomes: int | Exception) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[tuple[str, str, dict[str, str], bytes]] = []

    def __call__(
        self, method: str, url: str, headers: dict[str, str], body: bytes
    ) -> tuple[int, bytes]:
        self.calls.append((method, url, headers, body))
        outcome = self.outcomes.pop(0) if self.outcomes else 201
        if isinstance(outcome, Exception):
            raise outcome
        return outcome, b'{"created": true}'


def make_publisher(tmp_path: Path, transport: FakeTransport) -> Publisher:
    client = HubClient(
        "https://example.com/fx", "s3cret", transport=transport, clock=lambda: 1_700_000_000
    )
    return Publisher(client, tmp_path / "outbox.json")


def test_signature_matches_shared_test_vector() -> None:
    expected = "072797722b39e1c79ce186eb4407616db21956c07bb22a23520e1f38a41fed21"
    assert sign("s3cret", "1700000000", "POST", "/api/v1/signals/", b'{"a":1}') == expected


def test_request_is_signed_over_the_mounted_subpath(tmp_path: Path) -> None:
    transport = FakeTransport(201)
    make_publisher(tmp_path, transport).publish([make_signal()])
    _, url, headers, body = transport.calls[0]
    assert url == "https://example.com/fx/api/v1/signals/"
    assert headers["X-Signature"] == sign(
        "s3cret", "1700000000", "POST", "/fx/api/v1/signals/", body
    )
    assert json.loads(body)["key"] == "EURUSD:buy:1000"


def test_success_sends_without_queueing(tmp_path: Path) -> None:
    report = make_publisher(tmp_path, FakeTransport(201)).publish([make_signal()])
    assert (report.sent, report.queued) == (1, 0)
    assert not (tmp_path / "outbox.json").exists()


@pytest.mark.parametrize("failure", [500, 429, ConnectionError("down"), TimeoutError()])
def test_transient_failures_are_queued_then_flushed(
    tmp_path: Path, failure: int | Exception
) -> None:
    transport = FakeTransport(failure)
    publisher = make_publisher(tmp_path, transport)
    report = publisher.publish([make_signal()])
    assert (report.sent, report.queued) == (0, 1)
    flushed = publisher.flush()  # transport now defaults to 201
    assert (flushed.sent, flushed.queued) == (1, 0)
    assert publisher.pending == 0


def test_flush_stops_at_first_transient_failure_and_keeps_order(tmp_path: Path) -> None:
    publisher = make_publisher(tmp_path, FakeTransport(500, 500))
    publisher.publish([make_signal(1), make_signal(2)])
    assert publisher.pending == 2
    publisher._client.transport = FakeTransport(201, 500)  # type: ignore[misc]
    report = publisher.flush()
    assert (report.sent, report.queued) == (1, 1)
    assert json.loads((tmp_path / "outbox.json").read_text())[0]["trigger_epoch"] == 2


def test_permanent_rejection_is_dropped_not_retried(tmp_path: Path) -> None:
    publisher = make_publisher(tmp_path, FakeTransport(400))
    report = publisher.publish([make_signal()])
    assert report.rejected == ["EURUSD:buy:1000"] and report.queued == 0


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_surfaces_instead_of_queueing(tmp_path: Path, status: int) -> None:
    publisher = make_publisher(tmp_path, FakeTransport(status))
    with pytest.raises(HubAuthError):
        publisher.publish([make_signal()])
    assert publisher.pending == 0


def test_heartbeat_reports_reachability(tmp_path: Path) -> None:
    assert make_publisher(tmp_path, FakeTransport(200)).heartbeat({"n": 1}) is True
    assert make_publisher(tmp_path, FakeTransport(ConnectionError("x"))).heartbeat() is False


def test_scan_once_publishes_new_signal_and_heartbeats(tmp_path: Path) -> None:
    cfg = AppConfig(
        symbols=("EURUSD",), strategy=StrategyConfig(), risk=RiskConfig(),
        brokers={}, state_file=tmp_path / "seen.json",
    )  # fmt: skip
    source = FakeSource(
        {("EURUSD", "H4"): uptrend_htf(), ("EURUSD", "H1"): bullish_engulfing_ltf()}
    )
    transport = FakeTransport()
    out: list[str] = []
    scan_once(
        cfg, source, SeenStore(cfg.state_file), out.append, make_publisher(tmp_path, transport)
    )
    paths = [c[1].rsplit("/fx", 1)[1] for c in transport.calls]
    assert paths == ["/api/v1/signals/", "/api/v1/heartbeat/"]


def test_scan_once_reports_when_hub_is_down(tmp_path: Path) -> None:
    cfg = AppConfig(
        symbols=("EURUSD",), strategy=StrategyConfig(), risk=RiskConfig(),
        brokers={}, state_file=tmp_path / "seen.json",
    )  # fmt: skip
    source = FakeSource(
        {("EURUSD", "H4"): uptrend_htf(), ("EURUSD", "H1"): bullish_engulfing_ltf()}
    )
    out: list[str] = []
    publisher = make_publisher(tmp_path, FakeTransport(*[ConnectionError("down")] * 5))
    scan_once(cfg, source, SeenStore(cfg.state_file), out.append, publisher)
    assert any("queued for retry" in line for line in out)
    assert publisher.pending == 1


def test_hub_secret_must_be_in_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    hub = HubConfig(base_url="https://x", secret_env="NOPE_SECRET")
    monkeypatch.delenv("NOPE_SECRET", raising=False)
    from fxscanner.config import ConfigError

    with pytest.raises(ConfigError):
        hub.secret()
    monkeypatch.setenv("NOPE_SECRET", "abc")
    assert hub.secret() == "abc"
