# H-Bit Protocol — Container Image
# Multi-stage build for minimal production image

FROM python:3.12-slim AS builder

WORKDIR /app
COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir build && \
    python -m build --wheel && \
    pip install --no-cache-dir dist/*.whl

# --- Production stage ---
FROM python:3.12-slim

LABEL maintainer="H-Bit Contributors"
LABEL description="H-Bit: Persistent Authenticity Protocol"
LABEL version="0.1.0"

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/hbit /usr/local/bin/hbit

# Create working directories
RUN mkdir -p /app/input /app/output /app/keys

VOLUME ["/app/input", "/app/output", "/app/keys"]

ENTRYPOINT ["hbit"]
CMD ["--help"]

# Usage examples:
# docker build -t hbit .
# docker run --rm hbit --help
# docker run --rm -v $(pwd)/keys:/app/keys hbit keygen --output /app/keys/my_key.pem
# docker run --rm -v $(pwd):/app/input -v $(pwd)/out:/app/output -v $(pwd)/keys:/app/keys \
#     hbit encode /app/input/photo.jpg --key /app/keys/my_key.pem --output /app/output/signed.png
