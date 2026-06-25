# Example configs

- `hub.yaml` - hub listening on `127.0.0.1:8888` over TCP, with shared-secret
  token authentication.
- `controller.yaml` - controller dialing the same address/port, with the
  matching token.
- `apply_ctl_settings.sh` - sets the sweep range to 2.4-2.49 GHz at 180
  points, and enables traces 1-3 with calc minh/maxh/aver4, against the
  hub described by `controller.yaml`.

The token in both files is a placeholder. Generate your own and put the
same value in both:

```sh
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## Usage

```sh
tsanet-hub --config hub.yaml &
./apply_ctl_settings.sh
```

Sweep range and trace calc settings are not part of the config file schema
(`tsanet-ctl --config controller.yaml` only carries network/security
settings) - the script above issues the equivalent commands instead.
