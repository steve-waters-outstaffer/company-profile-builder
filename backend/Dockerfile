# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend code
COPY . .

# Get port from environment variable (Cloud Run provides this)
ENV PORT 8080

# Run the app using gunicorn
# This tells gunicorn to listen on all interfaces (0.0.0.0)
# on the port Cloud Run provides, and to find the 'app' object
# inside the 'app.py' file.
CMD exec gunicorn --bind 0.0.0.0:$PORT --timeout 300 app:app