# Use a lightweight python image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY cloud_ui.py /app/
COPY web_ui.py /app/
COPY db_client.py /app/

# Expose port (Railway will override PORT env var)
EXPOSE 8080

# Run the cloud server
CMD ["python", "cloud_ui.py"]
