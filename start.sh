#!/bin/bash
#
# QN Code Assistant - Startup Script
#

cd "$(dirname "$0")"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════╗"
echo "║         QN Code Assistant                         ║"
echo "╚═══════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is required but not installed.${NC}"
    exit 1
fi

# Verify vendor directory exists
if [ ! -d "vendor" ]; then
    echo -e "${RED}Error: vendor/ directory not found. Dependencies are missing.${NC}"
    echo -e "${YELLOW}Run the installer or pip install --target=vendor/ flask flask-socketio${NC}"
    exit 1
fi

# Check for Claude CLI
if ! command -v claude &> /dev/null; then
    echo -e "${YELLOW}Warning: 'claude' CLI not found in PATH.${NC}"
    echo -e "${YELLOW}Make sure Claude Code is installed and accessible.${NC}"
fi

# Check for tmux (needed for persistent terminal sessions)
if ! command -v tmux &> /dev/null; then
    echo -e "${YELLOW}Warning: tmux is not installed — persistent terminal sessions will not work.${NC}"
    echo -e "${YELLOW}Install with: sudo apt install tmux${NC}"
fi

# Start the server
echo ""
echo -e "${GREEN}Starting server...${NC}"
echo -e "${GREEN}Access the web interface at: http://localhost:5001${NC}"
echo -e "${GREEN}For LAN access: http://$(hostname -I | awk '{print $1}'):5001${NC}"
echo ""

python3 app.py
