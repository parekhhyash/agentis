"""Pieces shared by the OAuth sign-ins (CRMs, LinkedIn, X): PKCE, and a
`state` parameter that is encrypted (Fernet) and time-limited, so callbacks
need no server-side session and nobody but this backend can read or forge it."""

import base64
import hashlib
import json
import secrets

from cryptography.fernet import Fernet, InvalidToken

STATE_TTL_SECONDS = 600


class StateError(Exception):
    """The state came back expired, altered or incomplete."""


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def seal_state(fernet: Fernet, user_id: str, provider: str, verifier: str = "", extra: dict[str, str] | None = None) -> str:
    """`extra` carries per-sign-in details the callback needs (like a
    company's own Salesforce app); it's encrypted with the rest."""
    payload = {**(extra or {}), "u": user_id, "p": provider, "v": verifier, "n": secrets.token_urlsafe(8)}
    return fernet.encrypt(json.dumps(payload, separators=(",", ":")).encode()).decode()


def open_state(fernet: Fernet, state: str, *, need_verifier: bool = True) -> dict[str, str]:
    try:
        payload = json.loads(fernet.decrypt(state.encode(), ttl=STATE_TTL_SECONDS))
    except (InvalidToken, ValueError):
        raise StateError("The sign-in link expired or was changed; connect again") from None
    required = ("u", "p", "v") if need_verifier else ("u", "p")
    if not isinstance(payload, dict) or not all(payload.get(k) for k in required):
        raise StateError("Invalid sign-in state")
    return payload
