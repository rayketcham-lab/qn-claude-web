#!/bin/bash
#
# QN Code Assistant - Release Builder
# Creates a self-extracting installer (single .sh file) with all project files embedded.
#
# Usage: ./build-release.sh
# Output: qn-code-assistant-v<VERSION>.sh
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

# Get version from app.py
VERSION=$(grep -oP "VERSION\s*=\s*['\"]([^'\"]+)['\"]" "${SCRIPT_DIR}/app.py" | head -1 | grep -oP "['\"][^'\"]+['\"]" | tr -d "'\"" || echo "unknown")
OUTPUT="${SCRIPT_DIR}/qn-code-assistant-v${VERSION}.sh"

echo -e "${GREEN}${BOLD}Building QN Code Assistant self-extracting installer v${VERSION}...${NC}"
echo ""

# Files and directories to include
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

# Verify all files exist
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

# Create zip archive using Python (no external zip tool needed)
echo -e "  Creating archive..."
ARCHIVE_B64=$(cd "${SCRIPT_DIR}" && python3 -c "
import zipfile, io, base64, os

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    # Add individual files
    files = '''$(printf '%s\n' "${INCLUDE_FILES[@]}")'''.strip().split('\n')
    for f in files:
        f = f.strip()
        if f and os.path.isfile(f):
            zf.write(f)

    # Add vendor directory
    for root, dirs, filenames in os.walk('vendor'):
        # Skip __pycache__
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for fn in filenames:
            filepath = os.path.join(root, fn)
            zf.write(filepath)

    # Add static/js/ace/ directory
    for root, dirs, filenames in os.walk('static/js/ace'):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for fn in filenames:
            filepath = os.path.join(root, fn)
            zf.write(filepath)

buf.seek(0)
print(base64.b64encode(buf.read()).decode(), end='')
")

ARCHIVE_SIZE=$(echo -n "${ARCHIVE_B64}" | wc -c)
ARCHIVE_SIZE_MB=$(python3 -c "print(f'{${ARCHIVE_SIZE}/1048576:.1f}')")
echo -e "  Archive size: ${ARCHIVE_SIZE_MB}MB (base64 encoded)"

# Count files in archive
FILE_COUNT=$(cd "${SCRIPT_DIR}" && python3 -c "
import os
count = len('''$(printf '%s\n' "${INCLUDE_FILES[@]}")'''.strip().split('\n'))
for walk_dir in ['vendor', 'static/js/ace']:
    for root, dirs, files in os.walk(walk_dir):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        count += len(files)
print(count)
")
echo -e "  Files included: ${FILE_COUNT}"

# Compute SHA-256 of the archive payload
PAYLOAD_HASH=$(echo "${ARCHIVE_B64}" | sha256sum | awk '{print $1}')
echo -e "  Payload hash: ${PAYLOAD_HASH}"

echo ""
echo -e "${YELLOW}Generating ${OUTPUT}...${NC}"

# Write the self-extracting installer
cat > "${OUTPUT}" << 'HEADER'
#!/bin/bash
#
# QN Code Assistant - Self-Extracting Installer
# This file contains the complete application with all dependencies.
# Just run it - no other files needed.
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

# Inject version and hash
cat >> "${OUTPUT}" << EOF
VERSION="${VERSION}"
PAYLOAD_HASH="${PAYLOAD_HASH}"
FILE_COUNT="${FILE_COUNT}"
EOF

cat >> "${OUTPUT}" << 'BODY'
INSTALL_DIR="/opt/qn-code-assistant"
EXTRACT_ONLY=0

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
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
            echo "Self-contained: includes all files + vendored Python dependencies."
            echo "Only requires Python 3.10+ on the target system."
            echo ""
            echo "Payload: ${FILE_COUNT} files, SHA-256: ${PAYLOAD_HASH}"
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

# Check Python
if ! command -v python3 &> /dev/null; then
    log_error "Python 3 is required but not installed."
    exit 1
fi

py_version="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
py_major="$(echo "${py_version}" | cut -d. -f1)"
py_minor="$(echo "${py_version}" | cut -d. -f2)"
if [[ "${py_major}" -lt 3 ]] || { [[ "${py_major}" -eq 3 ]] && [[ "${py_minor}" -lt 10 ]]; }; then
    log_error "Python 3.10+ required, found ${py_version}"
    exit 1
fi
log_info "Python ${py_version} found"

# -------------------------------------------------------------------
# Extract payload
# -------------------------------------------------------------------

echo ""
log_info "Extracting ${FILE_COUNT} files to ${INSTALL_DIR}..."

# Find payload line
PAYLOAD_LINE=$(awk '/^__PAYLOAD__$/ { print NR + 1; exit }' "$0")
if [[ -z "${PAYLOAD_LINE}" ]]; then
    log_error "Payload marker not found. File may be corrupted."
    exit 1
fi

# Verify payload integrity
log_info "Verifying payload integrity..."
ACTUAL_HASH=$(tail -n +"${PAYLOAD_LINE}" "$0" | sha256sum | awk '{print $1}')
if [[ "${ACTUAL_HASH}" != "${PAYLOAD_HASH}" ]]; then
    log_error "Payload integrity check failed!"
    echo "         Expected: ${PAYLOAD_HASH}"
    echo "         Actual:   ${ACTUAL_HASH}"
    log_error "File may have been corrupted or tampered with."
    exit 1
fi
log_info "Payload verified"

# Create install directory
mkdir -p "${INSTALL_DIR}"

# Extract using Python (no external tools needed beyond Python 3.10+)
tail -n +"${PAYLOAD_LINE}" "$0" | python3 -c "
import zipfile, io, base64, sys, os

data = base64.b64decode(sys.stdin.read().strip())
buf = io.BytesIO(data)
target = '${INSTALL_DIR}'

with zipfile.ZipFile(buf, 'r') as zf:
    count = 0
    for info in zf.infolist():
        zf.extract(info, target)
        count += 1

print(f'Extracted {count} files')
"

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

# Payload follows - DO NOT edit below this line
__PAYLOAD__
BODY

# Append the base64 payload
echo "${ARCHIVE_B64}" >> "${OUTPUT}"

chmod 755 "${OUTPUT}"

# Final size
FINAL_SIZE=$(du -h "${OUTPUT}" | awk '{print $1}')

echo ""
echo -e "${GREEN}${BOLD}============================================${NC}"
echo -e "${GREEN}${BOLD}  Self-extracting installer built!${NC}"
echo -e "${GREEN}${BOLD}============================================${NC}"
echo ""
echo -e "  Output:   ${CYAN}${OUTPUT}${NC}"
echo -e "  Version:  ${CYAN}${VERSION}${NC}"
echo -e "  Size:     ${CYAN}${FINAL_SIZE}${NC}"
echo -e "  Files:    ${CYAN}${FILE_COUNT}${NC}"
echo -e "  Hash:     ${CYAN}${PAYLOAD_HASH}${NC}"
echo ""
echo -e "  Transfer to target machine and run:"
echo -e "    ${YELLOW}chmod +x qn-code-assistant-v${VERSION}.sh${NC}"
echo -e "    ${YELLOW}./qn-code-assistant-v${VERSION}.sh${NC}"
echo ""
echo -e "  Or install to a custom directory:"
echo -e "    ${YELLOW}./qn-code-assistant-v${VERSION}.sh --dir /home/user/qn-code${NC}"
echo ""
