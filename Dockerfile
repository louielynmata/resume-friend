# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install --global npm@11.6.2 && npm ci
COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN python -m pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY prompts/ ./prompts/
COPY models_personal_example/ ./models_personal_example/
COPY --from=frontend-build /build/frontend/dist ./frontend/dist/

RUN mkdir -p /app/models_personal /app/outputs /app/ref /app/tmp/pdfs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)" || exit 1

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
