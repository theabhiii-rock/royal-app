FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source code
COPY backend /app/backend

# Copy the frontend (if you want to serve it statically from backend)
COPY www /app/www

# Set the working directory to backend
WORKDIR /app/backend

# Create data directory for SQLite
RUN mkdir -p data && chmod 777 data

EXPOSE 8000

# Start Uvicorn for production
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
