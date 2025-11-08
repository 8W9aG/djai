# djai

Utilities for building Django-based AI integrations.

## Development

Create a virtual environment and install the project in editable mode with its development dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

Run linters and tests locally:

```bash
ruff check .
pytest
```

## Continuous Integration

GitHub Actions runs linting (`ruff`) and tests (`pytest`) on pushes and pull requests targeting `main`. The workflow lives in `.github/workflows/ci.yml`.

## Publishing to PyPI

Releasing is handled by `.github/workflows/deploy.yml`. Trigger the **Publish** workflow manually from GitHub and provide the version you intend to release. Before the workflow runs, ensure:

- `pyproject.toml` has been updated with the desired version.
- A PyPI API token is stored in the repository secrets as `PYPI_API_TOKEN`.

The workflow builds the package and uploads the artifacts to PyPI using `twine`.
