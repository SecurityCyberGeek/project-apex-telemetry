# 1. Base Image: Enforce AMD64 architecture for Cisco IOx compatibility
FROM --platform=linux/amd64 python:3.10-slim

# 2. Metadata
LABEL maintainer="Timothy D. Harmon <info@securitycybergeek.com>"
LABEL description="Project Apex Edge Validator - 60Hz Telemetry Gate"
LABEL version="2.1"

# 3. Security: Run as non-root user (CISSP Zero-Trust Standard)
RUN useradd -m -u 1001 apexuser
WORKDIR /app

# 4. Install Dependencies
# No system dependencies (GCC/G++) required - all packages are pure Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Application Code
# Copy the hardened validator script into the container
COPY production_validator_service_prod.py .

# Ensure the non-root user owns the application files
RUN chown -R apexuser:apexuser /app
USER apexuser

# 6. Environment Defaults (Safety Net)
# Required runtime variables - injected via IOx manifest or docker run
# Left intentionally blank to trigger Python security gate if unconfigured
ENV SPLUNK_HEC_URL=""
ENV SPLUNK_TOKEN=""
ENV LISTEN_PORT="20777"
ENV LISTEN_IP="0.0.0.0"

# 7. Network Ports
# Expose the UDP port for ATLAS ingress
EXPOSE 20777/udp

# 8. Execution
# Run the validator in unbuffered mode (critical for real-time edge logs)
CMD ["python3", "-u", "production_validator_service_prod.py"]
