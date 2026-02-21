# Use a lightweight Python base image compatible with Cisco IOx x86
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies (GCC/G++ required for Scipy build)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libgfortran5 \
    && rm -rf /var/lib/apt/lists/*

# Install Python Libraries
# FIX: Added the "." at the end of the COPY command
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy our scripts
# FIX: Ensure these also have the "." at the end
COPY data_generator.py .
COPY validator_engine.py .

# Run the engine
CMD ["python", "validator_engine.py"]