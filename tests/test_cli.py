from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, List

import pytest
from dotenv import load_dotenv as real_load_dotenv

from djai import cli


def _reject_authorization(*args: object, **kwargs: object) -> None:
    raise AssertionError("initiate_user_authorization should not be called")


def test_cli_outputs_tracks_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("SPOTIFY_API_TOKEN", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "initiate_user_authorization", _reject_authorization)

    captured: List[Any] = [
        {"id": "t1", "name": "Song", "artists": [{"name": "Artist"}], "album": {"name": "Album"}},
    ]

    monkeypatch.setattr(cli, "fetch_liked_tracks", lambda *args, **kwargs: captured)

    exit_code = cli.main(["--token", "abc", "--compact"])

    assert exit_code == 0
    out = capsys.readouterr().out.strip()
    assert json.loads(out) == captured


def test_cli_reads_token_from_env_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("SPOTIFY_API_TOKEN", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(
        cli,
        "load_dotenv",
        lambda *args, **kwargs: real_load_dotenv(tmp_path / ".env", override=True),
    )
    monkeypatch.setattr(cli, "initiate_user_authorization", _reject_authorization)
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath(".env").write_text('SPOTIFY_API_TOKEN="env-token"\n', encoding="utf-8")

    captured: List[Any] = [{"id": "t1"}]
    monkeypatch.setattr(cli, "fetch_liked_tracks", lambda *args, **kwargs: captured)

    exit_code = cli.main(["--compact"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == captured


def test_cli_requires_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath(".env").write_text("", encoding="utf-8")
    monkeypatch.delenv("SPOTIFY_API_TOKEN", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "initiate_user_authorization", _reject_authorization)

    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("fetch_liked_tracks should not be called")

    monkeypatch.setattr(cli, "fetch_liked_tracks", _fail)

    with pytest.raises(SystemExit):
        cli.main([])


def test_cli_auto_authorizes_when_missing_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("SPOTIFY_API_TOKEN", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(
        cli,
        "load_dotenv",
        lambda *args, **kwargs: real_load_dotenv(tmp_path / ".env", override=True),
    )
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath(".env").write_text(
        "SPOTIFY_CLIENT_ID=id\nSPOTIFY_CLIENT_SECRET=secret\n", encoding="utf-8"
    )

    captured: List[Any] = [{"id": "cc"}]
    called: dict[str, Any] = {}

    def fake_fetch(token: str, **kwargs: Any) -> List[Any]:
        called["token"] = token
        return captured

    monkeypatch.setattr(cli, "fetch_liked_tracks", fake_fetch)
    monkeypatch.setattr(
        cli,
        "initiate_user_authorization",
        lambda *args, **kwargs: {
            "access_token": "user-token",
            "refresh_token": "ref-token",
        },
    )

    exit_code = cli.main(["--compact"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == captured
    assert called["token"] == "user-token"
    assert os.environ.get("SPOTIFY_API_TOKEN") == "user-token"
    session_file = tmp_path / ".djai_session"
    assert session_file.exists()
    data = json.loads(session_file.read_text(encoding="utf-8"))
    assert data["access_token"] == "user-token"
    assert data["refresh_token"] == "ref-token"
    monkeypatch.delenv("SPOTIFY_API_TOKEN", raising=False)


def test_cli_uses_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "load_dotenv", lambda *args, **kwargs: None)

    def fake_authorize(*_args: object, **_kwargs: object) -> dict[str, str]:
        return {"access_token": "token", "refresh_token": "refresh"}

    monkeypatch.setattr(cli, "initiate_user_authorization", fake_authorize)
    monkeypatch.delenv("SPOTIFY_API_TOKEN", raising=False)
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")

    calls: list[list[dict[str, Any]]] = []

    def fake_fetch(token: str, **kwargs: Any) -> List[Any]:
        payload = [{"id": f"track-{len(calls)}"}]
        calls.append(payload)
        return payload

    monkeypatch.setattr(cli, "fetch_liked_tracks", fake_fetch)

    # First run populates cache.
    cli.main(["--compact", "--max-items", "1"])
    assert len(calls) == 1

    # Second run should read from cache and not call fetch again.
    cli.main(["--compact", "--max-items", "1"])
    assert len(calls) == 1

    # Expire cache and ensure fetch called once more.
    cache_dir = tmp_path / ".djai_cache"
    cache_file = next(cache_dir.glob("*.json"))
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    payload["timestamp"] = payload["timestamp"] - (31 * 24 * 60 * 60)
    cache_file.write_text(json.dumps(payload), encoding="utf-8")

    cli.main(["--compact", "--max-items", "1"])
    assert len(calls) == 2