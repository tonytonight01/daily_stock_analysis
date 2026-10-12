#!/bin/sh
# Run on the target server after Docker Engine and Compose v2 are installed.
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_root"
docker compose version >/dev/null
docker info >/dev/null

umask 077
mkdir -p data logs reports
if [ ! -e data/runtime.env ]; then
    cp docs/examples/tdx-webui-cloud.env.example data/runtime.env
    printf '%s\n' 'Created data/runtime.env. Add the DeepSeek key in Web Settings or on this server.'
fi

docker compose -f docker/docker-compose.cloud.yml up -d --build server
docker compose -f docker/docker-compose.cloud.yml ps
printf '%s\n' 'The Web workspace is starting. Use an SSH tunnel or your HTTPS reverse proxy.'
printf '%s\n' 'First login creates the admin password. Keep data/runtime.env and the data directory private.'
