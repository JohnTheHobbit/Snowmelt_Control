"""
Snowmelt Control System - Control Logic Module
Implements the control algorithms for snowmelt and DHW systems
"""

import logging
from datetime import datetime, time as dtime, timedelta
from typing import Dict, Optional, Callable
from dataclasses import dataclass, field
from threading import Lock, RLock
from enum import Enum
from copy import deepcopy

from sensors import SensorManager, SensorReading
from relays import RelayManager, EquipmentMode
from setpoint_persistence import SetpointPersistence, PersistedSetpoints

logger = logging.getLogger(__name__)


class SystemState(Enum):
    """Overall system states"""
    IDLE = "idle"
    HEATING = "heating"
    BYPASS = "bypass"
    ERROR = "error"


@dataclass
class Setpoints:
    """Temperature setpoints"""
    high_temp: float
    delta_t: float
    
    @property
    def low_temp(self) -> float:
        """Calculate low setpoint from high and delta"""
        return self.high_temp - self.delta_t


@dataclass
class ControlState:
    """Current state of the control system"""
    # Snowmelt system
    snowmelt_enabled: bool = False
    snowmelt_state: SystemState = SystemState.IDLE
    glycol_setpoints: Setpoints = field(default_factory=lambda: Setpoints(110.0, 15.0))
    
    # DHW system
    dhw_enabled: bool = True
    dhw_state: SystemState = SystemState.IDLE
    dhw_setpoints: Setpoints = field(default_factory=lambda: Setpoints(125.0, 10.0))
    
    # Eco mode
    eco_enabled: bool = True
    eco_active: bool = False
    eco_setpoints: Setpoints = field(default_factory=lambda: Setpoints(115.0, 15.0))
    eco_start: str = "22:00"
    eco_end: str = "06:00"

    # Shutdown delay timer
    shutdown_timer_enabled: bool = False
    shutdown_timer_end_time: Optional[datetime] = None
    shutdown_timer_duration_minutes: int = 0

    # Temperatures
    glycol_return_temp: Optional[float] = None
    glycol_supply_temp: Optional[float] = None
    hx_in_temp: Optional[float] = None
    hx_out_temp: Optional[float] = None
    dhw_tank_temp: Optional[float] = None
    
    # Calculated values
    hx_delta_t: Optional[float] = None  # Heat exchanger effectiveness


class ControlLogic:
    """Main control logic for the snowmelt and DHW systems"""

    def __init__(self, sensor_manager: SensorManager, relay_manager: RelayManager,
                 setpoint_config: Dict, eco_config: Dict,
                 persistence: SetpointPersistence = None):
        self.sensors = sensor_manager
        self.relays = relay_manager
        self.state = ControlState()
        # Separate lock for state modifications vs reads
        self._state_lock = Lock()
        # Cached copy of state for fast GUI reads (no lock needed for reads)
        self._cached_state: Optional[ControlState] = None
        self._on_state_change: Optional[Callable] = None
        # Setpoint persistence
        self._persistence = persistence

        # Load initial setpoints from config (and persistence if available)
        self._load_setpoints(setpoint_config, eco_config)
        self._update_cached_state()

        logger.info("Control logic initialized")

    def _update_cached_state(self):
        """Update the cached state copy for GUI reads"""
        self._cached_state = deepcopy(self.state)
    
    def _load_setpoints(self, setpoint_config: Dict, eco_config: Dict):
        """Load setpoints from persistence (if available) or config defaults"""
        if self._persistence:
            # Merge config into format expected by persistence loader
            merged_defaults = {
                'glycol': setpoint_config.get('glycol', {}),
                'dhw': setpoint_config.get('dhw', {}),
                'eco': setpoint_config.get('eco', {}),
                'eco_schedule': eco_config
            }
            persisted = self._persistence.load(merged_defaults)

            self.state.glycol_setpoints = Setpoints(
                persisted.glycol_high_temp, persisted.glycol_delta_t
            )
            self.state.dhw_setpoints = Setpoints(
                persisted.dhw_high_temp, persisted.dhw_delta_t
            )
            self.state.eco_setpoints = Setpoints(
                persisted.eco_high_temp, persisted.eco_delta_t
            )
            self.state.eco_start = persisted.eco_start
            self.state.eco_end = persisted.eco_end
            self.state.eco_enabled = eco_config.get('enabled', True)
        else:
            # Fallback: load directly from config
            glycol = setpoint_config.get('glycol', {})
            dhw = setpoint_config.get('dhw', {})
            eco = setpoint_config.get('eco', {})

            self.state.glycol_setpoints = Setpoints(
                high_temp=glycol.get('high_temp', 110.0),
                delta_t=glycol.get('delta_t', 15.0)
            )
            self.state.dhw_setpoints = Setpoints(
                high_temp=dhw.get('high_temp', 125.0),
                delta_t=dhw.get('delta_t', 10.0)
            )
            self.state.eco_setpoints = Setpoints(
                high_temp=eco.get('high_temp', 115.0),
                delta_t=eco.get('delta_t', 15.0)
            )
            self.state.eco_enabled = eco_config.get('enabled', True)
            self.state.eco_start = eco_config.get('start_time', '22:00')
            self.state.eco_end = eco_config.get('end_time', '06:00')

    def _save_setpoints(self):
        """Save current setpoints to persistence (debounced)"""
        if self._persistence:
            setpoints = PersistedSetpoints(
                glycol_high_temp=self.state.glycol_setpoints.high_temp,
                glycol_delta_t=self.state.glycol_setpoints.delta_t,
                dhw_high_temp=self.state.dhw_setpoints.high_temp,
                dhw_delta_t=self.state.dhw_setpoints.delta_t,
                eco_high_temp=self.state.eco_setpoints.high_temp,
                eco_delta_t=self.state.eco_setpoints.delta_t,
                eco_start=self.state.eco_start,
                eco_end=self.state.eco_end
            )
            self._persistence.save(setpoints)

    def set_on_state_change(self, callback: Callable):
        """Set callback for state changes"""
        self._on_state_change = callback
    
    def _notify_state_change(self):
        """Notify listeners of state change - call with lock held"""
        self._update_cached_state()
        if self._on_state_change:
            # Pass cached copy to avoid threading issues
            self._on_state_change(self._cached_state)

    def _is_eco_time(self) -> bool:
        """Check if current time is within eco schedule"""
        if not self.state.eco_enabled:
            return False
        
        try:
            now = datetime.now().time()
            start = datetime.strptime(self.state.eco_start, "%H:%M").time()
            end = datetime.strptime(self.state.eco_end, "%H:%M").time()
            
            # Handle overnight schedule (e.g., 22:00 to 06:00)
            if start > end:
                return now >= start or now < end
            else:
                return start <= now < end
        except Exception as e:
            logger.error(f"Error checking eco time: {e}")
            return False

    def _check_shutdown_timer(self):
        """Check if shutdown timer has expired and disable snowmelt if so"""
        if not self.state.shutdown_timer_enabled:
            return
        if self.state.shutdown_timer_end_time is None:
            return

        if datetime.now() >= self.state.shutdown_timer_end_time:
            logger.info("Shutdown timer expired - disabling snowmelt system")
            self.state.snowmelt_enabled = False
            self.state.shutdown_timer_enabled = False
            self.state.shutdown_timer_end_time = None
            self.state.shutdown_timer_duration_minutes = 0

    def update(self):
        """Main control loop update - call periodically"""
        # Read sensors outside lock (non-blocking now)
        readings = self.sensors.read_all()

        with self._state_lock:
            # Update temperatures in state
            self._update_temperatures(readings)

            # Check eco mode
            self.state.eco_active = self._is_eco_time()

            # Check shutdown timer
            self._check_shutdown_timer()

            # Run control logic
            self._control_snowmelt()
            self._control_dhw()

            # Notify listeners
            self._notify_state_change()
    
    def _update_temperatures(self, readings: Dict[str, SensorReading]):
        """Update state with current temperatures"""
        def get_temp(sensor_id: str) -> Optional[float]:
            reading = readings.get(sensor_id)
            if reading and reading.valid:
                return reading.temperature_f
            return None
        
        self.state.glycol_return_temp = get_temp('glycol_return')
        self.state.glycol_supply_temp = get_temp('glycol_supply')
        self.state.hx_in_temp = get_temp('heat_exchanger_in')
        self.state.hx_out_temp = get_temp('heat_exchanger_out')
        self.state.dhw_tank_temp = get_temp('dhw_tank')
        
        # Calculate heat exchanger delta T
        if self.state.hx_in_temp and self.state.hx_out_temp:
            self.state.hx_delta_t = round(
                self.state.hx_in_temp - self.state.hx_out_temp, 2
            )
        else:
            self.state.hx_delta_t = None
    
    def _control_snowmelt(self):
        """Control logic for snowmelt system"""
        glycol_pump = self.relays.get_relay('glycol_pump')
        primary_pump = self.relays.get_relay('primary_pump')
        bypass_valve = self.relays.get_relay('bypass_valve')
        
        if not all([glycol_pump, primary_pump, bypass_valve]):
            logger.error("Missing relay for snowmelt control")
            return
        
        # If snowmelt not enabled, ensure equipment is off (in auto mode)
        if not self.state.snowmelt_enabled:
            self.state.snowmelt_state = SystemState.IDLE
            glycol_pump.set_auto_state(False)
            primary_pump.set_auto_state(False)
            bypass_valve.set_auto_state(False)
            return
        
        # Snowmelt enabled - glycol pump must always run
        glycol_pump.set_auto_state(True)
        
        # Check glycol return temperature
        return_temp = self.state.glycol_return_temp
        if return_temp is None:
            # Sensor error - go to safe state (bypass, no heating)
            self.state.snowmelt_state = SystemState.ERROR
            bypass_valve.set_auto_state(False)
            primary_pump.set_auto_state(False)
            logger.warning("Glycol return sensor error - safe mode")
            return
        
        setpoints = self.state.glycol_setpoints
        
        # Determine heating state based on temperature
        if return_temp >= setpoints.high_temp:
            # Temperature reached - bypass heat exchanger
            self.state.snowmelt_state = SystemState.BYPASS
            bypass_valve.set_auto_state(False)  # Close valve = bypass
            primary_pump.set_auto_state(False)
            logger.debug(f"Glycol at {return_temp}°F >= {setpoints.high_temp}°F - bypass mode")
            
        elif return_temp <= setpoints.low_temp:
            # Temperature low - enable heating
            self.state.snowmelt_state = SystemState.HEATING
            bypass_valve.set_auto_state(True)   # Open valve = through HX
            primary_pump.set_auto_state(True)
            logger.debug(f"Glycol at {return_temp}°F <= {setpoints.low_temp}°F - heating mode")
            
        else:
            # In deadband - maintain current state
            pass
    
    def _control_dhw(self):
        """Control logic for domestic hot water system"""
        dhw_pump = self.relays.get_relay('dhw_pump')
        
        if not dhw_pump:
            logger.error("Missing relay for DHW control")
            return
        
        # If DHW not enabled, ensure pump is off (in auto mode)
        if not self.state.dhw_enabled:
            self.state.dhw_state = SystemState.IDLE
            dhw_pump.set_auto_state(False)
            return
        
        # Check DHW tank temperature
        tank_temp = self.state.dhw_tank_temp
        if tank_temp is None:
            # Sensor error - safe state (pump off)
            self.state.dhw_state = SystemState.ERROR
            dhw_pump.set_auto_state(False)
            logger.warning("DHW tank sensor error - safe mode")
            return
        
        # Use eco setpoints if eco mode active
        if self.state.eco_active:
            setpoints = self.state.eco_setpoints
        else:
            setpoints = self.state.dhw_setpoints
        
        # Determine heating state
        if tank_temp >= setpoints.high_temp:
            # Temperature reached - stop recirculation
            self.state.dhw_state = SystemState.IDLE
            dhw_pump.set_auto_state(False)
            logger.debug(f"DHW at {tank_temp}°F >= {setpoints.high_temp}°F - idle")
            
        elif tank_temp <= setpoints.low_temp:
            # Temperature low - start recirculation
            self.state.dhw_state = SystemState.HEATING
            dhw_pump.set_auto_state(True)
            logger.debug(f"DHW at {tank_temp}°F <= {setpoints.low_temp}°F - heating")
            
        else:
            # In deadband - maintain current state
            pass
    
    # --- Public API for setpoint updates ---

    def set_snowmelt_enabled(self, enabled: bool):
        """Enable/disable snowmelt system"""
        with self._state_lock:
            self.state.snowmelt_enabled = enabled
            logger.info(f"Snowmelt system {'enabled' if enabled else 'disabled'}")
            self._notify_state_change()

    def set_dhw_enabled(self, enabled: bool):
        """Enable/disable DHW system"""
        with self._state_lock:
            self.state.dhw_enabled = enabled
            logger.info(f"DHW system {'enabled' if enabled else 'disabled'}")
            self._notify_state_change()

    def set_glycol_setpoints(self, high_temp: float, delta_t: float):
        """Update glycol temperature setpoints"""
        with self._state_lock:
            self.state.glycol_setpoints = Setpoints(high_temp, delta_t)
            logger.info(f"Glycol setpoints: high={high_temp}°F, delta={delta_t}°F")
            self._save_setpoints()
            self._notify_state_change()

    def set_dhw_setpoints(self, high_temp: float, delta_t: float):
        """Update DHW temperature setpoints"""
        with self._state_lock:
            self.state.dhw_setpoints = Setpoints(high_temp, delta_t)
            logger.info(f"DHW setpoints: high={high_temp}°F, delta={delta_t}°F")
            self._save_setpoints()
            self._notify_state_change()

    def set_eco_setpoints(self, high_temp: float, delta_t: float):
        """Update eco mode setpoints"""
        with self._state_lock:
            self.state.eco_setpoints = Setpoints(high_temp, delta_t)
            logger.info(f"Eco setpoints: high={high_temp}°F, delta={delta_t}°F")
            self._save_setpoints()
            self._notify_state_change()

    def set_eco_schedule(self, start_time: str, end_time: str):
        """Update eco mode schedule (24-hour format HH:MM)"""
        with self._state_lock:
            self.state.eco_start = start_time
            self.state.eco_end = end_time
            logger.info(f"Eco schedule: {start_time} - {end_time}")
            self._save_setpoints()
            self._notify_state_change()

    def set_eco_enabled(self, enabled: bool):
        """Enable/disable eco mode"""
        with self._state_lock:
            self.state.eco_enabled = enabled
            logger.info(f"Eco mode {'enabled' if enabled else 'disabled'}")
            self._notify_state_change()

    def start_shutdown_timer(self, hours: int, minutes: int):
        """Start the shutdown delay timer"""
        with self._state_lock:
            total_minutes = hours * 60 + minutes
            if total_minutes <= 0:
                return
            self.state.shutdown_timer_duration_minutes = total_minutes
            self.state.shutdown_timer_end_time = datetime.now() + timedelta(minutes=total_minutes)
            self.state.shutdown_timer_enabled = True
            logger.info(f"Shutdown timer started: {hours}h {minutes}m")
            self._notify_state_change()

    def cancel_shutdown_timer(self):
        """Cancel the shutdown delay timer"""
        with self._state_lock:
            self.state.shutdown_timer_enabled = False
            self.state.shutdown_timer_end_time = None
            self.state.shutdown_timer_duration_minutes = 0
            logger.info("Shutdown timer cancelled")
            self._notify_state_change()

    def get_shutdown_timer_remaining(self) -> Optional[int]:
        """Get remaining time in seconds, or None if timer not active"""
        if not self.state.shutdown_timer_enabled or not self.state.shutdown_timer_end_time:
            return None
        remaining = (self.state.shutdown_timer_end_time - datetime.now()).total_seconds()
        return max(0, int(remaining))

    def set_equipment_mode(self, equipment_id: str, mode: EquipmentMode):
        """Set equipment operating mode"""
        self.relays.set_mode(equipment_id, mode)
        logger.info(f"Equipment {equipment_id} mode set to {mode.value}")
        with self._state_lock:
            self._notify_state_change()

    def get_state(self) -> ControlState:
        """Get current control state - returns cached copy (non-blocking)"""
        # Return cached state for fast GUI reads
        if self._cached_state is not None:
            return self._cached_state
        # Fallback if cache not yet populated
        with self._state_lock:
            return deepcopy(self.state)

    def shutdown(self):
        """Shutdown control logic, saving any pending setpoints"""
        if self._persistence:
            self._persistence.shutdown()
        logger.info("Control logic shutdown complete")
