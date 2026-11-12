#!/bin/sh
# Makes the test bed's TLS files in /certs (a Docker volume): a throwaway CA, and certificates for
# hub.irc.example.test and leaf.irc.example.test signed by it. Generated on every run, never
# committed; the CA key is deleted once both certificates are signed. Compose starts this service
# again whenever it starts a service that depends on it, so files already made are kept: the
# running servers hold the certificates they loaded.
set -eu
IRCD_UID=1100 # the ircd user of unrealircd.Dockerfile
DAYS=2
cd /certs
if [ -s ca.pem ] && [ -s hub.pem ] && [ -s leaf.pem ] && [ -s hub.key ] && [ -s leaf.key ]; then
    echo "certificates already present"
    exit 0
fi
rm -f ./*
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days "$DAYS" \
    -keyout ca.key -out ca.pem -subj '/CN=FIDO test bed CA' \
    -addext 'basicConstraints=critical,CA:TRUE' -addext 'keyUsage=critical,keyCertSign,cRLSign' 2>/dev/null
for role in hub leaf; do
    printf '%s\n' 'basicConstraints=CA:FALSE' 'keyUsage=critical,digitalSignature' \
        'extendedKeyUsage=serverAuth,clientAuth' "subjectAltName=DNS:$role.irc.example.test" > "$role.ext"
    openssl req -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
        -keyout "$role.key" -out "$role.csr" -subj "/CN=$role.irc.example.test" 2>/dev/null
    openssl x509 -req -in "$role.csr" -CA ca.pem -CAkey ca.key -CAcreateserial -days "$DAYS" \
        -out "$role.pem" -extfile "$role.ext" 2>/dev/null
    rm "$role.csr" "$role.ext"
    chown "$IRCD_UID:$IRCD_UID" "$role.key"
    chmod 0600 "$role.key"
done
rm -f ca.key ca.srl
chmod 0644 ca.pem hub.pem leaf.pem
echo "certificates ready: ca.pem hub.pem leaf.pem"
