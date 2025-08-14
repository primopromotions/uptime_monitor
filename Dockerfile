# Uses Ubuntu Jammy with browsers preinstalled
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY checker.py /app/checker.py

CMD ["python", "/app/checker.py"]
