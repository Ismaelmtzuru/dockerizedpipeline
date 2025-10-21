# Python image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt ./
COPY .env ./
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Commando to run the script
CMD ["python", "4-ingest-data-parquet-pycog.py"]