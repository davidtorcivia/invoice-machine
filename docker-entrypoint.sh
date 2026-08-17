#!/bin/bash
set -e

# Fix ownership of the data directory if running as root, then drop privileges.
# We re-exec THIS entrypoint (not the CMD directly) so migrations below run as
# the unprivileged appuser.
if [ "$(id -u)" = "0" ]; then
    chown -R appuser:appuser /app/data 2>/dev/null || true
    exec gosu appuser "$0" "$@"
fi

# Apply database migrations before starting the app. `set -e` ensures the
# container fails to start if migrations fail, rather than serving a broken
# schema. Running here (single process) avoids multi-worker migration races.
echo "Running database migrations..."
python -c "from alembic.config import Config; from alembic import command; command.upgrade(Config('alembic.ini'), 'head')"

# uvicorn rewrites request.client from X-Forwarded-For when proxy-headers are
# on. That must track TRUST_PROXY_HEADERS or a client can pick its rate-limit key.
if [ "$1" = "uvicorn" ]; then
    case "${TRUST_PROXY_HEADERS}" in
        1|true|True|TRUE|yes|YES|on|ON)
            set -- "$@" --proxy-headers --forwarded-allow-ips "*"
            ;;
        *)
            set -- "$@" --no-proxy-headers
            ;;
    esac
fi

exec "$@"
