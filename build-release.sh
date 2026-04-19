#!/bin/bash
#
# QN Code Assistant - Release Builder
# Creates per-arch self-extracting installers with a bundled PBS Python runtime.
#
# Usage: ./build-release.sh
# Output: qn-code-assistant-v<VERSION>-linux-x86_64.sh
#         qn-code-assistant-v<VERSION>-linux-aarch64.sh
#
# Environment overrides:
#   PBS_PYTHON_VERSION   Python version to bundle (default: 3.12.13)
#   PBS_RELEASE_TAG      PBS release tag (default: 20260408)
#
# The PBS tarballs are cached in .build-cache/ and reused if SHA-256 matches.
# Pass PBS_PYTHON_VERSION and PBS_RELEASE_TAG as env vars to switch versions.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# -------------------------------------------------------------------
# PBS version pins
# Both x86_64-unknown-linux-musl and aarch64-unknown-linux-musl are
# published in the 20260414 release (3.12.13).
# SHA-256 hashes come from the release-wide SHA256SUMS manifest
# (there are no per-asset .sha256 files).
# -------------------------------------------------------------------
PBS_PYTHON_VERSION="${PBS_PYTHON_VERSION:-3.12.13}"
PBS_RELEASE_TAG="${PBS_RELEASE_TAG:-20260414}"
PBS_BASE_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_RELEASE_TAG}"

BUILD_CACHE="${SCRIPT_DIR}/.build-cache"
PBS_SHA256SUMS="${BUILD_CACHE}/SHA256SUMS-${PBS_RELEASE_TAG}"

# Get version from app.py
VERSION=$(grep -oP "VERSION\s*=\s*['\"]([^'\"]+)['\"]" "${SCRIPT_DIR}/app.py" | head -1 | grep -oP "['\"][^'\"]+['\"]" | tr -d "'\"" || echo "unknown")

echo -e "${GREEN}${BOLD}Building QN Code Assistant self-extracting installers v${VERSION}...${NC}"
echo -e "  PBS Python: ${CYAN}${PBS_PYTHON_VERSION}+${PBS_RELEASE_TAG}${NC} (musl)"
echo ""

# Files and directories to include in app payload
INCLUDE_FILES=(
    "app.py"
    "static/js/app.js"
    "static/css/style.css"
    "templates/index.html"
    "templates/login.html"
    "requirements.txt"
    "static/manifest.json"
    "static/sw.js"
    "static/icon.svg"
    "apache-proxy.conf"
    "maintenance.sh"
    "start.sh"
    "qn-code-assistant.service"
    "build-installer.sh"
    "install.sh"
    "README.md"
    "CHANGELOG.md"
    "DEVELOPMENT.md"
    ".gitignore"
)

# Verify all app files exist
MISSING=0
for f in "${INCLUDE_FILES[@]}"; do
    if [[ ! -f "${SCRIPT_DIR}/${f}" ]]; then
        echo -e "${RED}Missing: ${f}${NC}"
        MISSING=1
    fi
done
if [[ ! -d "${SCRIPT_DIR}/vendor" ]]; then
    echo -e "${RED}Missing: vendor/${NC}"
    MISSING=1
fi
if [[ ! -d "${SCRIPT_DIR}/static/js/ace" ]]; then
    echo -e "${RED}Missing: static/js/ace/${NC}"
    MISSING=1
fi
if [[ "${MISSING}" -eq 1 ]]; then
    echo -e "${RED}Aborting: missing files.${NC}"
    exit 1
fi

# -------------------------------------------------------------------
# Create the app zip payload (arch-independent, built once)
# -------------------------------------------------------------------
echo -e "  Creating app archive..."
mkdir -p "${BUILD_CACHE}"

APP_ZIP="${BUILD_CACHE}/app-v${VERSION}.zip"

# Use system python3 for build-time tooling only (not shipped to target)
python3 -c "
import zipfile, io, os, sys

target = '${APP_ZIP}'
include_files = '''$(printf '%s\n' "${INCLUDE_FILES[@]}")'''.strip().split('\n')

with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in include_files:
        f = f.strip()
        if f and os.path.isfile(f):
            zf.write(f)
    for walk_dir in ['vendor', 'static/js/ace']:
        for root, dirs, filenames in os.walk(walk_dir):
            dirs[:] = [d for d in dirs if d != '__pycache__']
            for fn in filenames:
                zf.write(os.path.join(root, fn))

print(f'App zip: {os.path.getsize(target)} bytes')
"

FILE_COUNT=$(python3 -c "
import os
count = len('''$(printf '%s\n' "${INCLUDE_FILES[@]}")'''.strip().split('\n'))
for walk_dir in ['vendor', 'static/js/ace']:
    for root, dirs, files in os.walk(walk_dir):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        count += len(files)
print(count)
")
echo -e "  App files: ${FILE_COUNT}"

# -------------------------------------------------------------------
# Fetch the SHA256SUMS manifest once (shared across arches)
# -------------------------------------------------------------------
fetch_sha256sums() {
    if [[ -s "${PBS_SHA256SUMS}" ]]; then
        echo -e "  SHA256SUMS: ${GREEN}cache hit${NC}" >&2
        return
    fi
    echo -e "  Fetching SHA256SUMS for release ${PBS_RELEASE_TAG}..." >&2
    curl -fSL --progress-bar \
        "${PBS_BASE_URL}/SHA256SUMS" \
        -o "${PBS_SHA256SUMS}" >&2
}

# -------------------------------------------------------------------
# Download PBS tarball (with caching + SHA-256 verification)
# Sets global: PBS_TARBALL_PATH
# -------------------------------------------------------------------
download_pbs() {
    local arch="$1"
    local tarball="cpython-${PBS_PYTHON_VERSION}+${PBS_RELEASE_TAG}-${arch}-unknown-linux-musl-install_only.tar.gz"
    local cached_tarball="${BUILD_CACHE}/${tarball}"

    echo "" >&2
    echo -e "  ${BOLD}[${arch}]${NC} PBS runtime: ${tarball}" >&2

    # Extract expected hash from SHA256SUMS manifest (fixed-string match)
    local expected_hash
    expected_hash="$(grep -F "  ${tarball}" "${PBS_SHA256SUMS}" | awk '{print $1}' | head -1)"
    if [[ -z "${expected_hash}" ]]; then
        echo -e "${RED}    No SHA-256 entry for ${tarball} in SHA256SUMS${NC}" >&2
        exit 1
    fi
    echo -e "    Expected SHA-256: ${expected_hash}" >&2

    # Cache hit?
    if [[ -f "${cached_tarball}" ]]; then
        local actual_hash
        actual_hash="$(sha256sum "${cached_tarball}" | awk '{print $1}')"
        if [[ "${actual_hash}" == "${expected_hash}" ]]; then
            echo -e "    ${GREEN}Cache hit${NC}" >&2
            PBS_TARBALL_PATH="${cached_tarball}"
            return
        fi
        echo -e "    ${YELLOW}Cache hash mismatch — re-downloading...${NC}" >&2
        rm -f "${cached_tarball}"
    fi

    echo -e "    Downloading..." >&2
    curl -fSL --progress-bar \
        "${PBS_BASE_URL}/${tarball}" \
        -o "${cached_tarball}" >&2

    local dl_hash
    dl_hash="$(sha256sum "${cached_tarball}" | awk '{print $1}')"
    if [[ "${dl_hash}" != "${expected_hash}" ]]; then
        echo -e "${RED}SHA-256 verification FAILED for ${tarball}${NC}" >&2
        echo -e "  Expected: ${expected_hash}" >&2
        echo -e "  Got:      ${dl_hash}" >&2
        rm -f "${cached_tarball}"
        exit 1
    fi
    echo -e "    ${GREEN}SHA-256 verified${NC}" >&2
    PBS_TARBALL_PATH="${cached_tarball}"
}

# -------------------------------------------------------------------
# Build one installer per arch
# -------------------------------------------------------------------
build_installer() {
    local arch="$1"
    local pbs_tarball="$2"
    local output="${SCRIPT_DIR}/qn-code-assistant-v${VERSION}-linux-${arch}.sh"

    echo ""
    echo -e "${YELLOW}Building ${output##*/}...${NC}"

    # Base64-encode both payloads to temp files so we can stream-embed them
    # (avoids shoving 100+ MB through bash variable substitution).
    local app_b64_file runtime_b64_file
    app_b64_file="${BUILD_CACHE}/app-v${VERSION}.b64"
    runtime_b64_file="${BUILD_CACHE}/runtime-${arch}.b64"

    base64 -w 0 "${APP_ZIP}" > "${app_b64_file}"
    # Match the trailing newline that `cat + echo` will produce in the installer
    printf '\n' >> "${app_b64_file}"

    base64 -w 0 "${pbs_tarball}" > "${runtime_b64_file}"
    printf '\n' >> "${runtime_b64_file}"

    # Hash the exact bytes that will end up in the installer
    local app_hash runtime_hash
    app_hash="$(sha256sum "${app_b64_file}" | awk '{print $1}')"
    runtime_hash="$(sha256sum "${runtime_b64_file}" | awk '{print $1}')"

    local app_b64_size runtime_b64_size
    app_b64_size=$(stat -c '%s' "${app_b64_file}")
    runtime_b64_size=$(stat -c '%s' "${runtime_b64_file}")

    echo -e "  App payload:     $(( app_b64_size / 1048576 ))MB (base64)"
    echo -e "  Runtime payload: $(( runtime_b64_size / 1048576 ))MB (base64)"

    # Write shell header
    cat > "${output}" << 'HEADER'
#!/bin/bash
#
# QN Code Assistant - Self-Extracting Installer
# Contains the complete application + vendored deps + bundled Python 3.12 runtime.
# No system Python required. Just run it.
#
# Usage:
#   ./qn-code-assistant-v*.sh                    Install to /opt/qn-code-assistant
#   ./qn-code-assistant-v*.sh --dir /custom/path Install to custom directory
#   ./qn-code-assistant-v*.sh --extract-only     Extract without running setup
#   ./qn-code-assistant-v*.sh --help             Show help
#

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

HEADER

    # Inject version and hashes
    cat >> "${output}" << EOF
VERSION="${VERSION}"
PBS_VERSION="${PBS_PYTHON_VERSION}+${PBS_RELEASE_TAG}"
APP_HASH="${app_hash}"
RUNTIME_HASH="${runtime_hash}"
FILE_COUNT="${FILE_COUNT}"
EOF

    cat >> "${output}" << 'BODY'
INSTALL_DIR="/opt/qn-code-assistant"
EXTRACT_ONLY=0

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# -------------------------------------------------------------------
# Parse arguments
# -------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir)
            INSTALL_DIR="$2"
            shift 2
            ;;
        --extract-only)
            EXTRACT_ONLY=1
            shift
            ;;
        --help|-h)
            echo "QN Code Assistant - Self-Extracting Installer v${VERSION}"
            echo ""
            echo "Usage:"
            echo "  ${0##*/}                         Install to /opt/qn-code-assistant"
            echo "  ${0##*/} --dir /custom/path      Install to custom directory"
            echo "  ${0##*/} --extract-only           Extract files without running setup"
            echo "  ${0##*/} --help                   Show this help"
            echo ""
            echo "Self-contained: includes all app files + vendored Python deps + bundled Python ${PBS_VERSION} runtime."
            echo "No system Python required."
            echo ""
            echo "Payload: ${FILE_COUNT} app files, SHA-256 (app): ${APP_HASH}"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Run ${0##*/} --help for usage."
            exit 1
            ;;
    esac
done

# -------------------------------------------------------------------
# Pre-flight checks
# -------------------------------------------------------------------
echo ""
echo -e "${GREEN}${BOLD}============================================${NC}"
echo -e "${GREEN}${BOLD}  QN Code Assistant v${VERSION}${NC}"
echo -e "${GREEN}${BOLD}  Self-Extracting Installer${NC}"
echo -e "${GREEN}${BOLD}============================================${NC}"
echo ""

# tmux check (optional — needed for persistent terminal sessions only)
if ! command -v tmux &> /dev/null; then
    log_warn "tmux is not installed — persistent terminal sessions will not work."
    log_warn "Install with: sudo apt install tmux  (or equivalent)"
fi

# We need base64 and tar for extraction
if ! command -v base64 &> /dev/null; then
    log_error "base64 is required but not found."
    exit 1
fi
if ! command -v tar &> /dev/null; then
    log_error "tar is required but not found."
    exit 1
fi

# -------------------------------------------------------------------
# Locate payload markers
# -------------------------------------------------------------------
APP_PAYLOAD_LINE=$(awk '/^__APP_PAYLOAD__$/ { print NR + 1; exit }' "$0")
RUNTIME_PAYLOAD_LINE=$(awk '/^__RUNTIME_PAYLOAD__$/ { print NR + 1; exit }' "$0")
if [[ -z "${APP_PAYLOAD_LINE}" ]] || [[ -z "${RUNTIME_PAYLOAD_LINE}" ]]; then
    log_error "Payload markers not found. File may be corrupted."
    exit 1
fi

# The app payload ends just before the __RUNTIME_PAYLOAD__ marker
# Runtime payload runs to EOF
APP_PAYLOAD_END=$(awk '/^__RUNTIME_PAYLOAD__$/ { print NR - 1; exit }' "$0")

# -------------------------------------------------------------------
# Verify payload integrity
# -------------------------------------------------------------------
log_info "Verifying app payload integrity..."
ACTUAL_APP_HASH=$(sed -n "${APP_PAYLOAD_LINE},${APP_PAYLOAD_END}p" "$0" | sha256sum | awk '{print $1}')
if [[ "${ACTUAL_APP_HASH}" != "${APP_HASH}" ]]; then
    log_error "App payload integrity check failed!"
    echo "         Expected: ${APP_HASH}"
    echo "         Actual:   ${ACTUAL_APP_HASH}"
    exit 1
fi
log_info "App payload verified"

log_info "Verifying runtime payload integrity..."
ACTUAL_RUNTIME_HASH=$(tail -n +"${RUNTIME_PAYLOAD_LINE}" "$0" | sha256sum | awk '{print $1}')
if [[ "${ACTUAL_RUNTIME_HASH}" != "${RUNTIME_HASH}" ]]; then
    log_error "Runtime payload integrity check failed!"
    echo "         Expected: ${RUNTIME_HASH}"
    echo "         Actual:   ${ACTUAL_RUNTIME_HASH}"
    exit 1
fi
log_info "Runtime payload verified"

# -------------------------------------------------------------------
# Extract app files
# -------------------------------------------------------------------
echo ""
log_info "Extracting ${FILE_COUNT} app files to ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}"

TMPDIR_EXTRACT="$(mktemp -d)"
trap 'rm -rf "${TMPDIR_EXTRACT}"' EXIT

sed -n "${APP_PAYLOAD_LINE},${APP_PAYLOAD_END}p" "$0" \
    | base64 -d > "${TMPDIR_EXTRACT}/app.zip"

# Extract zip using unzip if available, otherwise fall back to Python from the next step
if command -v unzip &> /dev/null; then
    unzip -q -o "${TMPDIR_EXTRACT}/app.zip" -d "${INSTALL_DIR}"
else
    log_warn "unzip not found — will extract with bundled Python after runtime is set up"
    NEED_PYTHON_UNZIP=1
fi

# -------------------------------------------------------------------
# Extract Python runtime
# -------------------------------------------------------------------
log_info "Extracting bundled Python ${PBS_VERSION} runtime..."
tail -n +"${RUNTIME_PAYLOAD_LINE}" "$0" \
    | base64 -d > "${TMPDIR_EXTRACT}/runtime.tar.gz"

mkdir -p "${INSTALL_DIR}/runtime"
# PBS tarballs extract as python/ — rename to runtime/
tar -xzf "${TMPDIR_EXTRACT}/runtime.tar.gz" -C "${TMPDIR_EXTRACT}"
if [[ -d "${TMPDIR_EXTRACT}/python" ]]; then
    cp -a "${TMPDIR_EXTRACT}/python/." "${INSTALL_DIR}/runtime/"
else
    log_error "Unexpected runtime tarball layout — expected a python/ directory at top level."
    exit 1
fi

# Ensure interpreter is executable
chmod +x "${INSTALL_DIR}/runtime/bin/python3" 2>/dev/null || true
find "${INSTALL_DIR}/runtime/bin" -type f -exec chmod +x {} \; 2>/dev/null || true

# Verify bundled Python works
log_info "Verifying bundled runtime..."
BUNDLED_PY_VER=$("${INSTALL_DIR}/runtime/bin/python3" -V 2>&1 | awk '{print $2}' || true)
if [[ -z "${BUNDLED_PY_VER}" ]]; then
    log_error "Bundled Python failed to run. The runtime may not be compatible with this system."
    exit 1
fi
log_info "Bundled Python ${BUNDLED_PY_VER} (musl) — OK"

# If unzip was unavailable, use the now-extracted Python to unzip the app
if [[ "${NEED_PYTHON_UNZIP:-0}" -eq 1 ]]; then
    log_info "Extracting app files using bundled Python..."
    "${INSTALL_DIR}/runtime/bin/python3" -c "
import zipfile, os
with zipfile.ZipFile('${TMPDIR_EXTRACT}/app.zip', 'r') as zf:
    zf.extractall('${INSTALL_DIR}')
print('Extracted OK')
"
fi

# Make scripts executable
chmod 755 "${INSTALL_DIR}/start.sh" 2>/dev/null || true
chmod 755 "${INSTALL_DIR}/maintenance.sh" 2>/dev/null || true
chmod 755 "${INSTALL_DIR}/install.sh" 2>/dev/null || true
chmod 755 "${INSTALL_DIR}/build-installer.sh" 2>/dev/null || true

log_info "Extraction complete"

if [[ "${EXTRACT_ONLY}" -eq 1 ]]; then
    echo ""
    echo -e "${GREEN}${BOLD}Files extracted to: ${INSTALL_DIR}${NC}"
    echo -e "Run ${YELLOW}cd ${INSTALL_DIR} && ./install.sh${NC} to complete setup."
    exit 0
fi

# -------------------------------------------------------------------
# Run interactive setup
# -------------------------------------------------------------------
echo ""
cd "${INSTALL_DIR}"
bash "${INSTALL_DIR}/install.sh"

exit 0

# Payloads follow - DO NOT edit below this line
__APP_PAYLOAD__
BODY

    # Append app payload (file already has trailing newline)
    cat "${app_b64_file}" >> "${output}"
    echo "__RUNTIME_PAYLOAD__" >> "${output}"

    # Append runtime payload (file already has trailing newline — ends the installer)
    cat "${runtime_b64_file}" >> "${output}"

    chmod 755 "${output}"

    # Clean up per-arch b64 temp file (keep app b64 for next arch build)
    rm -f "${runtime_b64_file}"

    local final_size
    final_size=$(du -h "${output}" | awk '{print $1}')

    echo ""
    echo -e "${GREEN}${BOLD}  Built: ${CYAN}${output##*/}${GREEN}  (${final_size})${NC}"
}

# -------------------------------------------------------------------
# Main: download PBS for each arch and build installers
# -------------------------------------------------------------------
declare -a ARCHES=("x86_64" "aarch64")

fetch_sha256sums

for ARCH in "${ARCHES[@]}"; do
    download_pbs "${ARCH}"
    build_installer "${ARCH}" "${PBS_TARBALL_PATH}"
done

# Clean up the shared app b64
rm -f "${BUILD_CACHE}/app-v${VERSION}.b64"

echo ""
echo -e "${GREEN}${BOLD}============================================${NC}"
echo -e "${GREEN}${BOLD}  Release builds complete!${NC}"
echo -e "${GREEN}${BOLD}============================================${NC}"
echo ""
echo -e "  Transfer to target and run (auto-detect arch):"
echo -e "    ${YELLOW}ARCH=\$(uname -m)${NC}"
echo -e "    ${YELLOW}bash qn-code-assistant-v${VERSION}-linux-\${ARCH}.sh${NC}"
echo ""
echo -e "  Or install to a custom directory:"
echo -e "    ${YELLOW}bash qn-code-assistant-v${VERSION}-linux-\${ARCH}.sh --dir /home/user/qn${NC}"
echo ""
