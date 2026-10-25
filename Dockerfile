FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY . /app/

RUN python3 -c "\
import os, shutil; \
for p in ['/app/lawyer-Backend-master', '/app/lawyer-backend']: \
    if os.path.isdir(p): \
        for f in os.listdir(p): \
            src = os.path.join(p, f); \
            dst = os.path.join('/app', f); \
            if not os.path.exists(dst): shutil.move(src, dst); \
print('Verified files in /app:', len(os.listdir('/app')))\
" && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt -v

CMD ["sh", "-c", "python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --timeout-keep-alive 300"]
