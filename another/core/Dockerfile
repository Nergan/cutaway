# syntax=docker/dockerfile:1

# --- Build stage --------------------------------------------------------------
FROM golang:1.24-bookworm AS build

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .

# CGO_ENABLED=0 — статический бинарник, можно положить в scratch-образ.
# Актуально ТОЛЬКО для cmd/desktop (Linux-контейнер) — cmd/mobilelib
# собирается отдельно через gomobile bind вне Docker (см. core/README.md).
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o /out/another-core ./cmd/desktop

# --- Runtime stage --------------------------------------------------------------
FROM gcr.io/distroless/static-debian12:nonroot

WORKDIR /app
COPY --from=build /out/another-core /app/another-core

# Локальный control API слушает на loopback по умолчанию (см. config.go) —
# в контейнере это бессмысленно (Flutter-клиент работает не в этом же
# контейнере), поэтому ANOTHER_LOCAL_API_ADDR обычно переопределяется на
# 0.0.0.0:PORT через переменные окружения при контейнерном запуске.
EXPOSE 47821

USER nonroot:nonroot
ENTRYPOINT ["/app/another-core"]
