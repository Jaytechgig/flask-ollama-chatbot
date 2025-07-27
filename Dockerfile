# Use slim image with Python
FROM python:3.10-slim

# Set work directory
WORKDIR /app

# Copy dependency list and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose Flask port
EXPOSE 5000

# Start Flask app
CMD ["python", "app/main.py"]
