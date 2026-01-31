#!/bin/bash

# Spin up Docker containers
docker compose -f docker-compose.local.yml --env-file .env.local up -d

# Run the main application
uv run main.py