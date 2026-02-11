#!/usr/bin/env bash
# =============================================================================
# QN Code Assistant — Kali Security Scan
# =============================================================================
# SSHes into a Kali Linux host and runs security tools against the target.
#
# Usage:
#   ./kali_scan.sh --target http://192.168.1.241:5001 --level standard --output ./results/kali/
#
# Prerequisites:
#   - SSH access to Kali host (key-based auth, BatchMode)
#   - nmap, nikto, zaproxy (or docker), sqlmap installed on Kali
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
TARGET=""
LEVEL="standard"
OUTPUT_DIR="./results/kali"
KALI_HOST="kali"
SSH_OPTS="-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SUMMARY_FILE=""
CRITICAL_COUNT=0
HIGH_COUNT=0

# Temporary files created on Kali for cleanup
KALI_TMPFILES=()

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --target URL        Target URL (required)
  --level LEVEL       Scan level: quick | standard | full (default: standard)
  --output DIR        Output directory (default: ./results/kali/)
  --kali-host HOST    Kali SSH host (default: kali)
  -h, --help          Show this help message

Examples:
  $(basename "$0") --target http://192.168.1.241:5001
  $(basename "$0") --target https://10.0.0.5:5001 --level full --kali-host kali-vm
EOF
    exit 0
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --target)   TARGET="$2"; shift 2 ;;
        --level)    LEVEL="$2"; shift 2 ;;
        --output)   OUTPUT_DIR="$2"; shift 2 ;;
        --kali-host) KALI_HOST="$2"; shift 2 ;;
        -h|--help)  usage ;;
        *)          echo "[ERROR] Unknown argument: $1" >&2; usage ;;
    esac
done

if [[ -z "$TARGET" ]]; then
    echo "[ERROR] --target is required" >&2
    usage
fi

# ---------------------------------------------------------------------------
# Extract host and port from target URL
# ---------------------------------------------------------------------------
# Strip protocol
HOST_PORT="${TARGET#*://}"
# Strip trailing path
HOST_PORT="${HOST_PORT%%/*}"

if [[ "$HOST_PORT" == *:* ]]; then
    HOST="${HOST_PORT%%:*}"
    PORT="${HOST_PORT##*:}"
else
    HOST="$HOST_PORT"
    if [[ "$TARGET" == https://* ]]; then
        PORT=443
    else
        PORT=80
    fi
fi

echo "============================================================"
echo " QN Code Assistant — Kali Security Scan"
echo "============================================================"
echo " Target : $TARGET"
echo " Host   : $HOST"
echo " Port   : $PORT"
echo " Level  : $LEVEL"
echo " Kali   : $KALI_HOST"
echo " Output : $OUTPUT_DIR"
echo " Time   : $TIMESTAMP"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# Validate level
# ---------------------------------------------------------------------------
case "$LEVEL" in
    quick|standard|full) ;;
    *)
        echo "[ERROR] Invalid level: $LEVEL. Must be quick, standard, or full." >&2
        exit 1
        ;;
esac

# ---------------------------------------------------------------------------
# Create output directory
# ---------------------------------------------------------------------------
mkdir -p "$OUTPUT_DIR"
SUMMARY_FILE="$OUTPUT_DIR/summary.json"

# ---------------------------------------------------------------------------
# Cleanup trap — remove temporary files on Kali
# ---------------------------------------------------------------------------
cleanup() {
    if [[ ${#KALI_TMPFILES[@]} -gt 0 ]]; then
        echo "[*] Cleaning up temporary files on $KALI_HOST..."
        for f in "${KALI_TMPFILES[@]}"; do
            ssh $SSH_OPTS "$KALI_HOST" "rm -rf '$f'" 2>/dev/null || true
        done
    fi
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Helper: SSH to Kali
# ---------------------------------------------------------------------------
kali_ssh() {
    ssh $SSH_OPTS "$KALI_HOST" "$@"
}

# ---------------------------------------------------------------------------
# Helper: SCP from Kali
# ---------------------------------------------------------------------------
kali_scp() {
    local remote_path="$1"
    local local_path="$2"
    scp $SSH_OPTS "$KALI_HOST:$remote_path" "$local_path" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Helper: write error summary and exit
# ---------------------------------------------------------------------------
write_error_summary() {
    local msg="$1"
    cat > "$SUMMARY_FILE" <<ENDJSON
{
  "target": "$TARGET",
  "level": "$LEVEL",
  "timestamp": "$TIMESTAMP",
  "error": "$msg",
  "tools": {},
  "critical_count": 0,
  "high_count": 0
}
ENDJSON
    echo "[ERROR] $msg" >&2
    exit 1
}

# ---------------------------------------------------------------------------
# Verify Kali SSH connectivity
# ---------------------------------------------------------------------------
echo "[*] Verifying SSH connectivity to $KALI_HOST..."
if ! kali_ssh "echo ok" &>/dev/null; then
    write_error_summary "Cannot reach Kali host '$KALI_HOST' via SSH"
fi
echo "[+] Kali host is reachable."
echo ""

# ---------------------------------------------------------------------------
# Tool tracking
# ---------------------------------------------------------------------------
declare -A TOOL_STATUS

mark_tool() {
    local tool="$1"
    local status="$2"
    TOOL_STATUS["$tool"]="$status"
}

# ===========================================================================
# NMAP SCAN (all levels)
# ===========================================================================
run_nmap() {
    echo "------------------------------------------------------------"
    echo "[*] Running nmap scan..."
    echo "------------------------------------------------------------"

    local remote_out="/tmp/nmap_qn_${TIMESTAMP}.txt"
    KALI_TMPFILES+=("$remote_out")

    if kali_ssh "command -v nmap" &>/dev/null; then
        if kali_ssh "nmap -sV -sC --script=http-headers,http-methods,http-server-header -p $PORT $HOST -oN $remote_out" 2>&1; then
            kali_scp "$remote_out" "$OUTPUT_DIR/nmap_scan.txt" && \
                echo "[+] nmap results saved to $OUTPUT_DIR/nmap_scan.txt"
            mark_tool "nmap" "completed"
        else
            echo "[!] nmap scan encountered errors"
            mark_tool "nmap" "error"
        fi
    else
        echo "[!] nmap not found on $KALI_HOST — skipping"
        mark_tool "nmap" "not_installed"
    fi
    echo ""
}

# ===========================================================================
# NIKTO SCAN (standard + full)
# ===========================================================================
run_nikto() {
    echo "------------------------------------------------------------"
    echo "[*] Running nikto scan..."
    echo "------------------------------------------------------------"

    local remote_out="/tmp/nikto_qn_${TIMESTAMP}.txt"
    KALI_TMPFILES+=("$remote_out")

    if kali_ssh "command -v nikto" &>/dev/null; then
        if kali_ssh "nikto -h $TARGET -o $remote_out -Format txt -Tuning 1234567890 -maxtime 300" 2>&1; then
            kali_scp "$remote_out" "$OUTPUT_DIR/nikto_scan.txt" && \
                echo "[+] nikto results saved to $OUTPUT_DIR/nikto_scan.txt"
            mark_tool "nikto" "completed"

            # Count high-severity nikto findings (OSVDB entries)
            if [[ -f "$OUTPUT_DIR/nikto_scan.txt" ]]; then
                local osvdb_count
                osvdb_count=$(grep -c "OSVDB" "$OUTPUT_DIR/nikto_scan.txt" 2>/dev/null || echo "0")
                if [[ "$osvdb_count" -gt 5 ]]; then
                    HIGH_COUNT=$((HIGH_COUNT + 1))
                fi
            fi
        else
            echo "[!] nikto scan encountered errors"
            mark_tool "nikto" "error"
        fi
    else
        echo "[!] nikto not found on $KALI_HOST — skipping"
        mark_tool "nikto" "not_installed"
    fi
    echo ""
}

# ===========================================================================
# OWASP ZAP (standard: baseline, full: active)
# ===========================================================================
run_zap() {
    echo "------------------------------------------------------------"
    echo "[*] Running OWASP ZAP scan..."
    echo "------------------------------------------------------------"

    local remote_out="/tmp/zap_qn_${TIMESTAMP}"
    KALI_TMPFILES+=("$remote_out" "${remote_out}.html" "${remote_out}.json")

    # Try docker-based ZAP first, then native zap-cli
    local zap_mode=""
    if kali_ssh "docker image ls 2>/dev/null | grep -q zaproxy" 2>/dev/null; then
        zap_mode="docker"
    elif kali_ssh "command -v zap-cli" &>/dev/null; then
        zap_mode="native"
    else
        echo "[!] Neither ZAP docker image nor zap-cli found on $KALI_HOST — skipping"
        mark_tool "zap" "not_installed"
        echo ""
        return
    fi

    if [[ "$LEVEL" == "full" ]]; then
        echo "[*] ZAP mode: active scan ($zap_mode)"
        if [[ "$zap_mode" == "docker" ]]; then
            kali_ssh "docker run --rm -v /tmp:/zap/wrk zaproxy/zap-stable zap-full-scan.py -t $TARGET -r qn_zap_report.html -J qn_zap_report.json 2>&1 || true"
            kali_scp "/tmp/qn_zap_report.html" "$OUTPUT_DIR/zap_report.html" 2>/dev/null || true
            kali_scp "/tmp/qn_zap_report.json" "$OUTPUT_DIR/zap_report.json" 2>/dev/null || true
            KALI_TMPFILES+=("/tmp/qn_zap_report.html" "/tmp/qn_zap_report.json")
        else
            kali_ssh "zap-cli active-scan $TARGET 2>&1 || true"
            kali_ssh "zap-cli report -o ${remote_out}.html -f html 2>/dev/null || true"
            kali_scp "${remote_out}.html" "$OUTPUT_DIR/zap_report.html" 2>/dev/null || true
        fi
    else
        echo "[*] ZAP mode: baseline scan ($zap_mode)"
        if [[ "$zap_mode" == "docker" ]]; then
            kali_ssh "docker run --rm -v /tmp:/zap/wrk zaproxy/zap-stable zap-baseline.py -t $TARGET -r qn_zap_report.html -J qn_zap_report.json 2>&1 || true"
            kali_scp "/tmp/qn_zap_report.html" "$OUTPUT_DIR/zap_report.html" 2>/dev/null || true
            kali_scp "/tmp/qn_zap_report.json" "$OUTPUT_DIR/zap_report.json" 2>/dev/null || true
            KALI_TMPFILES+=("/tmp/qn_zap_report.html" "/tmp/qn_zap_report.json")
        else
            kali_ssh "zap-cli quick-scan -s xss,sqli $TARGET 2>&1 || true"
            kali_ssh "zap-cli report -o ${remote_out}.html -f html 2>/dev/null || true"
            kali_scp "${remote_out}.html" "$OUTPUT_DIR/zap_report.html" 2>/dev/null || true
        fi
    fi

    if [[ -f "$OUTPUT_DIR/zap_report.html" ]] || [[ -f "$OUTPUT_DIR/zap_report.json" ]]; then
        echo "[+] ZAP results saved to $OUTPUT_DIR/"
        mark_tool "zap" "completed"

        # Parse JSON report for alert counts if available
        if [[ -f "$OUTPUT_DIR/zap_report.json" ]]; then
            local zap_high
            zap_high=$(python3 -c "
import json, sys
try:
    data = json.load(open('$OUTPUT_DIR/zap_report.json'))
    alerts = data.get('site', [{}])[0].get('alerts', []) if isinstance(data.get('site'), list) else []
    high = sum(1 for a in alerts if a.get('riskcode', '0') in ('3',))
    crit = sum(1 for a in alerts if a.get('riskcode', '0') in ('4',))
    print(f'{crit},{high}')
except Exception:
    print('0,0')
" 2>/dev/null || echo "0,0")
            local zap_crit="${zap_high%%,*}"
            local zap_hi="${zap_high##*,}"
            CRITICAL_COUNT=$((CRITICAL_COUNT + zap_crit))
            HIGH_COUNT=$((HIGH_COUNT + zap_hi))
        fi
    else
        echo "[!] ZAP did not produce output files"
        mark_tool "zap" "error"
    fi
    echo ""
}

# ===========================================================================
# SQLMAP (full only)
# ===========================================================================
run_sqlmap() {
    echo "------------------------------------------------------------"
    echo "[*] Running sqlmap scan..."
    echo "------------------------------------------------------------"

    local remote_out="/tmp/sqlmap_qn_${TIMESTAMP}"
    KALI_TMPFILES+=("$remote_out")

    if ! kali_ssh "command -v sqlmap" &>/dev/null; then
        echo "[!] sqlmap not found on $KALI_HOST — skipping"
        mark_tool "sqlmap" "not_installed"
        echo ""
        return
    fi

    local endpoints=(
        "$TARGET/api/files?path=test"
        "$TARGET/api/files/read?path=test"
        "$TARGET/api/sessions/search?q=test"
    )

    local sqlmap_found=0
    for url in "${endpoints[@]}"; do
        echo "[*] Testing: $url"
        local result
        result=$(kali_ssh "sqlmap -u '$url' --batch --level=1 --risk=1 --output-dir=$remote_out --timeout=10 --retries=1 2>&1" || true)

        if echo "$result" | grep -qi "is vulnerable\|injectable\|sql injection"; then
            echo "[!!] Potential SQL injection found at: $url"
            CRITICAL_COUNT=$((CRITICAL_COUNT + 1))
            sqlmap_found=1
        fi
    done

    # Copy results back
    kali_scp "$remote_out" "$OUTPUT_DIR/sqlmap/" 2>/dev/null && \
        echo "[+] sqlmap results saved to $OUTPUT_DIR/sqlmap/" || \
        echo "[*] No sqlmap output files to retrieve"

    if [[ $sqlmap_found -eq 0 ]]; then
        echo "[+] No SQL injection vulnerabilities detected"
    fi
    mark_tool "sqlmap" "completed"
    echo ""
}

# ===========================================================================
# Run scans based on level
# ===========================================================================

# All levels: nmap
run_nmap

# Standard and full: nikto + ZAP baseline
if [[ "$LEVEL" == "standard" || "$LEVEL" == "full" ]]; then
    run_nikto
    run_zap
fi

# Full only: sqlmap + ZAP active (ZAP handles this internally based on level)
if [[ "$LEVEL" == "full" ]]; then
    run_sqlmap
fi

# ===========================================================================
# Generate summary
# ===========================================================================
echo "============================================================"
echo "[*] Generating summary report..."
echo "============================================================"

# Build tools JSON block
TOOLS_JSON="{"
first=true
for tool in "${!TOOL_STATUS[@]}"; do
    if [[ "$first" == true ]]; then
        first=false
    else
        TOOLS_JSON+=","
    fi
    TOOLS_JSON+="\"$tool\":\"${TOOL_STATUS[$tool]}\""
done
TOOLS_JSON+="}"

cat > "$SUMMARY_FILE" <<ENDJSON
{
  "target": "$TARGET",
  "host": "$HOST",
  "port": $PORT,
  "level": "$LEVEL",
  "timestamp": "$TIMESTAMP",
  "tools": $TOOLS_JSON,
  "critical_count": $CRITICAL_COUNT,
  "high_count": $HIGH_COUNT,
  "output_dir": "$OUTPUT_DIR"
}
ENDJSON

echo ""
echo "[+] Summary written to $SUMMARY_FILE"
echo ""
echo "------------------------------------------------------------"
echo " Results Summary"
echo "------------------------------------------------------------"
echo " Critical findings : $CRITICAL_COUNT"
echo " High findings     : $HIGH_COUNT"
echo " Tools run         : ${!TOOL_STATUS[*]}"
echo "------------------------------------------------------------"

# Exit with failure if critical findings were detected
if [[ $CRITICAL_COUNT -gt 0 ]]; then
    echo ""
    echo "[!!] CRITICAL vulnerabilities detected — exiting with failure"
    exit 1
fi

echo ""
echo "[+] Scan complete."
exit 0
