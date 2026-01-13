#!/usr/bin/env python3
"""
Snowmelt Control System - Sensor Discovery Utility
Discovers and displays all connected 1-Wire temperature sensors
"""

import os
import glob
import sys
import time


ONEWIRE_BASE_PATH = "/sys/bus/w1/devices"


def read_temp(device_path):
    """Read temperature from a DS18B20 sensor"""
    try:
        with open(os.path.join(device_path, 'w1_slave'), 'r') as f:
            lines = f.readlines()
        
        if len(lines) < 2 or 'YES' not in lines[0]:
            return None, "CRC failed"
        
        equals_pos = lines[1].find('t=')
        if equals_pos == -1:
            return None, "No temp found"
        
        temp_c = float(lines[1][equals_pos + 2:]) / 1000.0
        temp_f = (temp_c * 9.0 / 5.0) + 32.0
        return temp_f, None
    except Exception as e:
        return None, str(e)


def discover_sensors():
    """Find all 1-Wire temperature sensors"""
    devices = glob.glob(os.path.join(ONEWIRE_BASE_PATH, "28-*"))
    sensors = []
    
    for device in devices:
        address = os.path.basename(device)
        temp, error = read_temp(device)
        sensors.append({
            'address': address,
            'path': device,
            'temperature_f': temp,
            'error': error
        })
    
    return sensors


def main():
    print("=" * 60)
    print("  1-Wire Temperature Sensor Discovery")
    print("=" * 60)
    print()
    
    # Check if 1-Wire is available
    if not os.path.exists(ONEWIRE_BASE_PATH):
        print("ERROR: 1-Wire bus not found at", ONEWIRE_BASE_PATH)
        print()
        print("Make sure 1-Wire is enabled:")
        print("  1. Add to /boot/config.txt:")
        print("     dtoverlay=w1-gpio,gpiopin=23")
        print("  2. Load kernel modules:")
        print("     sudo modprobe w1-gpio")
        print("     sudo modprobe w1-therm")
        print("  3. Reboot the system")
        sys.exit(1)
    
    print(f"1-Wire bus found at: {ONEWIRE_BASE_PATH}")
    print()
    
    # Discover sensors
    sensors = discover_sensors()
    
    if not sensors:
        print("No temperature sensors found!")
        print()
        print("Check your wiring:")
        print("  - Data wire (usually yellow/white) to GPIO 23")
        print("  - 4.7kΩ pull-up resistor between data and 3.3V")
        print("  - GND wire to ground")
        print("  - VCC wire to 3.3V (parasitic mode) or 5V")
        sys.exit(1)
    
    print(f"Found {len(sensors)} sensor(s):")
    print()
    print("-" * 60)
    print(f"{'Address':<20} {'Temperature':<15} {'Status'}")
    print("-" * 60)
    
    for sensor in sensors:
        if sensor['temperature_f'] is not None:
            temp_str = f"{sensor['temperature_f']:.2f} °F"
            status = "OK"
        else:
            temp_str = "---"
            status = f"Error: {sensor['error']}"
        
        print(f"{sensor['address']:<20} {temp_str:<15} {status}")
    
    print("-" * 60)
    print()
    
    # Print configuration snippet
    print("Configuration snippet for config.yaml:")
    print()
    print("sensors:")
    
    labels = [
        ("glycol_return", "White tape - Glycol Return"),
        ("glycol_supply", "Orange tape - Glycol Supply"),
        ("heat_exchanger_in", "Green tape - Heat Exchanger In"),
        ("heat_exchanger_out", "Yellow tape - Heat Exchanger Out"),
        ("dhw_tank", "Blue tape - DHW Tank")
    ]
    
    for i, sensor in enumerate(sensors):
        if i < len(labels):
            sensor_id, label = labels[i]
        else:
            sensor_id = f"sensor_{i+1}"
            label = f"Sensor {i+1}"
        
        print(f"  {sensor_id}:")
        print(f'    address: "{sensor[\'address\']}"')
        print(f'    name: "{label.split(" - ")[-1] if " - " in label else label}"')
        print(f'    label: "{label.split(" - ")[0] if " - " in label else ""}"')
    
    print()
    print("NOTE: Update the sensor IDs and labels above to match your")
    print("      actual sensor placement (identified by tape color).")
    

if __name__ == '__main__':
    main()
