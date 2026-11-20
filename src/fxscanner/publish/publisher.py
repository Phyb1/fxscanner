from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fxscanner.models import Signal
from fxscanner.publish.client import (
    HubClient,
    HubRejectedError,
    HubTransientError,
    signal_payload,
)


@dataclass
class PublishReport:
    sent: int = 0
    queued: int = 0
    rejected: list[str] = field(default_factory=list)


class Publisher:
    """Delivers signals to the hub. Failed deliveries wait in an on-disk outbox."""

    def __init__(self, client: HubClient, outbox: Path, source: str = "scanner") -> None:
        self._client = client
        self._outbox = outbox
        self._source = source

    def _load(self) -> list[dict[str, Any]]:
        if not self._outbox.exists():
            return []
        try:
            data = json.loads(self._outbox.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []

    def _store(self, items: list[dict[str, Any]]) -> None:
        tmp = self._outbox.with_suffix(".tmp")
        tmp.write_text(json.dumps(items), encoding="utf-8")
        os.replace(tmp, self._outbox)

    @property
    def pending(self) -> int:
        return len(self._load())

    def flush(self) -> PublishReport:
        """Retry queued signals oldest-first; stop at the first transient failure."""
        report = PublishReport()
        queue = self._load()
        remaining = list(queue)
        for item in queue:
            try:
                self._client.send_payload(item)
            except HubTransientError:
                break
            except HubRejectedError:
                report.rejected.append(str(item.get("key")))
            else:
                report.sent += 1
            remaining.pop(0)
        if remaining != queue:
            self._store(remaining)
        report.queued = len(remaining)
        return report

    def publish(self, signals: Sequence[Signal]) -> PublishReport:
        report = PublishReport()
        undelivered: list[dict[str, Any]] = []
        for signal in signals:
            payload = signal_payload(signal)
            try:
                self._client.send_payload(payload)
            except HubTransientError:
                undelivered.append(payload)
            except HubRejectedError:
                report.rejected.append(signal.key)
            else:
                report.sent += 1
        if undelivered:
            self._store(self._load() + undelivered)
        report.queued = self.pending
        return report

    def heartbeat(self, detail: dict[str, Any] | None = None) -> bool:
        try:
            self._client.heartbeat(self._source, detail)
        except HubTransientError:
            return False
        return True
