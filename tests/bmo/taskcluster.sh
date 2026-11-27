#!/bin/bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

# Run the rule scenarios in a Taskcluster task (see .taskcluster.yml): start a
# Docker daemon in the task's container (which needs to be privileged), then
# the local BMO, and run the tests that need it.
#
# Run from the root of the repository, in a Debian container.

set -euxo pipefail

apt-get update -qq
apt-get install -y -qq --no-install-recommends docker.io docker-cli fuse-overlayfs curl ca-certificates

# Debian's Docker Compose (2.26) doesn't support the `service:` build contexts
# of tests/bmo/docker-compose.yml.
COMPOSE_VERSION=2.35.1
COMPOSE_SHA256=7bdb2ce2916e5dd0354e5d129892bf96fdcdb1a9ab8eed69b9173e131db4c230
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL -o /usr/local/lib/docker/cli-plugins/docker-compose \
  "https://github.com/docker/compose/releases/download/v${COMPOSE_VERSION}/docker-compose-linux-x86_64"
echo "${COMPOSE_SHA256}  /usr/local/lib/docker/cli-plugins/docker-compose" | sha256sum --check
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
docker compose version

# The task's container is on an overlay filesystem, which overlay2 can't use.
dockerd --storage-driver=fuse-overlayfs > /tmp/dockerd.log 2>&1 &
for _ in $(seq 60); do
  docker info > /dev/null 2>&1 && break
  sleep 1
done
docker info --format 'Docker {{.ServerVersion}}, storage driver: {{.Driver}}'

mkdir -p /tmp/bugbot-bmo
echo "+0" > /tmp/bugbot-bmo/faketime
docker compose -f tests/bmo/docker-compose.yml up --detach --build

uv sync --quiet --locked --extra dev
status=0
BUGBOT_REQUIRE_BMO=1 uv run pytest -v tests/test_scenarios.py tests/test_scenario_framework.py || status=$?
if [ "$status" != 0 ]; then
  docker compose -f tests/bmo/docker-compose.yml logs --tail 200
fi
exit "$status"
