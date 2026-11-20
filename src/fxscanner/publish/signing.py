from __future__ import annotations

import hashlib
import hmac


def sign(secret: str, timestamp: str, method: str, path: str, body: bytes) -> str:
    """HMAC-SHA256 over timestamp, method, path and raw body (mirrors fxhub.hub.auth.sign)."""
    message = f"{timestamp}\n{method.upper()}\n{path}\n".encode() + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
