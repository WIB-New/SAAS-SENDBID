FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated user (no root)
RUN useradd -m -u 1000 sendbid && \
    mkdir -p /var/app/uploads/avatars /var/app/uploads/kyc /var/app/uploads/receipts && \
    chown -R sendbid:sendbid /var/app

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/
COPY .env.example ./.env

# Permissions
RUN chown -R sendbid:sendbid /app
RUN chmod 750 /var/app/uploads && \
    chmod 750 /var/app/uploads/avatars && \
    chmod 750 /var/app/uploads/kyc && \
    chmod 750 /var/app/uploads/receipts

USER sendbid

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
