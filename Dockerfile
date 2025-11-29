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

# Copy backend requirements
COPY backend/requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./

# Copy frontend build from stage 1
COPY --from=frontend-builder /frontend/dist ./static

# Expose port
EXPOSE 8080

# Run the application
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
