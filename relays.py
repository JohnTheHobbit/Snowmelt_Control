"""
Snowmelt Control System - Relay Control Module
Handles Oono 8-relay HAT control on Raspberry Pi
"""

import logging
from enum import Enum
from typing import Dict, Optional, Callable
from dataclasses import dataclass
from threading import Lock
import time

logger = logging.getLogger(__name__)

# Try to import RPi.GPIO, fall back to mock for development
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    logger.warning("RPi.GPIO not available - using mock GPIO")


class EquipmentMode(Enum):
    """Operating modes for equipment"""
    AUTO = "auto"
    ON = "on"
    OFF = "off"


@dataclass
class RelayState:
    """Current state of a relay"""
    relay_num: int
    name: str
    mode: EquipmentMode
    is_energized: bool  # Physical relay state
    auto_state: bool    # What auto mode wants
    description: str


class RelayController:
    """Controls a single relay on the HAT"""
    
    # Oono relay HAT GPIO pin mapping (BCM mode)
    # Typically relays 1-8 map to specific GPIO pins
    # Adjust these based on your specific HAT documentation
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
    
    # Some relay HATs are active-low (relay on when GPIO low)
    ACTIVE_LOW = False
    
    def __init__(self, relay_num: int, name: str, description: str = ""):
        self.relay_num = relay_num
        self.name = name
        self.description = description
        self.gpio_pin = self.RELAY_GPIO_MAP.get(relay_num)
        
        self._mode = EquipmentMode.AUTO
        self._auto_state = False
        self._is_energized = False
        self._lock = Lock()
        self._on_change_callback: Optional[Callable] = None
        
        if self.gpio_pin is None:
            raise ValueError(f"Invalid relay number: {relay_num}")
        
        # Initialize GPIO if available
        if GPIO_AVAILABLE:
            GPIO.setup(self.gpio_pin, GPIO.OUT)
            self._set_physical_state(False)
        
        logger.info(f"Initialized relay {relay_num} ({name}) on GPIO {self.gpio_pin}")
    
    def _set_physical_state(self, energize: bool):
        """Set the physical relay state"""
        if GPIO_AVAILABLE:
            # Handle active-low logic
            if self.ACTIVE_LOW:
                GPIO.output(self.gpio_pin, GPIO.LOW if energize else GPIO.HIGH)
            else:
                GPIO.output(self.gpio_pin, GPIO.HIGH if energize else GPIO.LOW)
        
        self._is_energized = energize
        logger.debug(f"Relay {self.name}: {'ON' if energize else 'OFF'}")
    
    def set_mode(self, mode: EquipmentMode):
        """Set the operating mode"""
        with self._lock:
            old_mode = self._mode
            self._mode = mode
            self._update_state()
            
            if old_mode != mode:
                logger.info(f"{self.name} mode changed: {old_mode.value} -> {mode.value}")
                if self._on_change_callback:
                    self._on_change_callback(self)
    
    def set_auto_state(self, state: bool):
        """Set what the auto mode wants the relay to be"""
        with self._lock:
            old_auto = self._auto_state
            self._auto_state = state
            self._update_state()
            
            if old_auto != state and self._mode == EquipmentMode.AUTO:
                logger.info(f"{self.name} auto state: {'ON' if state else 'OFF'}")
    
    def _update_state(self):
        """Update physical relay based on mode and auto state"""
        if self._mode == EquipmentMode.ON:
            new_state = True
        elif self._mode == EquipmentMode.OFF:
            new_state = False
        else:  # AUTO
            new_state = self._auto_state
        
        if new_state != self._is_energized:
            self._set_physical_state(new_state)
            if self._on_change_callback:
                self._on_change_callback(self)
    
    def set_on_change_callback(self, callback: Callable):
        """Set callback for state changes"""
        self._on_change_callback = callback
    
    @property
    def mode(self) -> EquipmentMode:
        return self._mode
    
    @property
    def is_energized(self) -> bool:
        return self._is_energized
    
    @property
    def auto_state(self) -> bool:
        return self._auto_state
    
    def get_state(self) -> RelayState:
        """Get current relay state"""
        with self._lock:
            return RelayState(
                relay_num=self.relay_num,
                name=self.name,
                mode=self._mode,
                is_energized=self._is_energized,
                auto_state=self._auto_state,
                description=self.description
            )


class RelayManager:
    """Manages all relays in the system"""
    
    def __init__(self, relay_config: Dict):
        self.relays: Dict[str, RelayController] = {}
        self._lock = Lock()
        
        # Initialize GPIO
        if GPIO_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
        
        # Initialize relays from config
        for relay_id, config in relay_config.items():
            self.relays[relay_id] = RelayController(
                relay_num=config['relay'],
                name=config['name'],
                description=config.get('description', '')
            )
    
    def get_relay(self, relay_id: str) -> Optional[RelayController]:
        """Get a relay by ID"""
        return self.relays.get(relay_id)
    
    def set_mode(self, relay_id: str, mode: EquipmentMode):
        """Set mode for a specific relay"""
        relay = self.relays.get(relay_id)
        if relay:
            relay.set_mode(mode)
    
    def set_auto_state(self, relay_id: str, state: bool):
        """Set auto state for a specific relay"""
        relay = self.relays.get(relay_id)
        if relay:
            relay.set_auto_state(state)
    
    def get_all_states(self) -> Dict[str, RelayState]:
        """Get states of all relays"""
        states = {}
        for relay_id, relay in self.relays.items():
            states[relay_id] = relay.get_state()
        return states
    
    def set_on_change_callback(self, callback: Callable):
        """Set callback for all relay changes"""
        for relay in self.relays.values():
            relay.set_on_change_callback(callback)
    
    def shutdown(self):
        """Safely shutdown all relays"""
        logger.info("Shutting down relay manager...")
        for relay_id, relay in self.relays.items():
            relay.set_mode(EquipmentMode.OFF)
            relay.set_auto_state(False)
        
        if GPIO_AVAILABLE:
            time.sleep(0.1)  # Brief delay for relays to switch
            GPIO.cleanup()
        
        logger.info("Relay manager shutdown complete")


# Mock GPIO for development
if not GPIO_AVAILABLE:
    class MockGPIO:
        BCM = 11
        OUT = 1
        HIGH = 1
        LOW = 0
        
        @staticmethod
        def setmode(mode): pass
        
        @staticmethod
        def setwarnings(warnings): pass
        
        @staticmethod
        def setup(pin, mode): pass
        
        @staticmethod
        def output(pin, state): pass
        
        @staticmethod
        def cleanup(): pass
    
    GPIO = MockGPIO
    GPIO_AVAILABLE = True  # Enable with mock
