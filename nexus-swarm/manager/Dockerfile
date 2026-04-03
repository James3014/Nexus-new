# 🛡️ Build Stage
FROM golang:1.22-alpine AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download

COPY . .
# 🛡️ Compile static binary
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o manager ./manager

# 🛡️ Production Stage
FROM alpine:3.19
RUN apk --no-cache add ca-certificates tzdata
WORKDIR /root/

COPY --from=builder /app/manager .
# 🛡️ Certs will be mounted via K8s Secret or copied here for local test
# COPY certs/ca.crt certs/manager.crt certs/manager.key ./certs/

EXPOSE 9000 9100
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:9100/cluster/status || exit 1

CMD ["./manager"]
