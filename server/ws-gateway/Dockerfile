FROM golang:1.22-alpine AS builder

WORKDIR /src
ENV GOPROXY=https://goproxy.cn,direct

COPY go.mod ./
RUN go mod download

COPY . ./
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/ws-gateway .

FROM alpine:3.20

WORKDIR /app
COPY --from=builder /out/ws-gateway /app/ws-gateway

EXPOSE 8084
CMD ["/app/ws-gateway"]
