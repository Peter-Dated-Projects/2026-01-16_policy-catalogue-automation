#!/bin/bash

# Display help message
show_help() {
    echo "Usage: ./clean.sh [OPTIONS]"
    echo ""
    echo "Stop and clean up Docker containers for PCA."
    echo ""
    echo "Options:"
    echo "  -h, --help        Show this help message"
    echo "  --deep-clean      Stop containers AND remove all volumes (postgres-data, arangodb-data, minio-data)"
    echo "                    WARNING: This will permanently delete all database data and object storage!"
    echo ""
    echo "Examples:"
    echo "  ./clean.sh                  # Stop containers only"
    echo "  ./clean.sh --deep-clean     # Stop containers and remove all data volumes"
}

# Check for help flag
if [[ "$1" == "-h" || "$1" == "--help" || "$1" == "help" ]]; then
    show_help
    exit 0
fi

# Stop Docker containers
echo "Stopping Docker containers..."
docker compose -f docker-compose.local.yml --env-file .env.local down

# Check for deep-clean flag
if [[ "$1" == "--deep-clean" ]]; then
    echo ""
    echo "⚠️  WARNING: Deep clean will permanently delete all data!"
    read -p "Are you sure you want to remove all volumes? (yes/no): " confirmation
    
    if [[ "$confirmation" == "yes" ]]; then
        echo "Removing Docker volumes..."
        docker compose -f docker-compose.local.yml --env-file .env.local down -v
        echo "✓ Deep clean completed. All containers and volumes removed."
    else
        echo "Deep clean cancelled. Volumes preserved."
    fi
else
    echo "✓ Containers stopped. Volumes preserved."
    echo "Run with --deep-clean to also remove volumes."
fi
