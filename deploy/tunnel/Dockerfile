# syntax=docker/dockerfile:1
#
# Deployer tunnel sidecar (docs/REMOTE_ACCESS.md): a pinned, checksum-verified cloudflared plus a
# small supervisor that follows /tunnel/desired.json (written by the API) and reports /tunnel/status.json.
#
# Upgrading cloudflared: take the version and the `cloudflared-linux-amd64` SHA256 from the
# "SHA256 Checksums" section of https://github.com/cloudflare/cloudflared/releases/tag/<version>
# (GitHub also shows the same value as the asset digest).
FROM alpine:3.24

ARG CLOUDFLARED_VERSION=2026.9.1
ARG CLOUDFLARED_SHA256=03f1f25d1cc93b9ad6c60569d44060bc4f17ed97075760ed8cfca4b12dcd68cc

RUN apk add --no-cache ca-certificates jq \
    && wget -q -O /tmp/cloudflared \
        "https://github.com/cloudflare/cloudflared/releases/download/${CLOUDFLARED_VERSION}/cloudflared-linux-amd64" \
    && echo "${CLOUDFLARED_SHA256}  /tmp/cloudflared" | sha256sum -c - \
    && install -m 0755 /tmp/cloudflared /usr/local/bin/cloudflared \
    && rm /tmp/cloudflared \
    && /usr/local/bin/cloudflared --version \
    && addgroup -S -g 10001 deployer \
    && adduser -S -D -H -u 10001 -G deployer -h /tmp deployer \
    && mkdir -p /tunnel \
    && chown deployer:deployer /tunnel \
    && chmod 0700 /tunnel

COPY supervisor.sh /usr/local/bin/tunnel-supervisor
# Tolerate CRLF checkouts on Windows.
RUN sed -i 's/\r$//' /usr/local/bin/tunnel-supervisor && chmod 0755 /usr/local/bin/tunnel-supervisor

# The compose service runs with a read-only root filesystem and a tmpfs on /tmp.
ENV HOME=/tmp \
    TUNNEL_STATE_DIR=/tunnel \
    TUNNEL_ORIGIN_URL=http://caddy:8081

USER 10001:10001

# Healthy while the supervisor keeps status.json fresh (it rewrites it at least every 15 s).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD test -n "$(find /tunnel/status.json -mmin -1 2>/dev/null)" || exit 1

ENTRYPOINT ["/usr/local/bin/tunnel-supervisor"]
