# Use official Python slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install dependencies
RUN pip install --upgrade pip && \
    pip install --upgrade -r requirements.txt

# Default command (FastAPI app)
# You can override this in Railway for the worker service
CMD ["gunicorn", "--preload", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "main:app"]
