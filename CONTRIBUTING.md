# Contributing

Contributions to BeeMesh should stay small, clear, and technically honest.

## Setup

```bash
git clone https://github.com/Dhanushenoy/BeeMesh.git
cd BeeMesh
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
```

## Tests

```bash
python -m pytest tests/
```

## Before Opening a PR

- make sure tests pass
- add or update tests when behavior changes
- update docs if user-facing behavior changed
- keep changes focused and readable

For test details, see [docs/testing.md](docs/testing.md).
