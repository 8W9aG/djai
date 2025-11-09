from djai import __version__, fetch_liked_tracks, greet


def test_version() -> None:
    assert __version__ == "0.3.0"


def test_greet() -> None:
    assert greet("DJ") == "Hello, DJ! Welcome to djai."


def test_fetch_liked_tracks_requires_token() -> None:
    try:
        fetch_liked_tracks("")
    except ValueError:
        return
    raise AssertionError("fetch_liked_tracks should require a token")


