# Stage 1: Build React frontend
FROM node:20-slim AS frontend-builder

WORKDIR /frontend

# Copy frontend package files
COPY frontend/package.json frontend/package-lock.json* ./

# Install dependencies
RUN npm install

# Copy frontend source
COPY frontend/ ./

# Set production API base (use relative path for production)
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=${VITE_API_BASE}

# Build the frontend
RUN npm run build

# Stage 2: Python backend
FROM python:3.12-slim

WORKDIR /app

# Install git (required for tvDatafeed which installs from GitHub)
# Also install dependencies for Playwright/Chromium
RUN apt-get update && apt-get install -y \
    git \
    tzdata \
    # Playwright/Chromium dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Copy backend requirements
COPY backend/requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (chromium only to save space)
RUN playwright install chromium

# Copy backend code (includes worker.py for background job processing)
COPY backend/ ./

# Copy frontend build from stage 1
COPY --from=frontend-builder /frontend/dist ./static

# Expose port
EXPOSE 8080

# Default command runs the web server using Gunicorn (production WSGI server)
# Worker machines are created via Fly Machines API with: python worker.py
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
