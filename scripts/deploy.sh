#! /usr/bin/env sh

# LEGACY: Docker Swarm deploy, superseded by deploy/terraform + docker-compose.prod.yml.
# Kept for reference only; not part of the current OVH/Terraform deployment path.

# Exit in case of error
set -e

DOMAIN=${DOMAIN?Variable not set} \
STACK_NAME=${STACK_NAME?Variable not set} \
TAG=${TAG?Variable not set} \
docker-compose \
-f docker-compose.yml \
config > docker-stack.yml

docker-auto-labels docker-stack.yml

docker stack deploy -c docker-stack.yml --with-registry-auth "${STACK_NAME?Variable not set}"
