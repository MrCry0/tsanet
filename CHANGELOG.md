# Changelog

## [Unreleased]

### Added

- **Attenuator, RBW, and trigger mode control**: end-to-end from the device
  layer through the dispatcher, `tsanet-ctl signal attenuate` / `sweep rbw` /
  `sweep trigger`, and the GUI's Spectrum tab.
- **Client-side trace hold modes**: the Spectrum tab's up to 4 trace slots
  can each independently show Live, Min hold, Max hold, or a rolling
  Average, computed locally from the single `scanraw` stream.
- **Marker controls in the GUI**: 2 markers with frequency entry, peak
  search, live amplitude readout, and delta between them.
- **Reference level, scale, auto-range Y, and waterfall depth** controls in
  the Spectrum tab's Display group.
- **Single-shot capture** button alongside the existing Start/Stop.
- **Trace statistics dialog** is reachable from the GUI again, via a
  "Stats..." button on the Spectrum tab.

### Fixed

- The sweep device-clamp warning (e.g. a 900-point request capped to 450)
  is now surfaced consistently by both `tsanet-ctl` and the GUI; previously
  the CLI had its own duplicate implementation and the GUI's Spectrum tab
  had no warning at all after the Sweep tab was folded into it.

### Removed

- `live_graph.py`, superseded by the Spectrum tab's waterfall.

## [0.3.1] — 2026-07-01

### Fixed

- **Capture payload off-by-one**: tsapython's `capture()` can return one byte
  short of the expected RGB565 framebuffer size (307199 instead of 307200 for
  the 480x320 Ultra display). The adapter now pads the payload to the expected
  length, logging a warning, so screenshots work reliably.

## [0.3.0] — 2026-07-01

### Changed

- **Device layer replaced with tsapython**:
  the hand-ported go-tinysa protocol layer is replaced by the
  [tsapython](https://github.com/LC-Linkous/tinySA_python) library
  (PyPI: [tsapython>=3](https://pypi.org/project/tsapython/)).
  The new `TinySA` adapter in `device/adapter.py` wraps tsapython's
  `tinySA` class while preserving the existing `send()` /
  `send_binary()` / `write_only()` contract so the hub command layer
  and dispatcher require no changes.
  The legacy transport is retained as `device/_legacy.py` for the
  in-memory `FakeSerial` test infrastructure.

## [0.2.2] — 2026-06-30

### Added

- **Lazy hub connection**: `tsanet-ctl` no longer connects to the hub in
  the root callback. CLI options are stored and the RPC connection opens
  only when a command first needs it, so `--help` and argument validation
  complete before any network I/O.

- **Command help on input errors**: invalid arguments (bad frequency,
  wrong mode, unknown calc type) now print the full command reference
  listing every parameter with its help text and required status.

- **Enum validation for CLI parameters**: network mode, transport, spur
  suppression, LNA, trace unit, and calc type now use Typer's native
  enum validation. Invalid values show all valid choices directly in
  the error message.

- **`-L` / `--devices-list` flag alias**: listing devices is now also
  available as a top-level global option, not just the `devices-list`
  command.

- **CONTRIBUTION.md**: contributor guide covering development setup,
  code style, commit conventions, and the release process.

### Changed

- **`devices list` promoted to `devices-list` command**: the single
  subcommand group is now a top-level command with no nesting.

- **`device id --set N` changed to `device id [N]`**: the new device ID
  is now an optional positional argument instead of a value-taking option.

- **`sweep range --points N` changed to `sweep range [POINTS]`**: the
  point count is now an optional third positional argument.

- **Option naming harmonized**: `marker.get --marker/-m` and
  `trace.get --trace/-t` now use domain-consistent option names.

- **Help text unified**: frequency arguments across sweep, marker, and
  trace commands now consistently show examples in their help text.

### Fixed

- **Battery command resilience**: `device battery` no longer crashes when
  a sub-command is unsupported by the connected firmware. Each call is
  independently guarded and reports `"unsupported by this firmware"`.

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