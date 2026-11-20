from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from fxscanner.models import Signal
from fxscanner.publish.signing import sign

# (method, url, headers, body) -> (status, response body)
Transport = Callable[[str, str, dict[str, str], bytes], tuple[int, bytes]]


class HubError(RuntimeError):
    """Base class for hub communication failures."""


class HubTransientError(HubError):
    """Network trouble or a server error: safe to retry later."""


class HubRejectedError(HubError):
    """The hub understood the request and refused it: retrying will not help."""


class HubAuthError(HubError):
    """Bad secret or clock skew: a configuration problem the user must fix."""


def urllib_transport(
    method: str, url: str, headers: dict[str, str], body: bytes, timeout: float = 15.0
) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body or None, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), bytes(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def signal_payload(signal: Signal) -> dict[str, Any]:
    return {
        "key": signal.key,
        "symbol": signal.symbol,
        "side": signal.side.value,
        "entry": signal.entry,
        "stop": signal.stop,
        "target": signal.target,
        "risk_pips": signal.risk_pips,
        "rr": signal.rr,
        "trigger": signal.trigger,
        "trigger_epoch": signal.trigger_time,
        "zone_low": signal.zone_low,
        "zone_high": signal.zone_high,
    }


@dataclass
class HubClient:
    base_url: str
    secret: str
    transport: Transport = urllib_transport
    clock: Callable[[], float] = time.time

    def _request(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode()
        # The server signs request.path, which includes any sub-path the app is mounted at.
        signed_path = urlsplit(self.base_url).path.rstrip("/") + path
        timestamp = str(int(self.clock()))
        headers = {
            "Content-Type": "application/json",
            "X-Timestamp": timestamp,
            "X-Signature": sign(self.secret, timestamp, "POST", signed_path, body),
        }
        try:
            status, raw = self.transport("POST", self.base_url.rstrip("/") + path, headers, body)
        except OSError as exc:  # URLError, timeouts, connection resets
            raise HubTransientError(f"network error: {exc}") from exc
        if status in (401, 403):
            raise HubAuthError("hub refused the signature; check the secret and the PC clock")
        if status >= 500 or status == 429:
            raise HubTransientError(f"hub returned {status}")
        if status >= 400:
            raise HubRejectedError(f"hub rejected the request ({status}): {raw[:200]!r}")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise HubTransientError("hub returned invalid JSON") from exc
        return data if isinstance(data, dict) else {}

    def send_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("/api/v1/signals/", payload)

    def heartbeat(self, source: str, detail: dict[str, Any] | None = None) -> None:
        self._request("/api/v1/heartbeat/", {"source": source, "detail": detail or {}})
