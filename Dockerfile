FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npx vite build --outDir /static --emptyOutDir

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py db.py import_codes.py models.json schema.sql schema_pg.sql ./
COPY --from=web /static ./static

# The SQLite database lives on a mounted persistent disk, never inside the image.
ENV DB_PATH=/data/study.db
CMD uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips="*"
