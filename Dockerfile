# Base image
FROM python:3.12-slim

# Create a system group and user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Set working directory
WORKDIR /usr/src/app

# Copy dependencies first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY . .

# Give the appuser ownership of the working directory
RUN chown -R appuser:appgroup /usr/src/app

# Switch to non-root user
USER appuser

# Expose port for Flask
EXPOSE 8000

# Default command (Flask)
CMD ["flask", "run", "--host=0.0.0.0", "--port=8000"]