#!/bin/bash
#
# Snowmelt Control System - Installation Script
# Run this script on a fresh Raspberry Pi OS installation
#
# Usage: sudo ./install.sh
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/home/pi/snowmelt_control"
SERVICE_USER="pi"
LOG_DIR="/var/log/snowmelt"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Snowmelt Control System Installer    ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root (use sudo)${NC}" 
   exit 1
fi

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo -e "${YELLOW}Warning: This doesn't appear to be a Raspberry Pi${NC}"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo -e "${GREEN}Step 1: Updating system packages...${NC}"
apt-get update
apt-get upgrade -y

echo -e "${GREEN}Step 2: Installing system dependencies...${NC}"
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-pyqt5 \
    python3-dev \
    git \
    i2c-tools \
    libgpiod2 \
    fonts-dejavu \
    libatlas-base-dev \
    libopenjp2-7 \
    libtiff5

echo -e "${GREEN}Step 3: Enabling 1-Wire interface...${NC}"
# Add 1-Wire configuration to config.txt if not present
if ! grep -q "dtoverlay=w1-gpio,gpiopin=23" /boot/firmware/config.txt 2>/dev/null && \
   ! grep -q "dtoverlay=w1-gpio,gpiopin=23" /boot/config.txt 2>/dev/null; then
    
    # Determine which config file to use
    if [ -f /boot/firmware/config.txt ]; then
        CONFIG_FILE="/boot/firmware/config.txt"
    else
        CONFIG_FILE="/boot/config.txt"
    fi
    
    echo "" >> "$CONFIG_FILE"
    echo "# 1-Wire temperature sensors on GPIO 23" >> "$CONFIG_FILE"
    echo "dtoverlay=w1-gpio,gpiopin=23" >> "$CONFIG_FILE"
    echo -e "${YELLOW}1-Wire enabled on GPIO 23. Reboot required.${NC}"
fi

echo -e "${GREEN}Step 4: Loading 1-Wire kernel modules...${NC}"
modprobe w1-gpio || true
modprobe w1-therm || true

# Add modules to load at boot
if ! grep -q "w1-gpio" /etc/modules; then
    echo "w1-gpio" >> /etc/modules
fi
if ! grep -q "w1-therm" /etc/modules; then
    echo "w1-therm" >> /etc/modules
fi

echo -e "${GREEN}Step 5: Setting up GPIO permissions...${NC}"
# Add user to gpio group
usermod -a -G gpio,i2c,spi "$SERVICE_USER" || true

echo -e "${GREEN}Step 6: Creating installation directory...${NC}"
mkdir -p "$INSTALL_DIR"
chown "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR"

echo -e "${GREEN}Step 7: Creating log directory...${NC}"
mkdir -p "$LOG_DIR"
chown "$SERVICE_USER":"$SERVICE_USER" "$LOG_DIR"
chmod 755 "$LOG_DIR"

echo -e "${GREEN}Step 8: Creating Python virtual environment...${NC}"
sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/venv"

echo -e "${GREEN}Step 9: Installing Python dependencies...${NC}"
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install paho-mqtt PyYAML RPi.GPIO

# PyQt5 is typically installed system-wide on RPi OS
# Link it to the virtual environment
SITE_PACKAGES=$("$INSTALL_DIR/venv/bin/python" -c "import site; print(site.getsitepackages()[0])")
ln -sf /usr/lib/python3/dist-packages/PyQt5 "$SITE_PACKAGES/" 2>/dev/null || true
ln -sf /usr/lib/python3/dist-packages/sip* "$SITE_PACKAGES/" 2>/dev/null || true

echo -e "${GREEN}Step 10: Copying application files...${NC}"
# Copy files if running from the project directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/main.py" ]; then
    cp "$SCRIPT_DIR"/*.py "$INSTALL_DIR/"
    cp "$SCRIPT_DIR"/*.yaml "$INSTALL_DIR/" 2>/dev/null || true
    cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"
    chown -R "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR"
fi

echo -e "${GREEN}Step 11: Setting up secrets file...${NC}"
if [ ! -f "$INSTALL_DIR/secrets.yaml" ]; then
    cat > "$INSTALL_DIR/secrets.yaml" << 'EOF'
# Snowmelt Control System - Secrets Configuration
# Fill in your MQTT credentials below

mqtt:
  broker: "192.168.1.201"
  port: 1883
  username: "your_mqtt_username"
  password: "your_mqtt_password"
  base_topic: "snowmelt"
  discovery_prefix: "homeassistant"
EOF
    chown "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR/secrets.yaml"
    chmod 600 "$INSTALL_DIR/secrets.yaml"
    echo -e "${YELLOW}Created secrets.yaml - please edit with your MQTT credentials${NC}"
fi

echo -e "${GREEN}Step 12: Installing systemd service...${NC}"
if [ -f "$SCRIPT_DIR/snowmelt.service" ]; then
    cp "$SCRIPT_DIR/snowmelt.service" /etc/systemd/system/
    cp "$SCRIPT_DIR/snowmelt-headless.service" /etc/systemd/system/
    systemctl daemon-reload
    echo -e "${YELLOW}Service files installed. Enable with:${NC}"
    echo -e "${YELLOW}  sudo systemctl enable snowmelt.service${NC}"
    echo -e "${YELLOW}  OR for headless:${NC}"
    echo -e "${YELLOW}  sudo systemctl enable snowmelt-headless.service${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Installation Complete!               ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Next steps:"
echo -e "  1. Edit ${YELLOW}$INSTALL_DIR/secrets.yaml${NC} with your MQTT credentials"
echo -e "  2. Edit ${YELLOW}$INSTALL_DIR/config.yaml${NC} to verify sensor addresses"
echo -e "  3. Reboot the Raspberry Pi: ${YELLOW}sudo reboot${NC}"
echo -e "  4. After reboot, enable the service:"
echo -e "     ${YELLOW}sudo systemctl enable --now snowmelt.service${NC}"
echo ""
echo -e "To test manually:"
echo -e "  ${YELLOW}cd $INSTALL_DIR${NC}"
echo -e "  ${YELLOW}./venv/bin/python main.py --mock-sensors${NC}"
echo ""
