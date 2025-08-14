# Uses Ubuntu Jammy with browsers preinstalled
FROM mcr.microsoft.com/playwright/python:v1.54.0-jammy

WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Ensure browsers are installed and up to date
RUN playwright install chromium

# Copy the application code
COPY checker.py /app/checker.py

CMD ["python", "/app/checker.py"]
