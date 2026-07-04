# Controller configuration reference

Both `tsanet-ctl` (CLI) and `tsanet-gui` read the same config shape and
file. It's validated with [pydantic](https://docs.pydantic.dev/)
(`ControllerConfig` in `src/tsanet/controller/config.py`); an invalid
value fails fast with a clear error.

- Default path: `~/.config/tsanet/controller.yaml`
- Override with: `tsanet-ctl --config /path/to/controller.yaml ...`
  (or `tsanet-gui --config /path/to/controller.yaml`)
- If the file doesn't exist, the controller starts with every field at
  its default (`network.mode: dial`, everything else the same as the hub's
  defaults — see below).
- The GUI's connection dialog can also **write** this file: its Save
  button persists whatever you entered to this same default path (or a
  path you pick), so you don't have to hand-edit YAML just to reconnect
  with the same settings next time.

## Full example

```yaml
# ~/.config/tsanet/controller.yaml
#
# Every field below is optional; the controller falls back to the default
# shown in the comment for anything you omit.

network:
  # Which side establishes the connection. This is the mirror image of the
  # hub's own network.mode:
  #   dial (default for the controller) - connect out to a hub that is
  #                                        listening. The common case.
  #   listen                            - wait for a hub to connect in
  #                                        instead (matches a hub configured
  #                                        with network.mode: dial, e.g. a
  #                                        hub behind NAT dialing out to you).
  mode: dial

  # Transport for the control connection. Must match the hub's transport.
  #   tcp (default) - works across machines/networks.
  #   unix          - a local Unix domain socket; only reachable from the
  #                   same machine as the hub. `address` becomes a socket
  #                   path instead of a host, and `port` is ignored.
  transport: tcp

  # Connect address (mode: dial) or bind address (mode: listen).
  #   For transport: tcp   - the hub's IP/hostname, e.g. 192.168.1.50 or
  #                          127.0.0.1 for a hub on the same machine.
  #   For transport: unix  - the same socket path the hub is listening on,
  #                          e.g. /run/tsanet.sock
  address: 0.0.0.0

  # TCP port. Required when transport is tcp; ignored for unix sockets.
  # Must match the hub's network.port.
  port: 7777
security:
  # Must match the hub's security.mode exactly.
  #   none (default) - no authentication.
  #   token          - present this shared secret to the hub; the
  #                    connection is otherwise unencrypted.
  #   tls-token      - accepted by this config schema, but not yet
  #                    implemented on either side (see hub-config.md).
  mode: none

  # Required when mode is token or tls-token. Must be the exact same
  # value as the hub's security.token.
  token: null

  # Reserved for mode: tls-token (not yet implemented).
  tls_cert: null
  tls_key: null
  tls_ca: null
```

## Field reference

| YAML path | Type | Default | CLI override |
|---|---|---|---|
| `network.mode` | `listen` \| `dial` | `dial` | `--mode` |
| `network.transport` | `tcp` \| `unix` | `tcp` | `--transport` |
| `network.address` | string | `0.0.0.0` | `--address` |
| `network.port` | integer \| `null` | `7777` | `--port` |
| `security.mode` | `none` \| `token` \| `tls-token` | `none` | *(config file only)* |
| `security.token` | string \| `null` | `null` | *(config file only)* |
| `security.tls_cert` | string \| `null` | `null` | *(config file only)* |
| `security.tls_key` | string \| `null` | `null` | *(config file only)* |
| `security.tls_ca` | string \| `null` | `null` | *(config file only)* |

The controller has no `poll_interval` field — this is a hub-only knob (the hub
owns the device connection; the controller only ever talks to the hub over the
network).

`tsanet-ctl` also accepts `--device <id>` to select a specific tinySA when
a hub has more than one attached; this is a per-invocation choice, not
something persisted in the config file.

Full CLI reference: `tsanet-ctl --help`.

## See also

- [`examples/controller.yaml`](../examples/controller.yaml) — a complete,
  runnable example using every field above.
- [Hub configuration reference](hub-config.md) — the matching
  `network`/`security` shape for `tsanet-hub`, plus the hub-only
  `poll_interval` field.
- Top-level [README.md](../README.md#security) for the security-mode
  tradeoffs.
