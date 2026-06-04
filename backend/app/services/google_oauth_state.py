from __future__ import annotations

import base64
import hashlib
import hmac
import time
import uuid


class OAuthStateError(ValueError):
    pass


def build_oauth_state(
    org_id: uuid.UUID,
    technician_id: uuid.UUID | None,
    signing_key: str,
    timestamp: int | None = None,
) -> str:
    ts = timestamp if timestamp is not None else int(time.time())
    tech_part = str(technician_id) if technician_id else "org"
    payload = f"{org_id}:{tech_part}:{ts}"
    digest = hmac.new(
        signing_key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    raw = f"{payload}:{digest}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def verify_oauth_state(
    state: str,
    signing_key: str,
    max_age_seconds: int = 600,
) -> tuple[uuid.UUID, uuid.UUID | None]:
    try:
        padded = state + "=" * (-len(state) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode()).decode()
        parts = decoded.split(":")
        if len(parts) != 4:
            raise OAuthStateError("Invalid state format")
        org_id = uuid.UUID(parts[0])
        tech_part = parts[1]
        ts = int(parts[2])
        provided_sig = parts[3]
    except (ValueError, UnicodeDecodeError) as exc:
        raise OAuthStateError("Invalid state parameter") from exc

    payload = f"{org_id}:{tech_part}:{ts}"
    expected_sig = hmac.new(
        signing_key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(provided_sig, expected_sig):
        raise OAuthStateError("State signature mismatch")

    if int(time.time()) - ts > max_age_seconds:
        raise OAuthStateError("State expired")

    technician_id = None if tech_part == "org" else uuid.UUID(tech_part)
    return org_id, technician_id
