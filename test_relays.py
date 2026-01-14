#!/usr/bin/env python3
"""
Snowmelt Control System - Relay Test Utility
Tests individual relays on the Oono 8-relay HAT
"""

import sys
import time
import argparse

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("Warning: RPi.GPIO not available - running in simulation mode")


# Relay to GPIO pin mapping (BCM mode)
# Adjust these based on your specific Oono HAT documentation
RELAY_GPIO_MAP = {
    1: 5,   # Relay 1 -> GPIO 5
    2: 6,   # Relay 2 -> GPIO 6
    3: 13,  # Relay 3 -> GPIO 13
    4: 16,  # Relay 4 -> GPIO 16
    5: 19,  # Relay 5 -> GPIO 19
    6: 20,  # Relay 6 -> GPIO 20
    7: 21,  # Relay 7 -> GPIO 21
    8: 26,  # Relay 8 -> GPIO 26
}

# Most relay HATs are active-low (relay ON when GPIO LOW)
ACTIVE_LOW = False

# Relay names for this project
RELAY_NAMES = {
    1: "Glycol Pump",
    2: "Primary Pump",
    3: "Bypass Valve",
    4: "DHW Recirc Pump",
    5: "Unused",
    6: "Unused",
    7: "Unused",
    8: "Unused",
}


def setup_gpio():
    """Initialize GPIO"""
    if GPIO_AVAILABLE:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for relay_num, gpio_pin in RELAY_GPIO_MAP.items():
            GPIO.setup(gpio_pin, GPIO.OUT)
            # Ensure all relays start OFF
            GPIO.output(gpio_pin, GPIO.HIGH if ACTIVE_LOW else GPIO.LOW)


def cleanup_gpio():
    """Cleanup GPIO"""
    if GPIO_AVAILABLE:
        GPIO.cleanup()


def set_relay(relay_num, state):
    """Set relay state"""
    if relay_num not in RELAY_GPIO_MAP:
        print(f"Invalid relay number: {relay_num}")
        return False
    
    gpio_pin = RELAY_GPIO_MAP[relay_num]
    name = RELAY_NAMES.get(relay_num, f"Relay {relay_num}")
    
    if GPIO_AVAILABLE:
        if ACTIVE_LOW:
            GPIO.output(gpio_pin, GPIO.LOW if state else GPIO.HIGH)
        else:
            GPIO.output(gpio_pin, GPIO.HIGH if state else GPIO.LOW)
    
    state_str = "ON" if state else "OFF"
    print(f"Relay {relay_num} ({name}): {state_str}")
    return True


def test_single_relay(relay_num, duration=2.0):
    """Test a single relay"""
    print(f"\nTesting Relay {relay_num} ({RELAY_NAMES.get(relay_num, 'Unknown')})...")
    print(f"  GPIO Pin: {RELAY_GPIO_MAP.get(relay_num, 'Unknown')}")
    
    set_relay(relay_num, True)
    time.sleep(duration)
    set_relay(relay_num, False)
    print(f"  Test complete\n")


def test_all_relays(duration=1.0):
    """Test all relays sequentially"""
    print("\n" + "=" * 50)
    print("  Testing All Relays Sequentially")
    print("=" * 50)
    
    for relay_num in range(1, 9):
        test_single_relay(relay_num, duration)
        time.sleep(0.5)
    
    print("All relay tests complete!")


def interactive_mode():
    """Interactive relay control"""
    print("\n" + "=" * 50)
    print("  Interactive Relay Control")
    print("=" * 50)
    print("\nCommands:")
    print("  1-8 on    - Turn relay on")
    print("  1-8 off   - Turn relay off")
    print("  all on    - Turn all relays on")
    print("  all off   - Turn all relays off")
    print("  test      - Test all relays")
    print("  status    - Show relay status")
    print("  quit      - Exit")
    print()
    
    relay_states = {i: False for i in range(1, 9)}
    
    while True:
        try:
            cmd = input("relay> ").strip().lower()
            
            if not cmd:
                continue
            
            if cmd == 'quit' or cmd == 'q' or cmd == 'exit':
                break
            
            if cmd == 'test':
                test_all_relays(1.0)
                continue
            
            if cmd == 'status':
                print("\nRelay Status:")
                for i in range(1, 9):
                    state = "ON" if relay_states[i] else "OFF"
                    name = RELAY_NAMES.get(i, f"Relay {i}")
                    print(f"  {i}: {name:<20} [{state}]")
                print()
                continue
            
            parts = cmd.split()
            if len(parts) != 2:
                print("Invalid command. Use: <relay#> <on|off> or 'help'")
                continue
            
            relay_str, action = parts
            
            if action not in ('on', 'off'):
                print("Action must be 'on' or 'off'")
                continue
            
            state = action == 'on'
            
            if relay_str == 'all':
                for i in range(1, 9):
                    set_relay(i, state)
                    relay_states[i] = state
            else:
                try:
                    relay_num = int(relay_str)
                    if 1 <= relay_num <= 8:
                        set_relay(relay_num, state)
                        relay_states[relay_num] = state
                    else:
                        print("Relay number must be 1-8")
                except ValueError:
                    print("Invalid relay number")
                    
        except KeyboardInterrupt:
            print("\n")
            break
        except EOFError:
            break


def main():
    parser = argparse.ArgumentParser(description='Relay Test Utility')
    parser.add_argument(
        '--test',
        type=int,
        choices=range(1, 9),
        metavar='N',
        help='Test specific relay (1-8)'
    )
    parser.add_argument(
        '--test-all',
        action='store_true',
        help='Test all relays sequentially'
    )
    parser.add_argument(
        '--interactive', '-i',
        action='store_true',
        help='Interactive mode'
    )
    parser.add_argument(
        '--duration', '-d',
        type=float,
        default=2.0,
        help='Test duration in seconds (default: 2.0)'
    )
    parser.add_argument(
        '--list-pins',
        action='store_true',
        help='List relay to GPIO pin mapping'
    )
    
    args = parser.parse_args()
    
    if args.list_pins:
        print("\nRelay to GPIO Pin Mapping:")
        print("-" * 50)
        for relay_num, gpio_pin in sorted(RELAY_GPIO_MAP.items()):
            name = RELAY_NAMES.get(relay_num, "Unused")
            print(f"  Relay {relay_num}: GPIO {gpio_pin:<3} - {name}")
        print("-" * 50)
        print(f"Active Low: {ACTIVE_LOW}")
        print()
        return
    
    print("=" * 50)
    print("  Snowmelt Control - Relay Test Utility")
    print("=" * 50)
    
    if not GPIO_AVAILABLE:
        print("\nWARNING: Running in simulation mode (no GPIO)")
    
    setup_gpio()
    
    try:
        if args.test:
            test_single_relay(args.test, args.duration)
        elif args.test_all:
            test_all_relays(args.duration)
        elif args.interactive:
            interactive_mode()
        else:
            # Default: show help
            parser.print_help()
            print("\nExamples:")
            print("  ./test_relays.py --test 1          # Test relay 1")
            print("  ./test_relays.py --test-all        # Test all relays")
            print("  ./test_relays.py --interactive     # Interactive mode")
            print("  ./test_relays.py --list-pins       # Show pin mapping")
    
    finally:
        # Turn off all relays before exit
        print("\nTurning off all relays...")
        for relay_num in range(1, 9):
            set_relay(relay_num, False)
        cleanup_gpio()
        print("Done.")


if __name__ == '__main__':
    main()
