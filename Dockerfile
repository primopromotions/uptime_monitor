# Uses Ubuntu Noble with browsers preinstalled
FROM mcr.microsoft.com/playwright/python:v1.45.0-noble

WORKDIR /app
COPY checker.py /app/checker.py

CMD ["python", "/app/checker.py"]
