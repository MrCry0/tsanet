# Hub configuration reference

The hub (`tsanet-hub`) reads a YAML file at startup and merges it with any
CLI flags — flags always win. Values are validated with
[pydantic](https://docs.pydantic.dev/) (`HubConfig` in
`src/tsanet/hub/config.py`); an invalid value fails fast with a clear error
instead of starting the hub in a broken state.

- Default path: `~/.config/tsanet/hub.yaml`
- Override with: `tsanet-hub --config /path/to/hub.yaml`
- If the file doesn't exist, the hub starts with every field at its default
  and logs `no config file found at ..., using defaults`.

## Full example

```yaml
# ~/.config/tsanet/hub.yaml
#
# Every field below is optional; the hub falls back to the default shown
# in the comment for anything you omit. This file only needs the fields
# you actually want to change from their defaults.

network:
  # Which side establishes the TCP/Unix connection.
  #   listen (default) - the hub binds and waits for a controller to connect.
  #                       Use this for the common case: hub on the same
  #                       machine as (or reachable from) the controller.
  #   dial              - the hub connects out to a controller that is
  #                       itself listening. Useful when the hub is behind
  #                       NAT/a firewall and can't accept inbound
  #                       connections, but can reach the controller's
  #                       machine outbound.
  mode: listen

  # Transport for the control connection.
  #   tcp (default) - works across machines/networks.
  #   unix          - a local Unix domain socket; only reachable from the
  #                   same machine. `address` becomes a socket path instead
  #                   of a host, and `port` is ignored.
  transport: tcp

  # Bind address (mode: listen) or connect address (mode: dial).
  #   For transport: tcp   - an IP/hostname. 0.0.0.0 (default) binds all
  #                          interfaces; use 127.0.0.1 to only accept local
  #                          connections (e.g. a GUI on the same machine).
  #   For transport: unix  - a filesystem path to the socket, e.g.
  #                          /run/tsanet.sock
  address: 0.0.0.0

  # TCP port. Required when transport is tcp; ignored for unix sockets.
  port: 7777

security:
  # Authentication for the control connection.
  #   none (default) - no authentication. Fine for a unix socket, or a tcp
  #                    bind restricted to 127.0.0.1. tsanet warns at
  #                    startup if you bind non-loopback tcp with mode: none.
  #   token          - a shared secret the controller must present; the
  #                    connection is otherwise unencrypted (see the
  #                    ## Security section of the top-level README).
  #   tls-token      - token auth over TLS. Accepted by this config schema,
  #                    but the hub currently refuses to start with mode:
  #                    tls-token, since the TLS transport isn't implemented
  #                    yet. Use token or none until it lands.
  mode: none

  # Required when mode is token or tls-token. Generate one with:
  #   python3 -c "import secrets; print(secrets.token_hex(32))"
  # Must match the same token in the controller's config.
  token: null

  # Reserved for mode: tls-token (not yet implemented). Paths to a PEM
  # certificate, its private key, and (optionally) a CA bundle to verify
  # the peer against.
  tls_cert: null
  tls_key: null
  tls_ca: null

# Seconds between device hotplug rescans -- how quickly the hub notices a
# tinySA being plugged in or unplugged. Lower values notice hotplug events
# faster at the cost of more frequent serial-port probing.
poll_interval: 2.0

## Field reference

| YAML path | Type | Default | CLI override |
|---|---|---|---|
| `network.mode` | `listen` \| `dial` | `listen` | `--mode` |
| `network.transport` | `tcp` \| `unix` | `tcp` | `--transport` |
| `network.address` | string | `0.0.0.0` | `--address` |
| `network.port` | integer \| `null` | `7777` | `--port` |
| `security.mode` | `none` \| `token` \| `tls-token` | `none` | *(config file only)* |
| `security.token` | string \| `null` | `null` | *(config file only)* |
| `security.tls_cert` | string \| `null` | `null` | *(config file only)* |
| `security.tls_key` | string \| `null` | `null` | *(config file only)* |
| `security.tls_ca` | string \| `null` | `null` | *(config file only)* |
| `poll_interval` | float (seconds) | `2.0` | `--poll-interval` |

Full CLI reference: `tsanet-hub --help`.

## See also

- [`examples/hub.yaml`](../examples/hub.yaml) — a complete, runnable example
  using every field above.
- [Controller configuration reference](controller-config.md) — the
  matching `network`/`security` shape for `tsanet-ctl`/`tsanet-gui`.
- Top-level [README.md](../README.md#security) for the security-mode
  tradeoffs (`none` vs `token` vs the not-yet-implemented `tls-token`).
