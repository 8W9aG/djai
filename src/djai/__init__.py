"""Top-level package for djai."""

from __future__ import annotations

__all__ = ["__version__", "greet"]
__version__ = "0.1.0"


def greet(name: str) -> str:
    """Return a friendly greeting for ``name``."""
    return f"Hello, {name}! Welcome to djai."


