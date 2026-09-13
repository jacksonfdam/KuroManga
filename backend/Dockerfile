# The downloader is a Go program invoked as a subprocess, so it is built once
# here and copied into the runtime image.
FROM golang:1.23-alpine AS downloader
RUN apk add --no-cache git
RUN go install github.com/elboletaire/manga-downloader@latest

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv

COPY --from=downloader /go/bin/manga-downloader /usr/local/bin/manga-downloader

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e . && pip install --no-cache-dir alembic

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
