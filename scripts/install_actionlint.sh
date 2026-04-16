#!/usr/bin/env bash
# Installs actionlint into ./tools/actionlint/ (inside validate-actions-eval) so the
# whole thing can be removed with `rm -rf tools/actionlint`. Pins a specific version.
#
# Usage: bash scripts/install_actionlint.sh
# Uninstall: rm -rf tools/actionlint
set -euo pipefail

# Pinned version; bump deliberately if you need a newer actionlint.
VERSION="${ACTIONLINT_VERSION:-1.7.7}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS_DIR="${HERE}/tools/actionlint"
mkdir -p "${TOOLS_DIR}"

case "$(uname -s)" in
  Darwin) OS="darwin" ;;
  Linux)  OS="linux" ;;
  *)      echo "Unsupported OS: $(uname -s)" >&2; exit 1 ;;
esac

case "$(uname -m)" in
  x86_64|amd64) ARCH="amd64" ;;
  arm64|aarch64) ARCH="arm64" ;;
  *) echo "Unsupported arch: $(uname -m)" >&2; exit 1 ;;
esac

TARBALL="actionlint_${VERSION}_${OS}_${ARCH}.tar.gz"
URL="https://github.com/rhysd/actionlint/releases/download/v${VERSION}/${TARBALL}"

echo "Downloading ${URL}"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
curl -sSfL "${URL}" -o "${TMP}/${TARBALL}"
tar -xzf "${TMP}/${TARBALL}" -C "${TMP}"
mv "${TMP}/actionlint" "${TOOLS_DIR}/actionlint"
chmod +x "${TOOLS_DIR}/actionlint"

echo "Installed: ${TOOLS_DIR}/actionlint"
"${TOOLS_DIR}/actionlint" -version
echo "Remove with: rm -rf ${TOOLS_DIR}"
