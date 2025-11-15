#!/bin/bash
# Setup script for Lynch Stock Screener nightly batch process
#
# This script helps you set up the nightly stock data refresh scheduler.
# It supports both systemd timers (recommended) and cron.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$SCRIPT_DIR"

echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}Lynch Stock Screener - Scheduler Setup${NC}"
echo -e "${BLUE}======================================${NC}"
echo ""

# Check if running on systemd-based system
has_systemd() {
    command -v systemctl >/dev/null 2>&1
}

# Setup systemd timer
setup_systemd() {
    echo -e "${GREEN}Setting up systemd timer...${NC}"

    # Check if systemd is available
    if ! has_systemd; then
        echo -e "${RED}Error: systemd not found on this system${NC}"
        echo -e "${YELLOW}Please use cron setup instead${NC}"
        return 1
    fi

    # Create user systemd directory if it doesn't exist
    mkdir -p ~/.config/systemd/user

    # Update paths in service file with actual paths
    SERVICE_FILE="$HOME/.config/systemd/user/stock-refresh.service"
    TIMER_FILE="$HOME/.config/systemd/user/stock-refresh.timer"

    # Copy and update service file
    sed "s|%u|$USER|g; s|/home/user|$HOME|g" "$BACKEND_DIR/systemd/stock-refresh.service" > "$SERVICE_FILE"

    # Copy timer file
    cp "$BACKEND_DIR/systemd/stock-refresh.timer" "$TIMER_FILE"

    echo -e "${GREEN}✓ Service and timer files created${NC}"
    echo "  Service: $SERVICE_FILE"
    echo "  Timer: $TIMER_FILE"
    echo ""

    # Reload systemd
    systemctl --user daemon-reload

    # Enable and start timer
    systemctl --user enable stock-refresh.timer
    systemctl --user start stock-refresh.timer

    echo -e "${GREEN}✓ Systemd timer enabled and started${NC}"
    echo ""

    # Show status
    echo -e "${BLUE}Timer Status:${NC}"
    systemctl --user status stock-refresh.timer --no-pager
    echo ""
    echo -e "${BLUE}Next scheduled run:${NC}"
    systemctl --user list-timers stock-refresh.timer --no-pager
    echo ""

    echo -e "${GREEN}Systemd setup complete!${NC}"
    echo ""
    echo -e "${YELLOW}Useful commands:${NC}"
    echo "  View timer status:     systemctl --user status stock-refresh.timer"
    echo "  View service status:   systemctl --user status stock-refresh.service"
    echo "  View logs:             journalctl --user -u stock-refresh.service -f"
    echo "  Run manually now:      systemctl --user start stock-refresh.service"
    echo "  Stop timer:            systemctl --user stop stock-refresh.timer"
    echo "  Disable timer:         systemctl --user disable stock-refresh.timer"
    echo ""
}

# Setup cron
setup_cron() {
    echo -e "${GREEN}Setting up cron job...${NC}"
    echo ""

    # Create the cron entry
    CRON_ENTRY="0 2 * * * cd $BACKEND_DIR && /usr/bin/python3 batch_refresh.py --config batch_config.json >> logs/cron.log 2>&1"

    echo -e "${YELLOW}Add the following line to your crontab:${NC}"
    echo ""
    echo "$CRON_ENTRY"
    echo ""
    echo -e "${BLUE}To edit your crontab, run:${NC}"
    echo "  crontab -e"
    echo ""
    echo -e "${BLUE}Current crontab:${NC}"
    crontab -l 2>/dev/null || echo "  (no crontab installed)"
    echo ""

    read -p "Would you like to add this cron job automatically? (y/N) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Backup existing crontab
        crontab -l > /tmp/crontab.backup 2>/dev/null || true

        # Add new entry if it doesn't exist
        (crontab -l 2>/dev/null || true; echo "$CRON_ENTRY") | crontab -

        echo -e "${GREEN}✓ Cron job added successfully${NC}"
        echo ""
        echo -e "${BLUE}Current crontab:${NC}"
        crontab -l
    else
        echo -e "${YELLOW}Skipped automatic installation${NC}"
    fi
    echo ""
}

# Test the batch process
test_batch() {
    echo -e "${GREEN}Testing batch process...${NC}"
    echo ""
    echo -e "${BLUE}Running dry-run with limit of 5 stocks...${NC}"
    echo ""

    cd "$BACKEND_DIR"
    python3 batch_refresh.py --dry-run --limit 5 --verbose

    echo ""
    echo -e "${GREEN}Test complete!${NC}"
    echo ""
}

# Create necessary directories
setup_directories() {
    echo -e "${GREEN}Creating necessary directories...${NC}"
    cd "$BACKEND_DIR"
    mkdir -p logs backups reports
    echo -e "${GREEN}✓ Directories created${NC}"
    echo ""
}

# Main menu
show_menu() {
    echo -e "${BLUE}What would you like to do?${NC}"
    echo ""
    echo "  1) Setup systemd timer (recommended for Linux servers)"
    echo "  2) Setup cron job (alternative method)"
    echo "  3) Test batch process (dry-run)"
    echo "  4) Create directories only"
    echo "  5) Exit"
    echo ""
    read -p "Enter your choice (1-5): " choice

    case $choice in
        1)
            setup_directories
            setup_systemd
            ;;
        2)
            setup_directories
            setup_cron
            ;;
        3)
            test_batch
            ;;
        4)
            setup_directories
            ;;
        5)
            echo -e "${GREEN}Exiting...${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid choice${NC}"
            exit 1
            ;;
    esac
}

# Main
main() {
    # Check if Python 3 is available
    if ! command -v python3 >/dev/null 2>&1; then
        echo -e "${RED}Error: Python 3 is required but not found${NC}"
        exit 1
    fi

    # Check if we're in the right directory
    if [ ! -f "$BACKEND_DIR/batch_refresh.py" ]; then
        echo -e "${RED}Error: batch_refresh.py not found${NC}"
        echo "Make sure you're running this script from the backend directory"
        exit 1
    fi

    # Show menu
    show_menu
}

main
