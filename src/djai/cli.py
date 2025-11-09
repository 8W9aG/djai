"""Command-line interface for djai."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import socketserver
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Sequence

from dotenv import load_dotenv

from .spotify import exchange_authorization_code, fetch_liked_tracks

DEFAULT_REDIRECT_URI = "http://127.0.0.1:8765/callback"
AUTHORIZE_TIMEOUT = 300
SESSION_FILENAME = ".djai_session"
CACHE_DIRNAME = ".djai_cache"
CACHE_TTL_SECONDS = 30 * 24 * 60 * 60  # ~30 days


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="djai",
        description="Fetch Spotify liked tracks metadata for DJ ideation.",
    )
    parser.add_argument(
        "--token",
        help="Spotify API token with user-library-read scope. "
        "Falls back to the SPOTIFY_API_TOKEN environment variable if omitted.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Number of tracks to fetch per request (max 50).",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=None,
        help="Optional maximum number of tracks to retrieve.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Emit compact JSON instead of pretty-printed output.",
    )
    parser.add_argument(
        "--client-id",
        help="Spotify client ID (falls back to SPOTIFY_CLIENT_ID env var).",
    )
    parser.add_argument(
        "--client-secret",
        help="Spotify client secret (falls back to SPOTIFY_CLIENT_SECRET env var).",
    )
    parser.add_argument(
        "--redirect-uri",
        default=DEFAULT_REDIRECT_URI,
        help=f"Redirect URI to listen on during authorization (default: {DEFAULT_REDIRECT_URI}).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)

    cwd = Path.cwd()
    session = _load_session(cwd)

    token = args.token or os.getenv("SPOTIFY_API_TOKEN")
    client_id = args.client_id or os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = args.client_secret or os.getenv("SPOTIFY_CLIENT_SECRET")
    refresh_token = session.get("refresh_token") if session else None
    if not token and session:
        token = session.get("access_token")

    new_tokens: Dict[str, Any] | None = None

    if not token and client_id and client_secret:
        new_tokens = initiate_user_authorization(
            client_id,
            client_secret,
            redirect_uri=args.redirect_uri,
        )
        token = new_tokens.get("access_token")
        if not token:
            parser.error("Spotify authorization did not return an access token.")
        os.environ["SPOTIFY_API_TOKEN"] = token
        refresh_token = new_tokens.get("refresh_token")
        _store_session(
            cwd,
            {
                "access_token": token,
                "refresh_token": refresh_token,
                "timestamp": time.time(),
            },
        )

    if not token:
        parser.error(
            "A Spotify API token is required. "
            "Pass --token, set SPOTIFY_API_TOKEN, or provide client credentials."
        )

    cache_key = _make_cache_key(token, args.limit, args.max_items)
    cached_tracks = _load_cache(cwd, cache_key)
    if cached_tracks is not None:
        tracks = cached_tracks
        sys.stderr.write("Loaded liked tracks from cache.\n")
    else:
        sys.stderr.write("Fetching liked tracks from Spotify...\n")
        tracks = fetch_liked_tracks(
            token,
            limit=args.limit,
            max_items=args.max_items,
        )
        _store_cache(
            cwd,
            cache_key,
            tracks,
        )
        sys.stderr.write("Finished fetching liked tracks.\n")

    try:
        downloaded = _download_audio_previews(
            tracks,
            cwd / CACHE_DIRNAME / "audio",
        )
    except RuntimeError:
        return 1
    sys.stderr.write(f"Downloaded {downloaded} new audio previews.\n")

    sys.stdout.write(f"{len(tracks)}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


class _AuthServer(socketserver.TCPServer):
    allow_reuse_address = True


def initiate_user_authorization(
    client_id: str,
    client_secret: str,
    *,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    scope: str = "user-library-read",
) -> Dict[str, Any]:
    """Perform the Authorization Code flow to obtain a user access token."""

    parsed_redirect = urllib.parse.urlparse(redirect_uri)
    if parsed_redirect.scheme not in {"http", "https"}:
        raise ValueError("Redirect URI must use http or https.")
    host = parsed_redirect.hostname or "127.0.0.1"
    port = parsed_redirect.port
    if port is None:
        port = 443 if parsed_redirect.scheme == "https" else 80
    path = parsed_redirect.path or "/"

    state = secrets.token_urlsafe(16)
    authorize_params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "show_dialog": "true",
    }
    authorize_url = (
        "https://accounts.spotify.com/authorize?"
        + urllib.parse.urlencode(authorize_params)
    )

    received: MutableMapping[str, Any] = {}
    event = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != path:
                self.send_error(404)
                return

            payload = urllib.parse.parse_qs(parsed.query)
            if "error" in payload:
                received["error"] = payload.get("error", ["unknown"])[0]
            else:
                received["code"] = payload.get("code", [None])[0]
                received["state"] = payload.get("state", [None])[0]

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>You may close this window.</h1></body></html>"
            )
            event.set()

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    with _AuthServer((host, port), Handler) as httpd:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            print("Please authorize the application in your browser.")
            print(f"Opening: {authorize_url}")
            try:
                webbrowser.open(authorize_url, new=1, autoraise=True)
            except webbrowser.Error:
                pass

            deadline = time.time() + AUTHORIZE_TIMEOUT
            while not event.is_set():
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise TimeoutError("Timed out waiting for Spotify authorization.")
                event.wait(timeout=min(1.0, remaining))
        finally:
            httpd.shutdown()
            thread.join(timeout=1)

    if received.get("error"):
        raise RuntimeError(f"Spotify authorization failed: {received['error']}")

    if received.get("state") != state:
        raise RuntimeError("Received mismatched state during Spotify authorization.")

    code = received.get("code")
    if not code:
        raise RuntimeError("Spotify authorization did not return a code.")

    return exchange_authorization_code(
        client_id,
        client_secret,
        code,
        redirect_uri=redirect_uri,
    )


def _load_session(base_path: Path) -> Dict[str, Any] | None:
    session_file = base_path / SESSION_FILENAME
    if not session_file.exists():
        return None
    try:
        with session_file.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _store_session(base_path: Path, data: Dict[str, Any]) -> None:
    session_file = base_path / SESSION_FILENAME
    if not data.get("access_token"):
        session_file.unlink(missing_ok=True)
        return
    try:
        with session_file.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except OSError:
        pass


def _make_cache_key(token: str, limit: int, max_items: int | None) -> str:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return f"liked_tracks_{token_hash}_limit{limit}_max{max_items or 'all'}.json"


def _load_cache(base_path: Path, cache_key: str) -> list[Dict[str, Any]] | None:
    cache_dir = base_path / CACHE_DIRNAME
    cache_file = cache_dir / cache_key
    if not cache_file.exists():
        return None
    try:
        with cache_file.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    timestamp = payload.get("timestamp")
    if timestamp is None or time.time() - timestamp > CACHE_TTL_SECONDS:
        cache_file.unlink(missing_ok=True)
        return None
    tracks = payload.get("tracks")
    if not isinstance(tracks, list):
        return None
    return tracks


def _store_cache(base_path: Path, cache_key: str, tracks: list[Dict[str, Any]]) -> None:
    cache_dir = base_path / CACHE_DIRNAME
    try:
        cache_dir.mkdir(exist_ok=True)
        cache_file = cache_dir / cache_key
        with cache_file.open("w", encoding="utf-8") as fh:
            json.dump({"timestamp": time.time(), "tracks": tracks}, fh, indent=2)
    except OSError:
        pass


def _download_audio_previews(
    tracks: list[Dict[str, Any]],
    audio_dir: Path,
) -> int:
    try:
        from yt_dlp import YoutubeDL  # type: ignore
    except ImportError as exc:  # pragma: no cover - runtime guard
        sys.stderr.write(
            "yt-dlp is required for audio downloading. "
            "Install with `pip install djai[dev]` or `pip install yt-dlp`.\n"
        )
        raise RuntimeError("yt-dlp is not installed") from exc

    downloaded = 0
    audio_dir.mkdir(parents=True, exist_ok=True)

    for track in tracks:
        track_id = track.get("id") or hashlib.sha256(
            json.dumps(track, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        target = audio_dir / f"{track_id}.mp3"
        if target.exists():
            continue
        preview_url = track.get("preview_url")
        if not preview_url:
            query = _build_search_query(track)
            if query:
                preview_url = f"ytsearch1:{query}"
                track_name = track.get("name", "unknown")
                sys.stderr.write(
                    f"No preview for '{track_name}', searching YouTube for '{query}'.\n"
                )
            else:
                track_name = track.get("name", "unknown")
                sys.stderr.write(
                    f"Skipping track '{track_name}' without preview or searchable metadata.\n"
                )
                continue

        opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "noplaylist": True,
            "outtmpl": str(target),
            "overwrites": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }

        try:
            with YoutubeDL(opts) as ydl:
                ydl.download([preview_url])
            downloaded += 1
        except Exception as exc:  # pragma: no cover - defensive
            sys.stderr.write(
                f"Failed to download preview for '{track.get('name', track_id)}': {exc}\n"
            )
            if target.exists():
                target.unlink(missing_ok=True)

    return downloaded


def _build_search_query(track: Mapping[str, Any]) -> str | None:
    parts: list[str] = []
    name = track.get("name")
    if isinstance(name, str):
        parts.append(name)

    artists = track.get("artists")
    if isinstance(artists, list):
        for artist in artists:
            if isinstance(artist, Mapping):
                artist_name = artist.get("name")
                if isinstance(artist_name, str):
                    parts.append(artist_name)

    query = " ".join(part.strip() for part in parts if part)
    return query or None


