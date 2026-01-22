#!/bin/bash
set -e

# Fix ownership of data directory if running as root
# This handles cases where the mounted volume has different ownership
if [ "$(id -u)" = "0" ]; then
    # Ensure data directory and all contents are writable by appuser
    chown -R appuser:appuser /app/data 2>/dev/null || true

    # Re-exec as appuser
    exec gosu appuser "$@"
fi

# If not root, just run the command directly
exec "$@"
