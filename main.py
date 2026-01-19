#!/usr/bin/env python3
"""
Snowmelt Control System - Main Application Entry Point
Controls snowmelt and DHW systems via Raspberry Pi with touchscreen GUI and MQTT integration
"""

import sys
import os
import signal
import logging
import argparse
import threading
import time
from pathlib import Path

import yaml

# Add project directory to path
PROJECT_DIR = Path(__file__).parent.absolute()
sys.path.insert(0, str(PROJECT_DIR))

from sensors import SensorManager, MockSensorManager
from relays import RelayManager, EquipmentMode
from control import ControlLogic
from mqtt_integration import MQTTIntegration

# Global references for cleanup
app = None
mqtt_client = None
relay_manager = None
sensor_manager = None
control_thread = None
shutdown_event = threading.Event()

logger = logging.getLogger(__name__)


def setup_logging(log_level: str, log_file: str = None):
    """Configure logging"""
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    handlers = [logging.StreamHandler()]
    
    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )


def load_config(config_path: str) -> dict:
    """Load configuration from YAML file"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def load_secrets(secrets_path: str) -> dict:
    """Load secrets from YAML file"""
    if not os.path.exists(secrets_path):
        raise FileNotFoundError(
            f"Secrets file not found: {secrets_path}\n"
            f"Copy secrets.yaml.example to secrets.yaml and configure your MQTT credentials."
        )
    
    with open(secrets_path, 'r') as f:
        return yaml.safe_load(f)


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, initiating shutdown...")
    shutdown_event.set()
    
    if app:
        app.quit()


def control_loop(control: ControlLogic, interval: float):
    """Background control loop"""
    logger.info("Control loop started")
    
    while not shutdown_event.is_set():
        try:
            control.update()
        except Exception as e:
            logger.error(f"Error in control loop: {e}")
        
        shutdown_event.wait(interval)
    
    logger.info("Control loop stopped")


def run_headless(control: ControlLogic, mqtt: MQTTIntegration, interval: float):
    """Run in headless mode without GUI"""
    logger.info("Running in headless mode (no GUI)")
    
    try:
        while not shutdown_event.is_set():
            control.update()
            shutdown_event.wait(interval)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        shutdown_event.set()


def main():
    global app, mqtt_client, relay_manager, sensor_manager, control_thread
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Snowmelt Control System')
    parser.add_argument(
        '--config', '-c',
        default=str(PROJECT_DIR / 'config.yaml'),
        help='Path to configuration file'
    )
    parser.add_argument(
        '--secrets', '-s',
        default=str(PROJECT_DIR / 'secrets.yaml'),
        help='Path to secrets file'
    )
    parser.add_argument(
        '--no-gui',
        action='store_true',
        help='Run without GUI (headless mode)'
    )
    parser.add_argument(
        '--no-mqtt',
        action='store_true',
        help='Run without MQTT integration'
    )
    parser.add_argument(
        '--mock-sensors',
        action='store_true',
        help='Use mock sensors for testing'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    args = parser.parse_args()
    
    # Load configuration
    try:
        config = load_config(args.config)
        secrets = load_secrets(args.secrets) if not args.no_mqtt else {}
    except Exception as e:
        print(f"Error loading configuration: {e}")
        sys.exit(1)
    
    # Setup logging
    log_level = 'DEBUG' if args.debug else config.get('system', {}).get('log_level', 'INFO')
    log_file = config.get('system', {}).get('log_file')
    setup_logging(log_level, log_file)
    
    logger.info("=" * 60)
    logger.info("Snowmelt Control System Starting")
    logger.info("=" * 60)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Initialize sensor manager (starts background read thread for real sensors)
        if args.mock_sensors:
            logger.info("Using mock sensors for testing")
            sensor_manager = MockSensorManager(config['sensors'])
        else:
            sensor_manager = SensorManager(config['sensors'])

        # Initialize relay manager
        relay_manager = RelayManager(config['relays'])
        
        # Initialize control logic
        control = ControlLogic(
            sensor_manager=sensor_manager,
            relay_manager=relay_manager,
            setpoint_config=config['setpoints'],
            eco_config=config['eco_schedule']
        )
        
        # Initialize MQTT integration
        mqtt_client = None
        if not args.no_mqtt:
            try:
                mqtt_client = MQTTIntegration(secrets['mqtt'], control)
                mqtt_client.connect()
                logger.info("MQTT integration enabled")
            except Exception as e:
                logger.error(f"Failed to initialize MQTT: {e}")
                logger.warning("Continuing without MQTT integration")
        
        # Get polling interval
        poll_interval = config.get('system', {}).get('poll_interval', 5)
        
        if args.no_gui:
            # Run headless
            run_headless(control, mqtt_client, poll_interval)
        else:
            # Import GUI module (requires display)
            from gui import create_gui
            
            # Start control loop in background thread
            control_thread = threading.Thread(
                target=control_loop,
                args=(control, poll_interval),
                daemon=True
            )
            control_thread.start()
            
            # Create and run GUI
            app, window = create_gui(control)

            # Pass MQTT integration to GUI for status monitoring
            if mqtt_client:
                window.set_mqtt_integration(mqtt_client)

            logger.info("GUI started")
            exit_code = app.exec_()
            
            # Signal shutdown
            shutdown_event.set()
            
            sys.exit(exit_code)
            
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)
    
    finally:
        # Cleanup
        logger.info("Shutting down...")
        shutdown_event.set()

        if mqtt_client:
            mqtt_client.disconnect()

        if sensor_manager:
            sensor_manager.shutdown()

        if relay_manager:
            relay_manager.shutdown()

        logger.info("Shutdown complete")


if __name__ == '__main__':
    main()
