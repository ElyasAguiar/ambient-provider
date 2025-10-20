#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Restart production containers to apply audio playback fixes
# This script should be run from the ambient-scribe directory

set -e

echo "Restarting production containers to apply audio playback fixes..."

# Navigate to the infra directory
cd "$(dirname "$0")/../infra"

# Stop and remove existing containers
echo "Stopping existing containers..."
docker compose -f compose.prod.yml down

# Rebuild nginx container to pick up configuration changes
echo "Rebuilding nginx container with updated configuration..."
docker compose -f compose.prod.yml build nginx

# Start all services
echo "Starting production services..."
docker compose -f compose.prod.yml up -d

# Wait for services to be healthy
echo "Waiting for services to be healthy..."
sleep 10

# Check service status
echo "Checking service status..."
docker compose -f compose.prod.yml ps

echo "Production restart complete!"
echo ""
echo "Audio playback should now work in the Docker deployment."
echo ""
echo "To test:"
echo "1. Access your application at https://localhost:443 (or your configured domain)"
echo "2. Upload an audio file for transcription"
echo "3. Verify that the audio player can play the uploaded file"
echo ""
echo "If you're still experiencing issues, check the logs with:"
echo "  docker compose -f compose.prod.yml logs nginx"
echo "  docker compose -f compose.prod.yml logs api"
