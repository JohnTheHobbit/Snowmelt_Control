# Snowmelt Control System - Installation & Setup Guide

## Table of Contents
1. [System Overview](#system-overview)
2. [Hardware Requirements](#hardware-requirements)
3. [File Structure](#file-structure)
4. [Fresh Raspberry Pi OS Installation](#fresh-raspberry-pi-os-installation)
5. [System Configuration](#system-configuration)
6. [Software Installation](#software-installation)
7. [Hardware Setup](#hardware-setup)
8. [Configuration Files](#configuration-files)
9. [Home Assistant Integration](#home-assistant-integration)
10. [Starting the System](#starting-the-system)
11. [Troubleshooting](#troubleshooting)

---

## System Overview

This control system manages:
- **Snowmelt System**: Glycol circulation through heated slab with heat exchanger
- **DHW System**: Domestic hot water recirculation
- **Eco Mode**: Reduced temperature setpoints during scheduled hours

### Control Logic
- Equipment operates in three modes: **Auto**, **On**, **Off**
- Auto mode follows system logic; On/Off provides manual override
- Temperature-based control with high setpoint and delta T (differential)

---

## Hardware Requirements

### Computing
- Raspberry Pi 4B (2GB+ RAM recommended)
- MicroSD card (16GB+ recommended)
- Power supply (official RPi 5V 3A recommended)

### Display
- Waveshare 7" touchscreen (800x480)

### Relay Control
- Oono 8-channel SPST relay HAT

### Temperature Sensors
- 5x DS18B20 1-Wire temperature sensors
- 4.7kΩ pull-up resistor (if not built into sensor cables)

### Wiring Supplies
- Jumper wires
- Terminal blocks (for relay connections)
- 18-22 AWG wire for relay outputs

---

## File Structure

```
/home/pi/snowmelt_control/
├── main.py                 # Main application entry point
├── sensors.py              # Temperature sensor management
├── relays.py               # Relay control module
├── control.py              # Control logic engine
├── mqtt_integration.py     # Home Assistant MQTT integration
├── gui.py                  # PyQt5 touchscreen interface
├── config.yaml             # Main configuration file
├── secrets.yaml            # MQTT credentials (not in git)
├── requirements.txt        # Python dependencies
├── install.sh              # Automated installation script
├── discover_sensors.py     # Sensor discovery utility
├── test_relays.py          # Relay testing utility
├── snowmelt.service        # Systemd service (with GUI)
├── snowmelt-headless.service # Systemd service (headless)
├── __init__.py             # Python package marker
├── README.md               # This documentation
└── venv/                   # Python virtual environment (created during install)

/var/log/snowmelt/
└── control.log             # Application log file

/etc/systemd/system/
├── snowmelt.service        # Installed service file
└── snowmelt-headless.service
```

---

## Fresh Raspberry Pi OS Installation

### Step 1: Download and Flash OS

1. Download **Raspberry Pi Imager** from: https://www.raspberrypi.com/software/

2. Insert your microSD card into your computer

3. Open Raspberry Pi Imager and configure:
   - **OS**: Raspberry Pi OS (64-bit) with Desktop
   - **Storage**: Select your microSD card
   - Click the **gear icon** for advanced options:
     - Set hostname: `snowmelt-control`
     - Enable SSH with password authentication
     - Set username: `pi`
     - Set password: `<your-secure-password>`
     - Configure WiFi (if using wireless)
     - Set locale/timezone

4. Click **Write** and wait for completion

### Step 2: First Boot Configuration

1. Insert the microSD card into the Raspberry Pi
2. Connect the Waveshare touchscreen
3. Connect keyboard/mouse (temporarily)
4. Connect to your network (Ethernet recommended)
5. Power on the Raspberry Pi

### Step 3: Initial System Update

Open a terminal (or SSH in) and run:

```bash
# Update package lists
sudo apt update

# Upgrade all packages
sudo apt upgrade -y

# Install essential tools
sudo apt install -y git nano htop

# Reboot to apply any kernel updates
sudo reboot
```

---

## System Configuration

### Step 4: Configure Boot Options

```bash
# Edit the boot configuration
sudo nano /boot/firmware/config.txt
```

Add these lines at the end of the file:

```ini
# 1-Wire temperature sensors on GPIO 23
dtoverlay=w1-gpio,gpiopin=23

# Disable screen blanking (for touchscreen kiosk)
consoleblank=0
```

Save and exit (Ctrl+X, Y, Enter)

### Step 5: Configure Kernel Modules

```bash
# Add 1-Wire modules to load at boot
echo "w1-gpio" | sudo tee -a /etc/modules
echo "w1-therm" | sudo tee -a /etc/modules

# Load modules immediately
sudo modprobe w1-gpio
sudo modprobe w1-therm
```

### Step 6: Configure User Permissions

```bash
# Add pi user to required groups
sudo usermod -a -G gpio,i2c,spi pi
```

### Step 7: Disable Screen Blanking

```bash
# For the desktop environment
sudo nano /etc/xdg/lxsession/LXDE-pi/autostart
```

Add this line:
```
@xset s off
@xset -dpms
@xset s noblank
```

### Step 8: Configure Waveshare Display (if needed)

For the official 7" Waveshare display, you may need:

```bash
sudo nano /boot/firmware/config.txt
```

Add:
```ini
# Waveshare 7" display settings
hdmi_group=2
hdmi_mode=87
hdmi_cvt=800 480 60 6 0 0 0
hdmi_drive=1
```

---

## Software Installation

### Step 9: Copy Project Files

**Option A: Clone from Git repository (if available)**
```bash
git clone https://github.com/JohnTheHobbit/snowmelt-control.git
```

**Option B: Copy files manually**
Copy all the project files to `/home/pi/snowmelt_control/`

### Step 10: Install System Dependencies

```bash
# Install required system packages
# Note: Package names for Raspberry Pi OS Bookworm (Debian 12)
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-pyqt5 \
    python3-dev \
    python3-libgpiod \
    gpiod \
    fonts-dejavu \
    libopenblas-dev \
    libopenjp2-7 \
    libtiff6 \
    i2c-tools
```

> **Note for older Raspberry Pi OS versions (Bullseye/Buster):**
> If you're running an older OS version, use these package names instead:
> - `libgpiod2` instead of `gpiod`
> - `libatlas-base-dev` instead of `libopenblas-dev`
> - `libtiff5` instead of `libtiff6`

### Step 11: Create Python Virtual Environment

```bash
cd /home/pi/snowmelt_control

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip
```

### Step 12: Install Python Dependencies

```bash
# Install from requirements file
pip install paho-mqtt PyYAML

# Install GPIO library - use rpi-lgpio for Pi 5 compatibility
# rpi-lgpio is a drop-in replacement for RPi.GPIO that works on all Pi models
pip install rpi-lgpio

# Link system PyQt5 to virtual environment
SITE_PACKAGES=$(python -c "import site; print(site.getsitepackages()[0])")
ln -sf /usr/lib/python3/dist-packages/PyQt5 "$SITE_PACKAGES/"
ln -sf /usr/lib/python3/dist-packages/sip* "$SITE_PACKAGES/"
```

> **Note:** `rpi-lgpio` provides the same API as `RPi.GPIO` but uses the modern 
> `libgpiod` backend, making it compatible with Raspberry Pi 5 and Bookworm OS.

### Step 13: Create Log Directory

```bash
sudo mkdir -p /var/log/snowmelt
sudo chown pi:pi /var/log/snowmelt
sudo chmod 755 /var/log/snowmelt
```

### Step 14: Make Scripts Executable

```bash
chmod +x main.py
chmod +x discover_sensors.py
chmod +x test_relays.py
chmod +x install.sh
```

---

## Hardware Setup

### Step 15: Wire Temperature Sensors

DS18B20 1-Wire sensors use 3 wires:
- **Red (VCC)**: Connect to 3.3V (Pin 1) or 5V (Pin 2)
- **Black (GND)**: Connect to Ground (Pin 6, 9, 14, 20, 25, 30, 34, or 39)
- **Yellow/White (Data)**: Connect to GPIO 23 (Pin 16)

**Important**: All 5 sensors share the same 3 wires (parallel connection)

Add a 4.7kΩ pull-up resistor between Data and VCC (if not built into sensor cables)

```
Wiring Diagram:
                                    
    3.3V (Pin 1) ─────┬─────────────┬─── Red wire (all sensors)
                      │             │
                    [4.7kΩ]         │
                      │             │
    GPIO 23 (Pin 16) ─┴─────────────┼─── Yellow/Data wire (all sensors)
                                    │
    GND (Pin 6) ────────────────────┴─── Black wire (all sensors)
```

### Step 16: Install Relay HAT

1. Power off the Raspberry Pi
2. Carefully align the Oono 8-relay HAT with the GPIO header
3. Press down firmly to seat the HAT
4. Power on and verify the relay LEDs are off

### Step 17: Wire Equipment to Relays

Connect your equipment through the relay terminals:
- **Relay 1**: Glycol Pump
- **Relay 2**: Primary Pump
- **Relay 3**: Bypass Valve
- **Relay 4**: DHW Recirculation Pump
- **Relays 5-8**: Available for future use

**Warning**: Ensure all high-voltage wiring is done by a qualified electrician!

### Step 18: Verify Sensor Discovery

```bash
cd /home/pi/snowmelt_control
source venv/bin/activate

# Run sensor discovery
python discover_sensors.py
```

Expected output:
```
Found 5 sensor(s):

Address              Temperature     Status
------------------------------------------------------------
28-2605d446635a      95.23 °F        OK
28-0881d44609e5      104.56 °F       OK
28-2401000088aa      138.42 °F       OK
28-240100009c9a      119.87 °F       OK
28-30b6d44610ba      117.34 °F       OK
```

### Step 19: Test Relays

```bash
# Test all relays sequentially
python test_relays.py --test-all

# Or test individually
python test_relays.py --test 1

# Interactive mode
python test_relays.py --interactive
```

---

## Configuration Files

### Step 20: Configure Sensor Addresses

Edit `config.yaml` and verify the sensor addresses match your hardware:

```bash
nano config.yaml
```

Update the sensor section with addresses from the discovery output:

```yaml
sensors:
  glycol_return:
    address: "28-2605d446635a"    # White tape
    name: "Glycol Return"
    label: "White tape"
  glycol_supply:
    address: "28-0881d44609e5"    # Orange tape
    name: "Glycol Supply"
    label: "Orange tape"
  heat_exchanger_in:
    address: "28-2401000088aa"    # Green tape
    name: "Heat Exchanger In"
    label: "Green tape"
  heat_exchanger_out:
    address: "28-240100009c9a"    # Yellow tape
    name: "Heat Exchanger Out"
    label: "Yellow tape"
  dhw_tank:
    address: "28-30b6d44610ba"    # Blue tape
    name: "DHW Tank"
    label: "Blue tape"
```

### Step 21: Configure MQTT Credentials

```bash
nano secrets.yaml
```

Update with your MQTT broker credentials:

```yaml
mqtt:
  broker: "192.168.1.201"
  port: 1883
  username: "your_mqtt_username"
  password: "your_mqtt_password"
  base_topic: "snowmelt"
  discovery_prefix: "homeassistant"
```

**Important**: Set proper permissions on secrets file:
```bash
chmod 600 secrets.yaml
```

### Step 22: Adjust Setpoints (Optional)

Edit `config.yaml` to adjust default setpoints:

```yaml
setpoints:
  glycol:
    high_temp: 110.0      # Target glycol return temperature (°F)
    delta_t: 15.0         # Start heating when temp drops this much
  dhw:
    high_temp: 125.0      # DHW tank high setpoint (°F)
    delta_t: 10.0         # Start recirculation delta
  eco:
    high_temp: 115.0      # Eco mode DHW setpoint (°F)
    delta_t: 15.0         # Eco mode delta

eco_schedule:
  enabled: true
  start_time: "22:00"     # 10:00 PM
  end_time: "06:00"       # 6:00 AM
```

---

## Home Assistant Integration

### Step 23: Configure Home Assistant MQTT

Ensure MQTT is configured in Home Assistant. Add to `configuration.yaml`:

```yaml
mqtt:
  broker: 192.168.1.201
  port: 1883
  username: !secret mqtt_username
  password: !secret mqtt_password
  discovery: true
  discovery_prefix: homeassistant
```

### Step 24: Entities Created

The system automatically creates these Home Assistant entities via MQTT discovery:

**Sensors:**
- `sensor.snowmelt_glycol_return_temperature`
- `sensor.snowmelt_glycol_supply_temperature`
- `sensor.snowmelt_heat_exchanger_in`
- `sensor.snowmelt_heat_exchanger_out`
- `sensor.snowmelt_dhw_tank_temperature`
- `sensor.snowmelt_heat_exchanger_delta_t`
- `sensor.snowmelt_snowmelt_state`
- `sensor.snowmelt_dhw_state`
- `sensor.snowmelt_eco_mode_active`

**Binary Sensors (Equipment State):**
- `binary_sensor.snowmelt_glycol_pump_state`
- `binary_sensor.snowmelt_primary_pump_state`
- `binary_sensor.snowmelt_bypass_valve_state`
- `binary_sensor.snowmelt_dhw_recirculation_pump_state`

**Selects (Equipment Mode):**
- `select.snowmelt_glycol_pump_mode`
- `select.snowmelt_primary_pump_mode`
- `select.snowmelt_bypass_valve_mode`
- `select.snowmelt_dhw_recirculation_pump_mode`

**Switches (System Enable):**
- `switch.snowmelt_snowmelt_system`
- `switch.snowmelt_dhw_system`
- `switch.snowmelt_eco_mode`

**Numbers (Setpoints):**
- `number.snowmelt_glycol_high_setpoint`
- `number.snowmelt_glycol_delta_t`
- `number.snowmelt_dhw_high_setpoint`
- `number.snowmelt_dhw_delta_t`
- `number.snowmelt_eco_high_setpoint`
- `number.snowmelt_eco_delta_t`

---

## Starting the System

### Step 25: Test Manual Startup

```bash
cd /home/pi/snowmelt_control
source venv/bin/activate

# Test with mock sensors (no hardware required)
python main.py --mock-sensors --debug

# Test with real hardware
python main.py --debug

# Test headless mode
python main.py --no-gui --debug
```

### Step 26: Install Systemd Service

```bash
# Copy service files
sudo cp snowmelt.service /etc/systemd/system/
sudo cp snowmelt-headless.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload
```

### Step 27: Enable and Start Service

**For GUI mode (with touchscreen):**
```bash
# Enable service to start on boot
sudo systemctl enable snowmelt.service

# Start the service now
sudo systemctl start snowmelt.service

# Check status
sudo systemctl status snowmelt.service
```

**For headless mode (no display):**
```bash
sudo systemctl enable snowmelt-headless.service
sudo systemctl start snowmelt-headless.service
```

### Step 28: View Logs

```bash
# View service logs
sudo journalctl -u snowmelt.service -f

# View application log
tail -f /var/log/snowmelt/control.log
```

### Step 29: Reboot and Verify

```bash
sudo reboot
```

After reboot:
1. Verify the GUI appears on the touchscreen
2. Check Home Assistant for the new entities
3. Verify temperature readings are updating
4. Test equipment controls from both GUI and Home Assistant

---

## Troubleshooting

### Sensors Not Found

```bash
# Check if 1-Wire is enabled
ls /sys/bus/w1/devices/

# Reload modules
sudo modprobe w1-gpio
sudo modprobe w1-therm

# Check config.txt
cat /boot/firmware/config.txt | grep w1
```

### Relays Not Responding

```bash
# Test GPIO access
python test_relays.py --list-pins
python test_relays.py --test 1

# Check GPIO permissions
groups pi  # Should include 'gpio'
```

### MQTT Connection Failed

```bash
# Test MQTT connectivity
mosquitto_pub -h 192.168.1.201 -u username -P password -t test -m "hello"

# Check secrets file
cat secrets.yaml

# Run with debug logging
python main.py --debug
```

### GUI Not Displaying

```bash
# Check DISPLAY variable
echo $DISPLAY  # Should be :0

# Check X server
xhost +local:

# Run manually with display
DISPLAY=:0 python main.py
```

### Service Won't Start

```bash
# Check service status
sudo systemctl status snowmelt.service

# View detailed logs
sudo journalctl -u snowmelt.service --no-pager -n 100

# Verify paths in service file
cat /etc/systemd/system/snowmelt.service
```

### High CPU Usage

- Check sensor polling interval in `config.yaml` (increase if needed)
- Verify sensors are responding properly
- Check for error loops in logs

---

## Quick Reference Commands

```bash
# Start/Stop/Restart service
sudo systemctl start snowmelt.service
sudo systemctl stop snowmelt.service
sudo systemctl restart snowmelt.service

# View logs
sudo journalctl -u snowmelt.service -f

# Manual run (for testing)
cd /home/pi/snowmelt_control
source venv/bin/activate
python main.py --debug

# Discover sensors
python discover_sensors.py

# Test relays
python test_relays.py --interactive
```

---

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review logs for error messages
3. Verify hardware connections
4. Ensure all configuration files are correct

---

*Last updated: January 2026*
