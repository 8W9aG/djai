from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional

import pytest

from djai.spotify import (
    MAX_PAGE_SIZE,
    SpotifyAPIError,
    exchange_authorization_code,
    fetch_liked_tracks,
    get_client_credentials_token,
)


class StubResponse:
    def __init__(self, json_data: Mapping[str, Any], status_code: int = 200) -> None:
        self._json_data = json_data
        self.status_code = status_code
        self.text = str(json_data)

    def json(self) -> Mapping[str, Any]:
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise ValueError("HTTP error")


class StubSession:
    def __init__(self, responses: Iterable[StubResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[Dict[str, Any]] = []

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Optional[Mapping[str, Any]] = None,
        timeout: Optional[int] = None,
    ) -> StubResponse:
        self.calls.append({"url": url, "headers": headers, "params": params, "timeout": timeout})
        if not self._responses:
            raise RuntimeError("No more stub responses configured")
        return self._responses.pop(0)


class TokenSession:
    def __init__(self, response: StubResponse) -> None:
        self._response = response
        self.calls: list[Dict[str, Any]] = []

    def post(
        self,
        url: str,
        *,
        data: Mapping[str, Any],
        auth: Any,
        timeout: Optional[int] = None,
    ) -> StubResponse:
        self.calls.append({"url": url, "data": data, "auth": auth, "timeout": timeout})
        return self._response


def test_fetch_liked_tracks_collects_metadata() -> None:
    first_page = {
        "items": [
            {
                "track": {
                    "id": "track-1",
                    "name": "Track One",
                    "popularity": 80,
                    "duration_ms": 210000,
                    "explicit": False,
                    "preview_url": "https://example.com/preview1",
                    "external_urls": {"spotify": "https://spotify.com/track1"},
                    "artists": [
                        {"id": "artist-1", "name": "Artist One"},
                    ],
                    "album": {
                        "id": "album-1",
                        "name": "Album One",
                        "release_date": "2024-01-01",
                        "total_tracks": 10,
                        "external_urls": {"spotify": "https://spotify.com/album1"},
                    },
                }
            }
        ],
        "next": None,
    }
    session = StubSession([StubResponse(first_page)])

    tracks = fetch_liked_tracks("token", session=session)

    assert len(tracks) == 1
    track = tracks[0]
    assert track["name"] == "Track One"
    assert track["artists"][0]["name"] == "Artist One"
    assert session.calls[0]["params"]["limit"] == MAX_PAGE_SIZE


def test_fetch_liked_tracks_respects_max_items() -> None:
    first_page = {
        "items": [
            {"track": {"id": "a", "name": "A", "artists": [], "album": {}}},
            {"track": {"id": "b", "name": "B", "artists": [], "album": {}}},
        ],
        "next": "https://next",
    }
    second_page = {
        "items": [
            {"track": {"id": "c", "name": "C", "artists": [], "album": {}}},
        ],
        "next": None,
    }
    session = StubSession([StubResponse(first_page), StubResponse(second_page)])

    tracks = fetch_liked_tracks("token", max_items=2, session=session)

    assert len(tracks) == 2
    assert [t["id"] for t in tracks] == ["a", "b"]
    assert len(session.calls) == 1


def test_fetch_liked_tracks_raises_without_token() -> None:
    with pytest.raises(ValueError):
        fetch_liked_tracks("")


def test_get_client_credentials_token_returns_access_token() -> None:
    session = TokenSession(StubResponse({"access_token": "abc"}))

    token = get_client_credentials_token("id", "secret", session=session)

    assert token == "abc"
    assert session.calls[0]["data"]["grant_type"] == "client_credentials"


def test_get_client_credentials_token_requires_access_token() -> None:
    session = TokenSession(StubResponse({}))

    with pytest.raises(SpotifyAPIError):
        get_client_credentials_token("id", "secret", session=session)


def test_exchange_authorization_code_returns_tokens() -> None:
    session = TokenSession(StubResponse({"access_token": "abc", "refresh_token": "ref"}))

    tokens = exchange_authorization_code(
        "id",
        "secret",
        "code",
        redirect_uri="http://localhost/callback",
        session=session,
    )

    assert tokens["access_token"] == "abc"
    assert tokens["refresh_token"] == "ref"
    assert session.calls[0]["data"]["grant_type"] == "authorization_code"


def test_exchange_authorization_code_requires_access_token() -> None:
    session = TokenSession(StubResponse({}))

    with pytest.raises(SpotifyAPIError):
        exchange_authorization_code(
            "id",
            "secret",
            "code",
            redirect_uri="http://localhost/callback",
            session=session,
        )

