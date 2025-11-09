"""Top-level package for djai."""

from __future__ import annotations

__all__ = [
    "__version__",
    "greet",
    "fetch_liked_tracks",
    "get_client_credentials_token",
    "exchange_authorization_code",
]
__version__ = "0.3.0"


def greet(name: str) -> str:
    """Return a friendly greeting for ``name``."""
    return f"Hello, {name}! Welcome to djai."


from .spotify import (  # noqa: E402
    exchange_authorization_code,
    fetch_liked_tracks,
    get_client_credentials_token,
)


