# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /fileConvertor

# Install FreeCAD and dependencies
RUN apt-get update && apt-get install -y \
    freecad \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container
COPY . .

# Expose the API port
EXPOSE 5000

# Run the API
CMD ["python", "fileConvertor.py"]