# syntax=docker/dockerfile:1
#
# Один образ origin для HF Space и Render (и generic VPS).
# По умолчанию — только FastAPI (:8080).
# xHTTP sidecar — ANOTHER_RUN_XHTTP=1.
# Reality на 8443 (снаружи 443) — ANOTHER_RUN_REALITY=1, только VPS со стабильным IP.

FROM golang:1.24-bookworm AS xhttp
WORKDIR /src
COPY core/go.mod core/go.sum ./
RUN go mod download
COPY core/ ./
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o /out/xhttp-origin ./cmd/xhttp-origin \
 && CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o /out/reality-origin ./cmd/reality-origin

FROM python:3.12-slim

WORKDIR /app

COPY control-plane-admin/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY control-plane-admin/another_admin/ ./another_admin/
COPY deploy/origin/entrypoint.sh /entrypoint.sh
COPY --from=xhttp /out/xhttp-origin /usr/local/bin/xhttp-origin
COPY --from=xhttp /out/reality-origin /usr/local/bin/reality-origin

RUN chmod +x /entrypoint.sh \
    && useradd --create-home --uid 10001 apiuser \
    && chown apiuser:apiuser /entrypoint.sh

USER apiuser

ENV PYTHONPATH=/app
ENV ADMIN_API_HOST=0.0.0.0
ENV ADMIN_API_PORT=8080
ENV ANOTHER_XHTTP_ADDR=0.0.0.0:8081
ENV ANOTHER_REALITY_LISTEN=0.0.0.0:8443

EXPOSE 8080 8081 8443

ENTRYPOINT ["/entrypoint.sh"]
