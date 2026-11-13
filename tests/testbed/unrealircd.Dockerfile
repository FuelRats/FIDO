# Throwaway UnrealIRCd 6.2.6 for the local FIDO test bed (tests/testbed/run.sh). Test use only.
# The configuration and the entrypoint are mounted at run time from tests/testbed/.
# debian:trixie-slim, index digest read 2026-11-12.
FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential pkg-config libssl-dev libpcre2-dev \
      libargon2-dev libsodium-dev libc-ares-dev libjansson-dev openssl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1100 --user-group ircd

# The official release tarball; the build fails unless it has the SHA256 published on
# https://www.unrealircd.org/download/6.0/6.2.6/src ("File Checksums").
ADD --checksum=sha256:6eaf0f8963c2dc8c28ce580afa0239922e26c7b2df55aed7ec5f73daa307fc9b \
    https://www.unrealircd.org/downloads/unrealircd-6.2.6.tar.gz /tmp/unrealircd.tar.gz

RUN mkdir /src \
 && tar -xzf /tmp/unrealircd.tar.gz -C /src \
 && rm /tmp/unrealircd.tar.gz \
 && chown -R ircd:ircd /src

USER ircd
WORKDIR /src/unrealircd-6.2.6

# The answers ./Config would ask for: install under ~/unrealircd, no GeoIP, no remote includes,
# no generated certificate (run.sh generates the test bed's).
RUN B=/home/ircd/unrealircd \
 && printf '%s\n' \
      "BASEPATH=\"$B\"" "BINDIR=\"$B/bin\"" "DATADIR=\"$B/data\"" "CONFDIR=\"$B/conf\"" \
      "MODULESDIR=\"$B/modules\"" "LOGDIR=\"$B/logs\"" "CACHEDIR=\"$B/cache\"" "DOCDIR=\"$B/doc\"" \
      "TMPDIR=\"$B/tmp\"" "PRIVATELIBDIR=\"$B/lib\"" 'MAXCONNECTIONS_REQUEST="auto"' \
      'NICKNAMEHISTORYLENGTH="2000"' 'GEOIP="none"' 'DEFPERM="0600"' 'SSLDIR=""' 'REMOTEINC=""' \
      'CURLDIR=""' 'NOOPEROVERRIDE=""' 'OPEROVERRIDEVERIFY=""' 'GENCERTIFICATE=""' 'SANITIZER=""' \
      'EXTRAPARA=""' 'ADVANCED=""' > config.settings \
 && ./Config -quick \
 && make -j"$(nproc)" \
 && make install

WORKDIR /home/ircd
