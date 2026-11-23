#!/bin/sh
set -eu
version=$(caddy version)
export KASSE_CADDY_RUNTIME="${version%% *}"
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
