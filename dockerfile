FROM python:3.10-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies (including SQLite)
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Ensure upload directory exists
RUN mkdir -p submissions

# Expose Gunicorn port
EXPOSE 5000

# Initialize DB on start and run Gunicorn WSGI server
CMD python init_db.py && gunicorn --bind 0.0.0.0:5000 --workers 3 app:app