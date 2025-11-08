"""Helpers for interacting with Spotify's Web API."""

from __future__ import annotations

from typing import Any, Iterable, List, Mapping, MutableMapping, Optional

import requests
from requests.auth import HTTPBasicAuth

SPOTIFY_LIKED_TRACKS_URL = "https://api.spotify.com/v1/me/tracks"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
MAX_PAGE_SIZE = 50

TrackMetadata = MutableMapping[str, Any]


class SpotifyAPIError(RuntimeError):
    """Raised when the Spotify API returns an unexpected response."""


def exchange_authorization_code(
    client_id: str,
    client_secret: str,
    code: str,
    *,
    redirect_uri: str,
    session: Optional[requests.sessions.Session] = None,
) -> Mapping[str, Any]:
    """Exchange an authorization code for access and refresh tokens."""

    if not code:
        raise ValueError("Authorization code is required.")

    session = session or requests
    response = session.post(
        SPOTIFY_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        auth=HTTPBasicAuth(client_id, client_secret),
        timeout=10,
    )
    return _parse_token_response(response)


def get_client_credentials_token(
    client_id: str,
    client_secret: str,
    *,
    session: Optional[requests.sessions.Session] = None,
) -> str:
    """Request an application access token using the Client Credentials flow."""

    if not client_id or not client_secret:
        raise ValueError("Both client_id and client_secret are required.")

    session = session or requests
    response = session.post(
        SPOTIFY_TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=HTTPBasicAuth(client_id, client_secret),
        timeout=10,
    )
    token_data = _parse_token_response(response)
    token = token_data.get("access_token")
    if not token:
        raise SpotifyAPIError("Spotify token response missing access_token.")
    return str(token)


def fetch_liked_tracks(
    token: str,
    *,
    limit: int = MAX_PAGE_SIZE,
    max_items: Optional[int] = None,
    session: Optional[requests.sessions.Session] = None,
) -> List[TrackMetadata]:
    """Fetch the user's liked tracks and return simplified metadata.

    Args:
        token: Spotify access token with the ``user-library-read`` scope.
        limit: Page size for Spotify queries (max 50).
        max_items: Optional cap on the total number of tracks to return.
        session: Optional ``requests``-compatible session.

    Returns:
        A list of dictionaries, each describing a liked track.
    """

    if not token:
        raise ValueError("A Spotify API token is required to fetch liked tracks.")

    session = session or requests
    headers = {"Authorization": f"Bearer {token}"}
    url = SPOTIFY_LIKED_TRACKS_URL
    params: Mapping[str, Any] = {"limit": min(limit, MAX_PAGE_SIZE)}

    seen: List[TrackMetadata] = []

    while url:
        response = session.get(
            url,
            headers=headers,
            params=params if url == SPOTIFY_LIKED_TRACKS_URL else None,
            timeout=10,
        )
        _ensure_ok(response)
        payload = response.json()

        items: Iterable[Mapping[str, Any]] = payload.get("items", [])
        for item in items:
            track_info = item.get("track")
            if not track_info:
                continue
            seen.append(_simplify_track(track_info))

            if max_items is not None and len(seen) >= max_items:
                return seen[:max_items]

        url = payload.get("next")
        params = {}

    return seen


def _simplify_track(track: Mapping[str, Any]) -> TrackMetadata:
    artists = [
        {"id": artist.get("id"), "name": artist.get("name")}
        for artist in track.get("artists", [])
    ]
    album = track.get("album") or {}
    return {
        "id": track.get("id"),
        "name": track.get("name"),
        "popularity": track.get("popularity"),
        "duration_ms": track.get("duration_ms"),
        "explicit": track.get("explicit"),
        "preview_url": track.get("preview_url"),
        "external_urls": track.get("external_urls"),
        "artists": artists,
        "album": {
            "id": album.get("id"),
            "name": album.get("name"),
            "release_date": album.get("release_date"),
            "total_tracks": album.get("total_tracks"),
            "external_urls": album.get("external_urls"),
        },
    }


def _ensure_ok(response: requests.Response) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:  # pragma: no cover - defensive path
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise SpotifyAPIError(f"Spotify API error: {detail}") from exc


def _parse_token_response(response: requests.Response) -> Mapping[str, Any]:
    _ensure_ok(response)
    try:
        body = response.json()
    except ValueError as exc:  # pragma: no cover - defensive path
        raise SpotifyAPIError("Spotify token response was not valid JSON.") from exc
    if "access_token" not in body:
        raise SpotifyAPIError("Spotify token response missing access_token.")
    return body


