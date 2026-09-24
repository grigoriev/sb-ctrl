#!/usr/bin/env bash
# Smoke test of a built sb-ctrl image: start it with a token config, then check
# /health and the token check on /config. No seedbox, TMDb or Plex is needed.
#
# Usage: tests/smoke-image.sh <image>    (needs Docker and curl)
# CI runs it on every pull request, and docker-publish.yml on the image it pushes.
# SMOKE_PORT sets the local port, default 18765.
set -euo pipefail

cd "$(dirname "$0")/.."

IMAGE="${1:?usage: tests/smoke-image.sh <image>}"
SMOKE_PORT="${SMOKE_PORT:-18765}"
BASE="http://127.0.0.1:${SMOKE_PORT}"
TOKEN="smoke-$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')"
NAME="sb-ctrl-smoke-$$"
SMOKE_DIR="$(mktemp -d)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' sb_ctrl/__init__.py)"
[ -n "$VERSION" ] || { echo "FAIL: no __version__ in sb_ctrl/__init__.py" >&2; exit 1; }

failed=0
cleanup() {
  if [ "$failed" -ne 0 ]; then
    echo "--- container logs ---"
    docker logs "$NAME" 2>&1 || true
  fi
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  rm -rf "$SMOKE_DIR" 2>/dev/null || true
}
trap cleanup EXIT

fail() {
  failed=1
  echo "FAIL: $*" >&2
  exit 1
}

pass() {
  echo "ok: $*"
}

# The API refuses to start without authentication. A token is enough.
cat > "$SMOKE_DIR/config.toml" <<EOF
[api]
host  = "0.0.0.0"
port  = 8765
token = "$TOKEN"
EOF
chmod 644 "$SMOKE_DIR/config.toml"

# Run the image on its own platform: an amd64 image on an arm64 host then
# prints no warning. A pulled multi-arch image can report no platform.
platform=()
os_arch="$(docker image inspect -f '{{.Os}}/{{.Architecture}}' "$IMAGE")" || fail "no image $IMAGE"
[ "$os_arch" = / ] || platform=(--platform "$os_arch")
docker run -d --name "$NAME" ${platform[@]+"${platform[@]}"} \
  -p "127.0.0.1:${SMOKE_PORT}:8765" \
  -v "$SMOKE_DIR/config.toml:/config/config.toml:ro" \
  "$IMAGE" >/dev/null || fail "container did not start"

# GET <path> [curl args...]: prints the body, then the status code on the last line.
get() {
  local path="$1"
  shift
  curl -sS --max-time 10 -w '\n%{http_code}' "$@" "${BASE}${path}"
}

for _ in $(seq 1 60); do
  if out="$(get /health 2>/dev/null)" && [ "${out##*$'\n'}" = 200 ]; then
    break
  fi
  [ "$(docker inspect -f '{{.State.Running}}' "$NAME")" = true ] || fail "container exited"
  sleep 1
done

check() {
  local name="$1" path="$2" want_code="$3" want_body="$4"
  shift 4
  local out code body
  out="$(get "$path" "$@")" || fail "$name: request failed"
  code="${out##*$'\n'}"
  body="${out%$'\n'*}"
  [ "$code" = "$want_code" ] || fail "$name: HTTP $code, want $want_code. Body: $body"
  case "$body" in
    *"$want_body"*) ;;
    *) fail "$name: body lacks '$want_body'. Body: $body" ;;
  esac
  pass "$name"
}

check "health answers ok" /health 200 '"ok":true'
check "health reports version $VERSION" /health 200 "\"version\":\"$VERSION\""
check "config rejects a request without a token" /config 401 'unauthorized'
check "config rejects a wrong token" /config 401 'unauthorized' -H "Authorization: Bearer wrong"
check "config accepts the token" /config 200 '"api_port"' -H "Authorization: Bearer $TOKEN"

out="$(get /config -H "Authorization: Bearer $TOKEN")"
case "$out" in
  *"$TOKEN"*) fail "config leaks the token" ;;
esac
pass "config redacts the token"

echo "smoke test passed: $IMAGE"
