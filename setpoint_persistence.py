"""
Snowmelt Control System - Setpoint Persistence Module
Handles saving and loading user-modified setpoints to survive reboots
"""

import logging
import shutil
from pathlib import Path
from threading import Lock, Timer
from typing import Dict, Optional
from dataclasses import dataclass, asdict

import yaml

logger = logging.getLogger(__name__)

# Default persistence file location (same directory as this module)
DEFAULT_STATE_FILE = Path(__file__).parent / "setpoints_state.yaml"
SAVE_DEBOUNCE_SECONDS = 5.0


@dataclass
class PersistedSetpoints:
    """Data structure for persistent setpoints"""
    glycol_high_temp: float
    glycol_delta_t: float
    dhw_high_temp: float
    dhw_delta_t: float
    eco_high_temp: float
    eco_delta_t: float
    eco_start: str
    eco_end: str

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'PersistedSetpoints':
        return cls(
            glycol_high_temp=float(data.get('glycol_high_temp', 110.0)),
            glycol_delta_t=float(data.get('glycol_delta_t', 15.0)),
            dhw_high_temp=float(data.get('dhw_high_temp', 125.0)),
            dhw_delta_t=float(data.get('dhw_delta_t', 10.0)),
            eco_high_temp=float(data.get('eco_high_temp', 115.0)),
            eco_delta_t=float(data.get('eco_delta_t', 15.0)),
            eco_start=str(data.get('eco_start', '22:00')),
            eco_end=str(data.get('eco_end', '06:00'))
        )


class SetpointPersistence:
    """Manages persistence of setpoints to disk with debouncing"""

    def __init__(self, state_file: Path = DEFAULT_STATE_FILE,
                 debounce_seconds: float = SAVE_DEBOUNCE_SECONDS):
        self.state_file = Path(state_file)
        self.debounce_seconds = debounce_seconds
        self._lock = Lock()
        self._pending_save: Optional[PersistedSetpoints] = None
        self._save_timer: Optional[Timer] = None
        self._shutdown = False

        logger.info(f"Setpoint persistence initialized: {self.state_file}")

    def load(self, defaults: Dict) -> PersistedSetpoints:
        """Load persisted setpoints, falling back to defaults for missing values"""
        # Build merged defaults from config.yaml structure
        glycol_defaults = defaults.get('glycol', {})
        dhw_defaults = defaults.get('dhw', {})
        eco_defaults = defaults.get('eco', {})
        eco_schedule = defaults.get('eco_schedule', {})

        merged = {
            'glycol_high_temp': glycol_defaults.get('high_temp', 110.0),
            'glycol_delta_t': glycol_defaults.get('delta_t', 15.0),
            'dhw_high_temp': dhw_defaults.get('high_temp', 125.0),
            'dhw_delta_t': dhw_defaults.get('delta_t', 10.0),
            'eco_high_temp': eco_defaults.get('high_temp', 115.0),
            'eco_delta_t': eco_defaults.get('delta_t', 15.0),
            'eco_start': eco_schedule.get('start_time', '22:00'),
            'eco_end': eco_schedule.get('end_time', '06:00'),
        }

        # Try to load persisted state and merge
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    persisted = yaml.safe_load(f) or {}

                # Override defaults with persisted values
                for key in merged.keys():
                    if key in persisted:
                        merged[key] = persisted[key]

                logger.info(f"Loaded persisted setpoints from {self.state_file}")
            except Exception as e:
                logger.error(f"Error loading persisted setpoints: {e}")
                logger.warning("Using default setpoints")
        else:
            logger.info("No persisted setpoints found, using defaults")

        return PersistedSetpoints.from_dict(merged)

    def save(self, setpoints: PersistedSetpoints):
        """Queue setpoints for debounced save to minimize SD card writes"""
        with self._lock:
            if self._shutdown:
                return

            self._pending_save = setpoints

            # Cancel existing timer
            if self._save_timer is not None:
                self._save_timer.cancel()

            # Start new timer
            self._save_timer = Timer(self.debounce_seconds, self._do_save)
            self._save_timer.daemon = True
            self._save_timer.start()

            logger.debug("Setpoint save queued (debounced)")

    def _do_save(self):
        """Actually perform the atomic save"""
        with self._lock:
            if self._pending_save is None:
                return

            setpoints = self._pending_save
            self._pending_save = None
            self._save_timer = None

        try:
            # Write to temp file first (atomic write pattern)
            temp_file = self.state_file.with_suffix('.tmp')

            with open(temp_file, 'w') as f:
                yaml.safe_dump(setpoints.to_dict(), f, default_flow_style=False)

            # Atomic rename
            shutil.move(str(temp_file), str(self.state_file))

            logger.info(f"Setpoints persisted to {self.state_file}")
        except Exception as e:
            logger.error(f"Error saving setpoints: {e}")

    def save_now(self):
        """Force immediate save (for shutdown)"""
        with self._lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
                self._save_timer = None

        # Perform save directly if there's pending data
        self._do_save()

    def shutdown(self):
        """Clean shutdown - save any pending changes immediately"""
        with self._lock:
            self._shutdown = True
            if self._save_timer is not None:
                self._save_timer.cancel()
                self._save_timer = None

        # Save any pending changes
        self._do_save()
        logger.info("Setpoint persistence shut down")
