#!/usr/bin/env bash
# Compose a CA bundle that includes:
#   - certifi (Mozilla) standard CAs
#   - macOS System keychain CAs
#   - macOS SystemRoot CAs
#   - YandexInternal* CAs (in case they are stored as user trust)
# Result: ./data/ca-bundle.pem
#
# Re-run when corporate CAs rotate.

set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p data
OUT=data/ca-bundle.pem

# 1. certifi bundle (works in venv or in the host python with certifi installed)
PYBIN=".venv/bin/python"
if [ ! -x "$PYBIN" ]; then
  PYBIN="python3"
fi
CERTIFI_PATH=$("$PYBIN" - <<'PY'
import certifi, sys
sys.stdout.write(certifi.where())
PY
) || {
  echo "certifi not installed in $PYBIN; install it: $PYBIN -m pip install certifi" >&2
  exit 1
}

cat "$CERTIFI_PATH" > "$OUT"

if [[ "$(uname -s)" == "Darwin" ]]; then
  # 2. macOS keychain CAs
  /usr/bin/security find-certificate -a -p /Library/Keychains/System.keychain >> "$OUT" || true
  /usr/bin/security find-certificate -a -p /System/Library/Keychains/SystemRootCertificates.keychain >> "$OUT" || true
  # 3. Yandex CAs explicitly (sometimes they are inside, sometimes only in user keychain)
  for KC in \
      /Library/Keychains/System.keychain \
      /System/Library/Keychains/SystemRootCertificates.keychain \
      "$HOME/Library/Keychains/login.keychain-db" \
      ; do
    /usr/bin/security find-certificate -a -c "YandexInternalRootCA" -p "$KC" >> "$OUT" 2>/dev/null || true
    /usr/bin/security find-certificate -a -c "YandexInternalCA" -p "$KC" >> "$OUT" 2>/dev/null || true
  done
fi

# Sanity check
if grep -q "BEGIN CERTIFICATE" "$OUT"; then
  echo "CA bundle written: $OUT ($(wc -l < "$OUT") lines, $(grep -c 'BEGIN CERTIFICATE' "$OUT") certs)"
else
  echo "ERROR: no certificates found in $OUT" >&2
  exit 1
fi
