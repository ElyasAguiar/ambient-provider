#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Validate environment configuration for Ambient Scribe

echo "Validating environment configuration..."

ENV_FILE="apps/api/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: .env file not found at $ENV_FILE"
    echo "Run: make env"
    exit 1
fi

# Check for placeholder values
if grep -q "your_nvidia_api_key_here" "$ENV_FILE"; then
    echo "ERROR: NVIDIA_API_KEY is still a placeholder"
    echo "Update $ENV_FILE with your actual NVIDIA API key"
    exit 1
fi

# Check RIVA URI
RIVA_URI=$(grep "RIVA_URI=" "$ENV_FILE" | cut -d= -f2)
echo "RIVA URI: $RIVA_URI"

if [[ "$RIVA_URI" == "localhost:50051" ]]; then
    echo "WARNING: RIVA_URI is set to localhost, which won't work in Docker"
    echo "Consider using a network-accessible RIVA server"
fi

# Test RIVA connectivity (if not localhost)
if [[ "$RIVA_URI" != "localhost:50051" && "$RIVA_URI" != "parakeet-nim:50051" ]]; then
    echo "Testing RIVA connectivity..."
    HOST=$(echo "$RIVA_URI" | cut -d: -f1)
    PORT=$(echo "$RIVA_URI" | cut -d: -f2)
    
    if timeout 5 bash -c "</dev/tcp/$HOST/$PORT" 2>/dev/null; then
        echo "RIVA server is reachable at $RIVA_URI"
    else
        echo "ERROR: Cannot reach RIVA server at $RIVA_URI"
        echo "Check network connectivity and RIVA server status"
        exit 1
    fi
fi

echo "Environment validation complete!"
