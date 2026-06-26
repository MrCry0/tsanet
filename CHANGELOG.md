# Changelog

## [0.2.1] — 2026-06-26

### Fixed

- **Registry lock starvation**: `DeviceRegistry.scan()` held the lock while
  probing serial ports, blocking every other registry access (auto-select,
  device listing) for seconds at a time. Probe serial I/O is now done
  outside the lock.

- **Hub startup latency**: the hub no longer performs a blocking device scan
  before binding its listening socket — it binds and accepts connections
  immediately. Device scanning runs entirely in background.

- **Port discovery scope**: `list_serial_ports()` now filters to
  `/dev/ttyACM*` only, matching the tinySA USB CDC profile. Other serial
  ports are no longer probed.

- **Default log level**: the hub's default `--log-level` was accidentally
  lowered to `warning` in 0.2.0, producing silent startup. Restored to
  `info`.

- **CI formatting**: a pre-existing `ruff format` violation in
  `tests/conftest.py`, `live_graph.py`, and `main_window.py` was fixed
  across all commits.

- **CI Python 3.10 matrix**: removed `--locked` / `--python` flags from
  `uv sync` in CI so PySide6 resolves correctly on Python 3.10.

- **CI missing system libraries**: the `test` job now installs
  `libegl1 libgl1 libopengl0` so PySide6 can load on the headless
  Ubuntu runner.

- **Test resilience**: `test_smoke.py` catches `SystemExit` when PySide6
  is not installed; `test_gui_sweep_warning.py` skips gracefully when the
  GUI imports fail.

## [0.2.0] — 2026-06-25

### Added

- **Verbose and debug logging**: `--verbose` (`-v`, INFO level) and
  `--debug` (DEBUG level) flags on `tsanet-hub`, `tsanet-ctl`, and
  `tsanet-gui`. Per-module loggers trace RPC requests with timing, raw
  serial commands, device discovery, and subscription lifecycle.

- **GUI Log dock**: View > Log in `tsanet-gui` opens a live log panel
  streaming debug output. Opening the panel enables DEBUG capture without
  restarting.

- **GUI help and about dialog**: a Help menu with Usage Guide and About
  tsanet, plus tooltips on all input fields and buttons.

- **GUI token authentication field**: the Connect dialog now includes a
  Token field for token authentication.

- **Trace statistics display**: the GUI stats dialog and
  `tsanet-ctl trace stats` now show channel power, occupied bandwidth
  (99% OBW), PAPR, flatness, and field strength (with antenna factor).

- **CI/CD**: GitHub Actions workflow with Python 3.10/3.12 matrix,
  lint (ruff), and test (pytest). Release workflow builds and publishes
  to PyPI on tag push.

### Changed

- **Core dependencies**: `pyserial>=3.5` and `typer>=0.12` moved from
  optional extras to core, so `pip install tsanet` gives working
  `tsanet-hub` and `tsanet-ctl` without specifying extras. Only
  `PySide6`+`pyqtgraph` remain in the `gui` extra.

- **Entry point resilience**: `tsanet-hub` and `tsanet-ctl` catch
  missing `typer` with a clear install hint, matching the pattern
  `tsanet-gui` already uses for missing `PySide6`.