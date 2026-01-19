"""
Snowmelt Control System - Temperature Sensor Module
Handles 1-Wire temperature sensor communication on Raspberry Pi
"""

import os
import glob
import logging
from typing import Dict, Optional
from dataclasses import dataclass
from threading import Lock, Thread, Event
from copy import deepcopy

logger = logging.getLogger(__name__)

# 1-Wire base path on Raspberry Pi
ONEWIRE_BASE_PATH = "/sys/bus/w1/devices"


@dataclass
class SensorReading:
    """Represents a temperature reading from a sensor"""
    address: str
    name: str
    temperature_c: Optional[float]
    temperature_f: Optional[float]
    valid: bool
    error: Optional[str] = None


class TemperatureSensor:
    """Manages a single DS18B20 temperature sensor"""
    
    def __init__(self, address: str, name: str, label: str = ""):
        self.address = address
        self.name = name
        self.label = label
        self.device_path = os.path.join(ONEWIRE_BASE_PATH, address, "w1_slave")
        self._last_reading: Optional[SensorReading] = None
        self._lock = Lock()
    
    def read_temperature(self) -> SensorReading:
        """Read temperature from the sensor"""
        with self._lock:
            try:
                if not os.path.exists(self.device_path):
                    return SensorReading(
                        address=self.address,
                        name=self.name,
                        temperature_c=None,
                        temperature_f=None,
                        valid=False,
                        error=f"Sensor not found at {self.device_path}"
                    )
                
                with open(self.device_path, 'r') as f:
                    lines = f.readlines()
                
                # Check for valid CRC
                if len(lines) < 2 or "YES" not in lines[0]:
                    return SensorReading(
                        address=self.address,
                        name=self.name,
                        temperature_c=None,
                        temperature_f=None,
                        valid=False,
                        error="CRC check failed"
                    )
                
                # Extract temperature
                equals_pos = lines[1].find('t=')
                if equals_pos == -1:
                    return SensorReading(
                        address=self.address,
                        name=self.name,
                        temperature_c=None,
                        temperature_f=None,
                        valid=False,
                        error="Temperature value not found"
                    )
                
                temp_string = lines[1][equals_pos + 2:]
                temp_c = float(temp_string) / 1000.0
                temp_f = (temp_c * 9.0 / 5.0) + 32.0
                
                self._last_reading = SensorReading(
                    address=self.address,
                    name=self.name,
                    temperature_c=round(temp_c, 2),
                    temperature_f=round(temp_f, 2),
                    valid=True
                )
                return self._last_reading
                
            except Exception as e:
                logger.error(f"Error reading sensor {self.name} ({self.address}): {e}")
                return SensorReading(
                    address=self.address,
                    name=self.name,
                    temperature_c=None,
                    temperature_f=None,
                    valid=False,
                    error=str(e)
                )
    
    @property
    def last_reading(self) -> Optional[SensorReading]:
        """Get the last successful reading"""
        return self._last_reading


class SensorManager:
    """Manages all temperature sensors in the system with async reads"""

    def __init__(self, sensor_config: Dict):
        self.sensors: Dict[str, TemperatureSensor] = {}
        self._readings: Dict[str, SensorReading] = {}
        self._cached_readings: Dict[str, SensorReading] = {}
        self._lock = Lock()
        self._stop_event = Event()
        self._read_thread: Optional[Thread] = None

        # Initialize sensors from config
        for sensor_id, config in sensor_config.items():
            self.sensors[sensor_id] = TemperatureSensor(
                address=config['address'],
                name=config['name'],
                label=config.get('label', '')
            )
            logger.info(f"Initialized sensor: {config['name']} ({config['address']})")

        # Start background reading thread
        self._start_read_thread()

    def _start_read_thread(self):
        """Start background sensor reading thread"""
        self._stop_event.clear()
        self._read_thread = Thread(target=self._read_loop, daemon=True)
        self._read_thread.start()
        logger.info("Sensor read thread started")

    def _read_loop(self):
        """Background loop that continuously reads sensors"""
        while not self._stop_event.is_set():
            try:
                # Read all sensors (this is the slow operation)
                new_readings = {}
                for sensor_id, sensor in self.sensors.items():
                    reading = sensor.read_temperature()
                    new_readings[sensor_id] = reading
                    if reading.valid:
                        logger.debug(f"{sensor.name}: {reading.temperature_f}°F")
                    else:
                        logger.warning(f"{sensor.name}: {reading.error}")

                # Quick lock to update cached readings
                with self._lock:
                    self._readings = new_readings
                    self._cached_readings = deepcopy(new_readings)

            except Exception as e:
                logger.error(f"Error in sensor read loop: {e}")

            # Wait before next read cycle (sensors update slowly anyway)
            self._stop_event.wait(2.0)

    def read_all(self) -> Dict[str, SensorReading]:
        """Return cached readings (non-blocking)"""
        with self._lock:
            return deepcopy(self._cached_readings)

    def get_reading(self, sensor_id: str) -> Optional[SensorReading]:
        """Get the last reading for a specific sensor (non-blocking)"""
        with self._lock:
            return self._cached_readings.get(sensor_id)

    def get_temperature_f(self, sensor_id: str) -> Optional[float]:
        """Get temperature in Fahrenheit for a specific sensor"""
        reading = self.get_reading(sensor_id)
        if reading and reading.valid:
            return reading.temperature_f
        return None

    def get_all_readings(self) -> Dict[str, SensorReading]:
        """Get all current readings (non-blocking)"""
        with self._lock:
            return deepcopy(self._cached_readings)

    def shutdown(self):
        """Stop the background read thread"""
        self._stop_event.set()
        if self._read_thread and self._read_thread.is_alive():
            self._read_thread.join(timeout=3.0)
        logger.info("Sensor manager shutdown")

    @staticmethod
    def discover_sensors() -> list:
        """Discover all connected 1-Wire sensors"""
        try:
            devices = glob.glob(os.path.join(ONEWIRE_BASE_PATH, "28-*"))
            addresses = [os.path.basename(d) for d in devices]
            logger.info(f"Discovered {len(addresses)} temperature sensors")
            return addresses
        except Exception as e:
            logger.error(f"Error discovering sensors: {e}")
            return []


# Development/Testing mock for systems without actual sensors
class MockSensorManager:
    """Mock sensor manager for development and testing"""

    def __init__(self, sensor_config: Dict):
        self.sensors: Dict[str, TemperatureSensor] = {}
        self._readings: Dict[str, SensorReading] = {}
        self._lock = Lock()
        self._mock_temps: Dict[str, float] = {}

        # Initialize with mock temperatures
        default_temps = {
            'glycol_return': 95.0,
            'glycol_supply': 105.0,
            'heat_exchanger_in': 140.0,
            'heat_exchanger_out': 120.0,
            'dhw_tank': 118.0
        }

        for sensor_id, config in sensor_config.items():
            self.sensors[sensor_id] = TemperatureSensor(
                address=config['address'],
                name=config['name'],
                label=config.get('label', '')
            )
            self._mock_temps[sensor_id] = default_temps.get(sensor_id, 70.0)
            logger.info(f"Initialized MOCK sensor: {config['name']}")

    def set_mock_temperature(self, sensor_id: str, temp_f: float):
        """Set mock temperature for testing"""
        with self._lock:
            self._mock_temps[sensor_id] = temp_f

    def read_all(self) -> Dict[str, SensorReading]:
        """Return mock readings"""
        with self._lock:
            for sensor_id, sensor in self.sensors.items():
                temp_f = self._mock_temps.get(sensor_id, 70.0)
                temp_c = (temp_f - 32.0) * 5.0 / 9.0
                self._readings[sensor_id] = SensorReading(
                    address=sensor.address,
                    name=sensor.name,
                    temperature_c=round(temp_c, 2),
                    temperature_f=round(temp_f, 2),
                    valid=True
                )
            return deepcopy(self._readings)

    def get_reading(self, sensor_id: str) -> Optional[SensorReading]:
        """Get the last reading for a specific sensor"""
        with self._lock:
            return self._readings.get(sensor_id)

    def get_temperature_f(self, sensor_id: str) -> Optional[float]:
        """Get temperature in Fahrenheit for a specific sensor"""
        reading = self.get_reading(sensor_id)
        if reading and reading.valid:
            return reading.temperature_f
        return None

    def get_all_readings(self) -> Dict[str, SensorReading]:
        """Get all current readings"""
        with self._lock:
            return deepcopy(self._readings)

    def shutdown(self):
        """No-op for mock manager"""
        pass
