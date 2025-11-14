# djai

Tools for DJ ideation powered by AI/ML. The package ships with a command-line interface that helps you analyse your Spotify likes so you can feed curated metadata into downstream machine-learning workflows.

## Command Line Interface

Ensure you have a Spotify access token with the `user-library-read` scope. You can either pass it as a flag or export it as an environment variable:

```bash
export SPOTIFY_API_TOKEN="your-spotify-token"
djai --max-items 100 > liked_tracks.json
```

Key flags:

- `--token`: Provide the Spotify token directly (defaults to `SPOTIFY_API_TOKEN`).
- `--limit`: Batch size per API call (max 50; defaults to 50).
- `--max-items`: Optional cap on total tracks to fetch.

The CLI calls Spotify's `/v1/me/tracks` endpoint, caches responses, downloads MP3 previews via [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) (requires `ffmpeg`), falls back to a YouTube search when Spotify doesn't expose a preview URL, and runs [`demucs`](https://github.com/facebookresearch/demucs) to separate stems (cached under `.djai_cache/stems`). Demucs also needs the [`diffq`](https://pypi.org/project/diffq/) package; install it alongside Demucs. The command prints the total number of liked tracks retrieved.

### `.env` Support

Store secrets in a `.env` file to keep them out of your shell history:

```
SPOTIFY_CLIENT_ID="your-client-id"
SPOTIFY_CLIENT_SECRET="your-client-secret"
SPOTIFY_API_TOKEN="your-spotify-token"
```

The CLI automatically loads `.env` from the current working directory (or parent directories) using [`python-dotenv`](https://github.com/theskumar/python-dotenv). If an explicit API token is missing but client credentials are configured, `djai` launches a one-time Authorization Code flow using a temporary localhost listener to obtain fresh `access_token` and `refresh_token` values before fetching tracks. The resulting tokens are cached in `.djai_session` (ignored by git) so subsequent runs in the same directory reuse them. Downloaded previews are stored under `.djai_cache/audio`, and API responses are cached under `.djai_cache` for up to 30 days. Note that analysing a user's liked tracks still requires a token granted with the `user-library-read` scope.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
ruff check .
pytest
```

## Continuous Integration

GitHub Actions runs linting (`ruff`) and tests (`pytest`) on pushes and pull requests targeting `main` via `.github/workflows/ci.yml`.

## Publishing to PyPI

The manual **Publish** workflow in `.github/workflows/deploy.yml` builds and uploads the package. Before triggering it, bump the version in `pyproject.toml` and ensure a PyPI token is stored as `PYPI_API_TOKEN`.
