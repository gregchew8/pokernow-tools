# Use a lightweight python image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy the cloud UI script and the web_ui dashboard module
COPY cloud_ui.py /app/
COPY web_ui.py /app/

# Expose port (Railway will override PORT env var)
EXPOSE 8080

# Run the cloud server
CMD ["python", "cloud_ui.py"]
