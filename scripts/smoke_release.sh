#!/usr/bin/env bash
#
# Boot the release image against production settings and see whether it works.
#
# **This is not the same check CI already runs.** `manage.py check --deploy` in
# the backend job runs on the GitHub runner, against a virtualenv that has the
# dev dependency set installed and the repository checked out. The release
# image is a different filesystem with a different dependency set, and the
# failure this catches is exactly the one M12 T7 hit: adding `django-csp` to
# pyproject made every test pass and every check clean, and the container then
# died with `ModuleNotFoundError: No module named 'csp'` because the image
# predated the dependency.
#
# So this runs the checks *inside the image*, and then actually starts the
# server, because a settings module that imports cleanly can still be a
# gunicorn config that refuses to bind.
#
# Usage:
#   scripts/smoke_release.sh [image]
#
# The environment below is placeholder, and deliberately so. Every value is
# either a name, a throwaway generated per run, or a host nothing resolves.
# `check --deploy` is a static inspection of settings and the health endpoint
# touches no dependency — neither opens a connection, so nothing here needs to
# be real, and nothing here is a credential.

set -euo pipefail

IMAGE="${1:-e-platform-backend:smoke}"
CONTAINER="e-platform-smoke-$$"
PORT="${SMOKE_PORT:-18000}"

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Generated per run rather than stored. A fixed value here would be a secret in
# version control that also happens not to matter, which is how the habit of
# storing them starts.
SECRET_KEY="$(head -c 40 /dev/urandom | base64 | tr -d '=+/' | head -c 50)"

env_args=(
  -e "DJANGO_SETTINGS_MODULE=config.settings.production"
  -e "DJANGO_SECRET_KEY=${SECRET_KEY}"
  -e "DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1"
  -e "DATABASE_URL=postgres://smoke:smoke@127.0.0.1:5432/smoke"
  -e "REDIS_URL=redis://127.0.0.1:6379/0"
  -e "REDIS_CACHE_URL=redis://127.0.0.1:6379/1"
  -e "MEDIA_STORAGE_ENDPOINT=https://storage.invalid"
  -e "MEDIA_STORAGE_BUCKET=media"
  -e "MEDIA_STORAGE_ACCESS_KEY=not-a-credential"
  -e "MEDIA_STORAGE_SECRET_KEY=not-a-credential"
)

echo "==> Deployment checks, inside ${IMAGE}"
docker run --rm "${env_args[@]}" "$IMAGE" python manage.py check --deploy

echo "==> Every management command this project ships is importable"
# `check` alone does not import management commands. A command with a bad
# import — the pre-deploy step, say — would be discovered by whoever ran it
# during a deploy, which is the worst possible audience.
docker run --rm "${env_args[@]}" "$IMAGE" python manage.py help >/dev/null

echo "==> The server starts and answers"
docker run -d --name "$CONTAINER" -p "${PORT}:8000" "${env_args[@]}" "$IMAGE" >/dev/null

# `X-Forwarded-Proto: https` on every request from here down, because
# production sets `SECURE_SSL_REDIRECT` and `SECURE_PROXY_SSL_HEADER`: TLS
# terminates at the edge and the origin sees plain HTTP, so without the header
# Django 301s everything to https and the smoke check talks to a redirect.
#
# That is not a workaround — it is the same header the edge sends, so this
# also verifies the proxy wiring. The first version of this script omitted it
# and "passed" the wait loop against a 301 with an empty body, because `curl
# -f` does not treat a redirect as a failure.
PROXY_HEADER=(-H "X-Forwarded-Proto: https")

deadline=$((SECONDS + 45))
until curl -fsS "${PROXY_HEADER[@]}" "http://127.0.0.1:${PORT}/healthz" >/dev/null 2>&1; do
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "!! /healthz never answered. Container log:" >&2
    docker logs "$CONTAINER" >&2 || true
    exit 1
  fi
  sleep 2
done

# A 200 is not enough on its own: a proxy or an error page can return one. The
# body is what says this is our health endpoint and not something else.
body="$(curl -fsS "${PROXY_HEADER[@]}" "http://127.0.0.1:${PORT}/healthz")"
case "$body" in
  *'"status"'*'"ok"'*) ;;
  *)
    echo "!! /healthz answered with an unexpected body: ${body}" >&2
    exit 1
    ;;
esac

echo "==> Security headers are present on the running image"
headers="$(curl -fsSI "${PROXY_HEADER[@]}" "http://127.0.0.1:${PORT}/healthz")"
for header in "X-Content-Type-Options" "Content-Security-Policy-Report-Only"; do
  case "$headers" in
    *"$header"*) ;;
    *)
      echo "!! ${header} missing from the running image" >&2
      printf '%s\n' "$headers" >&2
      exit 1
      ;;
  esac
done

echo "==> Plain HTTP is redirected, not served"
# The other half of the header above: if this ever returns 200, the redirect
# has been turned off and every request would be served over plain HTTP at the
# origin. Asserted on the status line rather than the body, because a redirect
# body is empty and an empty body proves nothing.
# Read from the status line rather than `-w '%{http_code}'` with
# `-o /dev/null`. Under Git Bash a native curl receives `/dev/null` as a
# literal path and fails to write to it — the script exits 23 with every stage
# having printed success, which is a confusing way to learn your shell is
# translating paths.
status="$(curl -sSI "http://127.0.0.1:${PORT}/healthz" | head -n 1 | awk '{print $2}')"
case "$status" in
  30*) ;;
  *)
    echo "!! plain HTTP returned ${status}; SECURE_SSL_REDIRECT is not in force" >&2
    exit 1
    ;;
esac

echo "==> Smoke check passed for ${IMAGE}"
