# Deploying sb-ctrl

sb-ctrl runs on the Plex host (`beaver.h.g7v.io`) as a systemd user service
behind a Caddy reverse proxy that terminates TLS. The host is reachable only on
the LAN and VPN.

## 1. Install

```sh
python3 -m venv ~/.local/sb-ctrl-venv
~/.local/sb-ctrl-venv/bin/pip install "sb-ctrl @ git+https://github.com/grigoriev/sb-ctrl"
# or, from a checkout:  pip install .
```

Requires Python 3.14+ and `lftp` on the host.

## 2. Configure

```sh
mkdir -p ~/.config/sb-ctrl
cp config.example.toml ~/.config/sb-ctrl/config.toml
chmod 600 ~/.config/sb-ctrl/config.toml
$EDITOR ~/.config/sb-ctrl/config.toml     # fill every CHANGE_ME
```

Generate the API token with `openssl rand -hex 32`. `staging_root` must be on the
same filesystem as the library roots so the final `mv` is atomic.

## 3. systemd user service

`~/.config/systemd/user/sb-ctrl.service`:

```ini
[Unit]
Description=sb-ctrl REST API
After=network-online.target

[Service]
ExecStart=%h/.local/sb-ctrl-venv/bin/sb-ctrl serve
Restart=on-failure

[Install]
WantedBy=default.target
```

```sh
loginctl enable-linger "$USER"        # keep the service (and transfer units) alive without a login
systemctl --user daemon-reload
systemctl --user enable --now sb-ctrl
systemctl --user status sb-ctrl
journalctl --user -u sb-ctrl -f
```

Transfers run as transient `systemd-run --user` units, so `enable-linger` is what
lets them survive a service restart and logout.

## 4. TLS with Caddy (Let's Encrypt DNS-01)

The host is not publicly reachable, so the HTTP-01 challenge cannot work. Caddy
solves an ACME **DNS-01** challenge instead, which only needs API access to the
`g7v.io` DNS zone. Install a Caddy build with your DNS provider's plugin
(`xcaddy build --with github.com/caddy-dns/<provider>`; provider `[TBD]` -
Cloudflare, Route53, deSEC, etc.).

`/etc/caddy/Caddyfile`:

```caddyfile
beaver.h.g7v.io {
    tls {
        dns <provider> {env.DNS_API_TOKEN}
    }
    reverse_proxy 127.0.0.1:8765
}
```

Provide the provider credential to Caddy (e.g. `DNS_API_TOKEN` in
`/etc/caddy/caddy.env` referenced from the systemd unit), then
`systemctl reload caddy`. Caddy obtains and renews the certificate automatically.

## 5. Point the client at it

In the Alfred workflow: `seedbox >` -> Set API URL (`https://beaver.h.g7v.io`)
and Set API token (the value from the config). Verify with:

```sh
curl -s https://beaver.h.g7v.io/health
curl -s -H "Authorization: Bearer <token>" https://beaver.h.g7v.io/torrents | jq .
```

`GET /docs` serves the OpenAPI schema (useful for the future React client).
