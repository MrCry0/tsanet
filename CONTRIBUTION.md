# Contributing to tsanet

Thank you for your interest in contributing.

## Getting started

### Prerequisites

- Python 3.10 or later
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Fork and clone

```sh
git clone https://github.com/YOUR_USERNAME/tsanet.git
cd tsanet
git remote add upstream https://github.com/MrCry0/tsanet.git
```

### Development environment

```sh
uv sync                    # core + dev tools (pytest, ruff, twine)
uv sync --extra gui        # add GUI deps (PySide6, pyqtgraph)
```

This creates `.venv` with the package installed in editable mode. The dev
dependency group (pytest, ruff, twine) is installed automatically by
`uv sync`.

### Running from source (no install needed)

Wrapper scripts at the repo root run each program directly:

```sh
python tsanet-hub.py --port 7777
python tsanet-ctl.py --address 127.0.0.1 --port 7777 devices list
python tsanet-gui.py
```

These auto-detect `.venv` and re-exec under it, so virtualenv activation
is not required.

## Development workflow

### Code style

Format and lint with ruff:

```sh
uv run ruff check .
uv run ruff format .
```

The project uses ruff exclusively for both formatting and linting.
Configuration is in `pyproject.toml` — 100-character line length,
Python 3.10 target.

### Running tests

```sh
uv run pytest                          # core + device tests
uv run --extra gui pytest              # including GUI tests
uv run pytest tests/test_hardware.py --run-hardware  # requires real tinySA
```

Tests that import `PySide6` or `pyqtgraph` will skip cleanly when the
`gui` extra is not installed. The `--run-hardware` flag is required for
hardware tests — without it they skip automatically.

### Writing tests

- **`tests/conftest.py`** provides `FakeSerial` — an in-memory serial
  port that lets you script a device's responses. Use it to write
  deterministic tests without hardware.
- **`tests/fakeserial.py`** provides `FakeSerial` (scripted serial
  transport) and `FakeDevicePort` (fake tinySA responder).
- Hardware tests live in `tests/test_hardware.py` and must be decorated
  with the `--run-hardware` marker.

## Commit conventions

### Subject line

```
subsystem: short description of the change
```

- Use imperative mood: "add", "fix", "remove" — not "added", "fixes".
- 72 characters maximum. No trailing period.
- The subsystem prefix identifies the component most affected
  (e.g. `hub:`, `controller:`, `gui:`, `device:`, `ci:`, `docs:`).

### Body

- Separate from the subject with one blank line.
- Explain *why* the change is needed, not what the diff already shows.
- Wrap lines at 72 characters.

### Sign-off

All commits must be signed off:

```sh
git commit -s
```

This appends the `Signed-off-by` trailer automatically.

### Examples

```
hub: reduce registry lock contention during device scan

Probing serial ports while holding the registry lock blocked every
other access (auto-select, device listing) for seconds at a time.
Do the serial I/O outside the lock so the hub remains responsive
during background scans.

Signed-off-by: Your Name <your@email>
```

```
gui: use non-native file dialogs to avoid hangs on Linux

Qt's native file dialogs can deadlock on some Linux desktop
environments when called from a non-main thread or during an event
loop cycle. Switching to Qt's non-native dialogs resolves this.

Signed-off-by: Your Name <your@email>
```

### Branch naming

Work in a topic branch branched from `main`:

```
feature/my-feature
fix/fix-description
```

## Pull request process

1. Create a topic branch from `main`.
2. Make your changes, following the code style and commit conventions.
3. Run `uv run ruff check . && uv run ruff format --check .` to ensure
   formatting and lint pass.
4. Run `uv run pytest` to ensure all tests pass.
5. Push your branch and open a pull request against `main`.
6. CI will run the test matrix (Python 3.10, 3.12) and lint checks.
7. Maintainers will review. Address feedback in follow-up commits rather
   than force-pushing — this makes review easier.
8. Once approved, a maintainer will merge.

## Release process

Releases are cut by maintainers when changes on `main` are ready for a
new version.

1. Ensure the changelog in `CHANGELOG.md` is up to date.
2. Update `__version__` in `src/tsanet/__init__.py`.
3. Verify the build: `uv build && uv run twine check dist/*`
4. Create an annotated tag:
   ```sh
   git tag -s v$(uv run python -c "import tsanet; print(tsanet.__version__)") -m "tsanet v$(uv run python -c "import tsanet; print(tsanet.__version__)")"
   ```
5. Push the tag: `git push upstream vX.Y.Z`
6. GitHub Actions will build the distribution, verify the tag matches the
   package version, and publish to PyPI.

## License

By contributing, you agree that your contributions will be licensed under
the GPL-2.0-only license used by this project.
