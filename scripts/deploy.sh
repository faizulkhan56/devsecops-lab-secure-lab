#!/usr/bin/env bash
set -euo pipefail

TEAM_ID="${TEAM_ID:?Error: TEAM_ID is required (e.g., team-01)}"
TEAM_NUM="${TEAM_ID##*-}"
APP_DIR="/opt/teams/${TEAM_ID}/app"
APP_PORT="80${TEAM_NUM}"

echo "============================================"
echo "Deploying ${TEAM_ID}"
echo "  Directory: ${APP_DIR}"
echo "  Port:      ${APP_PORT}:5000"
echo "============================================"

mkdir -p "${APP_DIR}"
cd "${APP_DIR}"

export APP_PORT

if [[ -n "${GIT_SHA:-}" ]]; then
    export APP_VERSION="${GIT_SHA}"
    export IMAGE_TAG="${GIT_SHA}"
fi

echo "Checking deployment files..."
test -f docker-compose.yml || { echo "ERROR: docker-compose.yml not found in ${APP_DIR}"; exit 1; }
test -f .env || { echo "ERROR: .env not found in ${APP_DIR}"; exit 1; }

echo "Pulling latest images..."
docker compose pull

echo "Starting services..."
docker compose up -d --remove-orphans

echo "Running containers:"
docker compose ps

echo ""
echo "Waiting for application to start..."
sleep 5

echo "Checking health endpoint..."
if curl -sf "http://localhost:${APP_PORT}/api/health"; then
    echo ""
    echo "============================================"
    echo "Deployment successful!"
    echo "Health: http://localhost:${APP_PORT}/api/health"
    echo "============================================"
else
    echo ""
    echo "============================================"
    echo "ERROR: Health check failed!"
    echo "Check logs: cd ${APP_DIR} && docker compose logs"
    echo "============================================"
    exit 1
fi