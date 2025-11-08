from djai import __version__, greet


def test_version() -> None:
    assert __version__ == "0.1.0"


def test_greet() -> None:
    assert greet("DJ") == "Hello, DJ! Welcome to djai."


