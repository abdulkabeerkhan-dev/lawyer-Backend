FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY . /app/

RUN python3 -c "import os; [exec(open(f).read()) for f in ['/app/entrypoint_setup.py', '/app/lawyer-Backend-master/entrypoint_setup.py'] if os.path.exists(f)]" && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

CMD ["sh", "-c", "python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --timeout-keep-alive 300"]
