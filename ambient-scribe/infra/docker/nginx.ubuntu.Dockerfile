# Nginx reverse proxy using approved Ubuntu 24.04 base
FROM ubuntu:24.04

# Install nginx and curl for health checks
RUN apt-get update && apt-get install -y \
    nginx \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create nginx user if it doesn't exist
RUN id -u nginx >/dev/null 2>&1 || useradd -r -s /bin/false nginx

# Expose ports
EXPOSE 80 443

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:80/ || exit 1

# Start nginx in foreground
CMD ["nginx", "-g", "daemon off;"]
