FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
# aiogram 2.25.1 declares aiohttp<3.9 but actually works with 3.x.
# Install everything except aiogram normally (so transitive deps are resolved),
# then install aiogram with --no-deps to skip the stale aiohttp constraint.
RUN grep -v '^aiogram==' requirements.txt > /tmp/req_no_aiogram.txt && \
    pip install --no-cache-dir -r /tmp/req_no_aiogram.txt && \
    pip install --no-cache-dir --no-deps aiogram==2.25.1

COPY . .

RUN mkdir -p /app/storage

CMD ["python", "__main__.py"]
