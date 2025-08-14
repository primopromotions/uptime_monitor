# Uses Ubuntu Noble with browsers preinstalled
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app
COPY checker.py /app/checker.py

CMD ["python", "/app/checker.py"]
