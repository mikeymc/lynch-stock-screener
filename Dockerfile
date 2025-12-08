# Stage 1: Build React frontend
FROM node:20-slim AS frontend-builder

WORKDIR /frontend

# Copy frontend package files
COPY frontend/package.json frontend/package-lock.json* ./

# Install dependencies
RUN npm install

# Copy frontend source
COPY frontend/ ./

# Build the frontend
RUN npm run build

# Stage 2: Python backend
FROM python:3.12-slim

WORKDIR /app

# Install git (required for tvDatafeed which installs from GitHub)
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Copy backend requirements
COPY backend/requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code (includes worker.py for background job processing)
COPY backend/ ./

# Copy frontend build from stage 1
COPY --from=frontend-builder /frontend/dist ./static

# Expose port
EXPOSE 8080

# Default command runs the web server
# Worker machines are created via Fly Machines API with: python worker.py
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
