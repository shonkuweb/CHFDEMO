#!/bin/sh
set -e

# Ensure persistent data directories exist.
mkdir -p /app/data/uploads

# Seed database into persistent volume on first boot.
if [ ! -f "${DB_PATH:-/app/data/chf_archive.db}" ] && [ -f /app/chf_archive.db ]; then
  cp /app/chf_archive.db "${DB_PATH:-/app/data/chf_archive.db}"
fi

exec "$@"
