from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, List

import pytest
from dotenv import load_dotenv as real_load_dotenv

from djai import cli


def _reject_authorization(*args: object, **kwargs: object) -> None:
    raise AssertionError("initiate_user_authorization should not be called")


def test_cli_outputs_track_count(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("SPOTIFY_API_TOKEN", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "initiate_user_authorization", _reject_authorization)
    monkeypatch.setattr(cli, "_download_audio_previews", lambda *a, **k: 0)

    captured: List[Any] = [
        {"id": "t1", "name": "Song", "artists": [{"name": "Artist"}], "album": {"name": "Album"}},
    ]

    monkeypatch.setattr(cli, "fetch_liked_tracks", lambda *args, **kwargs: captured)

    exit_code = cli.main(["--token", "abc", "--compact"])

    assert exit_code == 0
    out = capsys.readouterr().out.strip()
    assert out == "1"


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
    monkeypatch.setattr(cli, "_download_audio_previews", lambda *a, **k: 0)
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath(".env").write_text('SPOTIFY_API_TOKEN="env-token"\n', encoding="utf-8")

    captured: List[Any] = [{"id": "t1"}]
    monkeypatch.setattr(cli, "fetch_liked_tracks", lambda *args, **kwargs: captured)

    exit_code = cli.main(["--compact"])

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "1"


def test_cli_requires_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    tmp_path.joinpath(".env").write_text("", encoding="utf-8")
    monkeypatch.delenv("SPOTIFY_API_TOKEN", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "initiate_user_authorization", _reject_authorization)
    monkeypatch.setattr(cli, "_download_audio_previews", lambda *a, **k: 0)

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
    monkeypatch.setattr(cli, "_download_audio_previews", lambda *a, **k: 0)
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
    monkeypatch.setattr(cli, "_download_audio_previews", lambda *a, **k: 0)

    exit_code = cli.main(["--compact"])

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "1"
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
    monkeypatch.setattr(cli, "_download_audio_previews", lambda *a, **k: 0)

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


def test_cli_downloads_audio(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import types

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "load_dotenv", lambda *args, **kwargs: None)
    tracks = [
        {"id": "track1", "name": "Song", "preview_url": "https://example.com/audio.mp3"},
    ]
    monkeypatch.setattr(cli, "fetch_liked_tracks", lambda *a, **k: tracks)
    monkeypatch.delenv("SPOTIFY_API_TOKEN", raising=False)
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setattr(
        cli,
        "initiate_user_authorization",
        lambda *a, **k: {"access_token": "token", "refresh_token": "refresh"},
    )

    downloads: list[dict[str, Any]] = []
    separated: list[tuple[Path, Path]] = []

    class FakeYoutubeDL:
        def __init__(self, params: dict[str, Any]) -> None:
            self.params = params

        def __enter__(self) -> "FakeYoutubeDL":
            downloads.append({"params": self.params})
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def download(self, urls: list[str]) -> None:
            downloads[-1]["urls"] = urls
            Path(str(self.params["outtmpl"]) + ".mp3").write_bytes(b"mp3")

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=FakeYoutubeDL))

    def fake_separate(audio: Path, stems: Path) -> None:
        separated.append((audio, stems))
        stems.mkdir(parents=True, exist_ok=True)
        (stems / "vocals.wav").write_bytes(b"vocals")
        (stems / "other.wav").write_bytes(b"other")

    monkeypatch.setattr(cli, "_separate_audio_sources", fake_separate)

    exit_code = cli.main([])

    assert exit_code == 0
    assert downloads[0]["urls"] == ["https://example.com/audio.mp3"]
    audio_file = tmp_path / ".djai_cache" / "audio" / "track1.mp3"
    assert audio_file.exists()
    assert separated


def test_cli_downloads_audio_via_search(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import types

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "load_dotenv", lambda *args, **kwargs: None)
    tracks = [
        {
            "id": "track2",
            "name": "Diane Young",
            "artists": [{"name": "Vampire Weekend"}],
        },
    ]
    monkeypatch.setattr(cli, "fetch_liked_tracks", lambda *a, **k: tracks)
    monkeypatch.delenv("SPOTIFY_API_TOKEN", raising=False)
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setattr(
        cli,
        "initiate_user_authorization",
        lambda *a, **k: {"access_token": "token", "refresh_token": "refresh"},
    )

    downloads: list[dict[str, Any]] = []
    separated: list[tuple[Path, Path]] = []

    class FakeYoutubeDL:
        def __init__(self, params: dict[str, Any]) -> None:
            self.params = params

        def __enter__(self) -> "FakeYoutubeDL":
            downloads.append({"params": self.params})
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def download(self, urls: list[str]) -> None:
            downloads[-1]["urls"] = urls
            Path(str(self.params["outtmpl"]) + ".mp3").write_bytes(b"mp3")

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=FakeYoutubeDL))

    def fake_separate(audio: Path, stems: Path) -> None:
        separated.append((audio, stems))
        stems.mkdir(parents=True, exist_ok=True)
        (stems / "vocals.wav").write_bytes(b"vocals")
        (stems / "other.wav").write_bytes(b"other")

    monkeypatch.setattr(cli, "_separate_audio_sources", fake_separate)

    exit_code = cli.main([])

    assert exit_code == 0
    assert downloads[0]["urls"] == ["ytsearch1:Diane Young Vampire Weekend"]
    audio_file = tmp_path / ".djai_cache" / "audio" / "track2.mp3"
    assert audio_file.exists()
    assert separated


def test_separate_audio_sources_moves_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import types

    audio_dir = tmp_path / ".djai_cache" / "audio"
    audio_dir.mkdir(parents=True)
    audio_file = audio_dir / "track.mp3"
    audio_file.write_bytes(b"audio")

    stems_dir = tmp_path / ".djai_cache" / "stems" / "track"

    monkeypatch.setitem(sys.modules, "diffq", types.SimpleNamespace())

    def fake_run(cmd, *, capture_output, text, check, cwd):
        assert Path(cwd) == audio_dir
        out_root = Path(cmd[cmd.index("--out") + 1])
        model_dir = out_root / "mdx_extra_q" / stems_dir.name
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "vocals.wav").write_bytes(b"vocals")
        (model_dir / "other.wav").write_bytes(b"other")
        return types.SimpleNamespace(stdout="done", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    cli._separate_audio_sources(audio_file, stems_dir)

    assert (stems_dir / "vocals.wav").exists()
    assert (stems_dir / "other.wav").exists()
    assert not (stems_dir.parent / "mdx_extra_q").exists()


def test_ensure_audio_file_renames_double_extension(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    original = audio_dir / "track.mp3.mp3"
    original.write_bytes(b"mp3")

    resolved = cli._ensure_audio_file(audio_dir, "track")

    assert resolved == audio_dir / "track.mp3"
    assert resolved.exists()
    assert not original.exists()