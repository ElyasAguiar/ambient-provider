# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Multi-stage build for React UI using approved Ubuntu 24.04 base
FROM ubuntu:24.04 as builder

# Install Node.js 20.x from NodeSource repository
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy package files
COPY apps/ui/package.json apps/ui/package-lock.json ./

# Copy local NVIDIA package files
COPY apps/ui/kui-foundations-0.403.0.tgz ./
COPY apps/ui/kui-react-0.402.1.tgz ./
COPY apps/ui/nv-brand-assets-icons-3.8.0.tgz ./
COPY apps/ui/nv-brand-assets-react-icons-inline-3.8.0.tgz ./

# Remove package-lock to avoid conflicts with file: dependencies
RUN rm -f package-lock.json

# Install all dependencies (force to ignore version conflicts)
RUN npm install --force

# Copy source code
COPY apps/ui ./

# Build the application
RUN npm run build

# Production stage with approved Ubuntu 24.04 base and nginx
FROM ubuntu:24.04

# Install nginx and curl for health checks
RUN apt-get update && apt-get install -y \
    nginx \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy UI-specific nginx configuration
COPY infra/docker/ui-nginx.conf /etc/nginx/nginx.conf
COPY infra/docker/ui-default.conf /etc/nginx/conf.d/default.conf

# Copy built application
COPY --from=builder /app/dist /usr/share/nginx/html

# Create nginx user if it doesn't exist and create necessary directories
RUN id -u nginx >/dev/null 2>&1 || useradd -r -s /bin/false nginx
RUN mkdir -p /var/cache/nginx /var/log/nginx /var/lib/nginx/body /var/lib/nginx/proxy /var/lib/nginx/fastcgi /var/lib/nginx/uwsgi /var/lib/nginx/scgi && \
    chown -R nginx:nginx /usr/share/nginx/html && \
    chown -R nginx:nginx /var/cache/nginx && \
    chown -R nginx:nginx /var/log/nginx && \
    chown -R nginx:nginx /var/lib/nginx && \
    chown -R nginx:nginx /etc/nginx/conf.d && \
    touch /tmp/nginx.pid && \
    chown nginx:nginx /tmp/nginx.pid

# Switch to nginx user
USER nginx

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:80/ || exit 1

# Start nginx
CMD ["nginx", "-g", "daemon off;"]