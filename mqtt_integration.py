"""
Snowmelt Control System - MQTT Integration Module
Handles Home Assistant integration via MQTT with auto-discovery
"""

import json
import logging
import time
from typing import Dict, Optional, Callable
from threading import Thread, Event
from dataclasses import asdict

import paho.mqtt.client as mqtt

from relays import EquipmentMode, RelayState
from control import ControlState, ControlLogic

logger = logging.getLogger(__name__)


class MQTTIntegration:
    """Manages MQTT connection and Home Assistant integration"""
    
    def __init__(self, mqtt_config: Dict, control: ControlLogic):
        self.config = mqtt_config
        self.control = control
        
        self.broker = mqtt_config['broker']
        self.port = mqtt_config.get('port', 1883)
        self.username = mqtt_config.get('username')
        self.password = mqtt_config.get('password')
        self.base_topic = mqtt_config.get('base_topic', 'snowmelt')
        self.discovery_prefix = mqtt_config.get('discovery_prefix', 'homeassistant')
        
        self.client: Optional[mqtt.Client] = None
        self._connected = False
        self._stop_event = Event()
        self._publish_thread: Optional[Thread] = None
        
        # Track last published states to avoid redundant publishes
        self._last_states: Dict[str, str] = {}
        
        logger.info(f"MQTT integration initialized for broker {self.broker}:{self.port}")
    
    def connect(self):
        """Connect to MQTT broker"""
        try:
            self.client = mqtt.Client(client_id=f"snowmelt_control_{int(time.time())}")
            
            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)
            
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            
            # Set last will for availability
            self.client.will_set(
                f"{self.base_topic}/status",
                payload="offline",
                retain=True
            )
            
            logger.info(f"Connecting to MQTT broker {self.broker}:{self.port}")
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()
            
            # Start publish thread
            self._stop_event.clear()
            self._publish_thread = Thread(target=self._publish_loop, daemon=True)
            self._publish_thread.start()
            
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            raise
    
    def _on_connect(self, client, userdata, flags, rc):
        """Handle MQTT connection"""
        if rc == 0:
            logger.info("Connected to MQTT broker")
            self._connected = True
            
            # Publish online status
            self.client.publish(f"{self.base_topic}/status", "online", retain=True)
            
            # Subscribe to command topics
            self._subscribe_to_commands()
            
            # Publish discovery configs
            self._publish_discovery()
            
        else:
            logger.error(f"Failed to connect to MQTT broker, code: {rc}")
            self._connected = False
    
    def _on_disconnect(self, client, userdata, rc):
        """Handle MQTT disconnection"""
        logger.warning(f"Disconnected from MQTT broker, code: {rc}")
        self._connected = False
    
    def _subscribe_to_commands(self):
        """Subscribe to command topics"""
        topics = [
            f"{self.base_topic}/+/mode/set",      # Equipment mode commands
            f"{self.base_topic}/system/+/set",    # System enable commands
            f"{self.base_topic}/setpoint/+/set",  # Setpoint commands
        ]
        
        for topic in topics:
            self.client.subscribe(topic)
            logger.debug(f"Subscribed to {topic}")
    
    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages"""
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            logger.debug(f"MQTT message: {topic} = {payload}")
            
            # Parse topic structure
            parts = topic.split('/')
            if len(parts) < 3:
                return
            
            # Equipment mode commands: snowmelt/{equipment}/mode/set
            if len(parts) == 4 and parts[2] == 'mode' and parts[3] == 'set':
                equipment_id = parts[1]
                self._handle_mode_command(equipment_id, payload)
            
            # System enable commands: snowmelt/system/{system}/set
            elif len(parts) == 4 and parts[1] == 'system' and parts[3] == 'set':
                system_name = parts[2]
                self._handle_system_command(system_name, payload)
            
            # Setpoint commands: snowmelt/setpoint/{setpoint}/set
            elif len(parts) == 4 and parts[1] == 'setpoint' and parts[3] == 'set':
                setpoint_name = parts[2]
                self._handle_setpoint_command(setpoint_name, payload)
                
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")
    
    def _handle_mode_command(self, equipment_id: str, mode_str: str):
        """Handle equipment mode change command"""
        try:
            mode = EquipmentMode(mode_str.lower())
            self.control.set_equipment_mode(equipment_id, mode)
            logger.info(f"MQTT: Set {equipment_id} mode to {mode.value}")
        except ValueError:
            logger.error(f"Invalid mode value: {mode_str}")
    
    def _handle_system_command(self, system_name: str, payload: str):
        """Handle system enable/disable command"""
        enabled = payload.lower() in ('on', 'true', '1', 'enable')
        
        if system_name == 'snowmelt':
            self.control.set_snowmelt_enabled(enabled)
        elif system_name == 'dhw':
            self.control.set_dhw_enabled(enabled)
        elif system_name == 'eco':
            self.control.set_eco_enabled(enabled)
        else:
            logger.warning(f"Unknown system: {system_name}")
    
    def _handle_setpoint_command(self, setpoint_name: str, payload: str):
        """Handle setpoint change command"""
        try:
            data = json.loads(payload)
            high_temp = float(data.get('high_temp', data.get('high', 0)))
            delta_t = float(data.get('delta_t', data.get('delta', 0)))
            
            if setpoint_name == 'glycol':
                self.control.set_glycol_setpoints(high_temp, delta_t)
            elif setpoint_name == 'dhw':
                self.control.set_dhw_setpoints(high_temp, delta_t)
            elif setpoint_name == 'eco':
                self.control.set_eco_setpoints(high_temp, delta_t)
            elif setpoint_name == 'eco_schedule':
                start = data.get('start', '22:00')
                end = data.get('end', '06:00')
                self.control.set_eco_schedule(start, end)
            else:
                logger.warning(f"Unknown setpoint: {setpoint_name}")
                
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Invalid setpoint payload: {e}")
    
    def _publish_discovery(self):
        """Publish Home Assistant MQTT discovery configurations"""
        device_info = {
            "identifiers": ["snowmelt_control"],
            "name": "Snowmelt Control System",
            "model": "RPi Snowmelt Controller",
            "manufacturer": "Custom",
            "sw_version": "1.0.0"
        }
        
        # Temperature sensors
        sensors = [
            ("glycol_return", "Glycol Return Temperature", "°F"),
            ("glycol_supply", "Glycol Supply Temperature", "°F"),
            ("hx_in", "Heat Exchanger In", "°F"),
            ("hx_out", "Heat Exchanger Out", "°F"),
            ("dhw_tank", "DHW Tank Temperature", "°F"),
            ("hx_delta_t", "Heat Exchanger Delta T", "°F"),
        ]
        
        for sensor_id, name, unit in sensors:
            config = {
                "name": name,
                "unique_id": f"snowmelt_{sensor_id}",
                "state_topic": f"{self.base_topic}/sensor/{sensor_id}",
                "unit_of_measurement": unit,
                "device_class": "temperature" if unit == "°F" else None,
                "device": device_info,
                "availability_topic": f"{self.base_topic}/status"
            }
            config = {k: v for k, v in config.items() if v is not None}
            
            self.client.publish(
                f"{self.discovery_prefix}/sensor/snowmelt/{sensor_id}/config",
                json.dumps(config),
                retain=True
            )
        
        # Equipment switches (with mode select)
        equipment = [
            ("glycol_pump", "Glycol Pump"),
            ("primary_pump", "Primary Pump"),
            ("bypass_valve", "Bypass Valve"),
            ("dhw_pump", "DHW Recirculation Pump"),
        ]
        
        for equip_id, name in equipment:
            # Binary sensor for actual state
            state_config = {
                "name": f"{name} State",
                "unique_id": f"snowmelt_{equip_id}_state",
                "state_topic": f"{self.base_topic}/{equip_id}/state",
                "payload_on": "ON",
                "payload_off": "OFF",
                "device": device_info,
                "availability_topic": f"{self.base_topic}/status"
            }
            self.client.publish(
                f"{self.discovery_prefix}/binary_sensor/snowmelt/{equip_id}_state/config",
                json.dumps(state_config),
                retain=True
            )
            
            # Select for mode
            mode_config = {
                "name": f"{name} Mode",
                "unique_id": f"snowmelt_{equip_id}_mode",
                "state_topic": f"{self.base_topic}/{equip_id}/mode",
                "command_topic": f"{self.base_topic}/{equip_id}/mode/set",
                "options": ["auto", "on", "off"],
                "device": device_info,
                "availability_topic": f"{self.base_topic}/status"
            }
            self.client.publish(
                f"{self.discovery_prefix}/select/snowmelt/{equip_id}_mode/config",
                json.dumps(mode_config),
                retain=True
            )
        
        # System switches
        systems = [
            ("snowmelt", "Snowmelt System"),
            ("dhw", "DHW System"),
            ("eco", "Eco Mode"),
        ]
        
        for sys_id, name in systems:
            switch_config = {
                "name": name,
                "unique_id": f"snowmelt_{sys_id}_enabled",
                "state_topic": f"{self.base_topic}/system/{sys_id}",
                "command_topic": f"{self.base_topic}/system/{sys_id}/set",
                "payload_on": "ON",
                "payload_off": "OFF",
                "device": device_info,
                "availability_topic": f"{self.base_topic}/status"
            }
            self.client.publish(
                f"{self.discovery_prefix}/switch/snowmelt/{sys_id}/config",
                json.dumps(switch_config),
                retain=True
            )
        
        # Number inputs for setpoints
        setpoints = [
            ("glycol_high", "Glycol High Setpoint", 80, 140, 1),
            ("glycol_delta", "Glycol Delta T", 5, 30, 1),
            ("dhw_high", "DHW High Setpoint", 100, 140, 1),
            ("dhw_delta", "DHW Delta T", 5, 20, 1),
            ("eco_high", "Eco High Setpoint", 100, 130, 1),
            ("eco_delta", "Eco Delta T", 5, 25, 1),
        ]
        
        for sp_id, name, min_val, max_val, step in setpoints:
            number_config = {
                "name": name,
                "unique_id": f"snowmelt_{sp_id}",
                "state_topic": f"{self.base_topic}/setpoint/{sp_id}",
                "command_topic": f"{self.base_topic}/setpoint/{sp_id}/set",
                "min": min_val,
                "max": max_val,
                "step": step,
                "unit_of_measurement": "°F",
                "device": device_info,
                "availability_topic": f"{self.base_topic}/status"
            }
            self.client.publish(
                f"{self.discovery_prefix}/number/snowmelt/{sp_id}/config",
                json.dumps(number_config),
                retain=True
            )
        
        # System state sensors
        state_sensors = [
            ("snowmelt_state", "Snowmelt State"),
            ("dhw_state", "DHW State"),
            ("eco_active", "Eco Mode Active"),
        ]
        
        for state_id, name in state_sensors:
            config = {
                "name": name,
                "unique_id": f"snowmelt_{state_id}",
                "state_topic": f"{self.base_topic}/state/{state_id}",
                "device": device_info,
                "availability_topic": f"{self.base_topic}/status"
            }
            self.client.publish(
                f"{self.discovery_prefix}/sensor/snowmelt/{state_id}/config",
                json.dumps(config),
                retain=True
            )
        
        logger.info("Published Home Assistant discovery configurations")
    
    def _publish_loop(self):
        """Background thread for publishing state updates"""
        while not self._stop_event.is_set():
            if self._connected:
                try:
                    self._publish_state()
                except Exception as e:
                    logger.error(f"Error publishing state: {e}")
            
            self._stop_event.wait(5)  # Publish every 5 seconds
    
    def _publish_state(self):
        """Publish current system state to MQTT"""
        state = self.control.get_state()
        relay_states = self.control.relays.get_all_states()
        
        # Publish temperatures
        temps = {
            'glycol_return': state.glycol_return_temp,
            'glycol_supply': state.glycol_supply_temp,
            'hx_in': state.hx_in_temp,
            'hx_out': state.hx_out_temp,
            'dhw_tank': state.dhw_tank_temp,
            'hx_delta_t': state.hx_delta_t,
        }
        
        for sensor_id, temp in temps.items():
            value = str(round(temp, 1)) if temp is not None else "unavailable"
            self._publish_if_changed(f"{self.base_topic}/sensor/{sensor_id}", value)
        
        # Publish equipment states and modes
        for equip_id, relay_state in relay_states.items():
            state_value = "ON" if relay_state.is_energized else "OFF"
            self._publish_if_changed(f"{self.base_topic}/{equip_id}/state", state_value)
            self._publish_if_changed(f"{self.base_topic}/{equip_id}/mode", relay_state.mode.value)
        
        # Publish system states
        self._publish_if_changed(
            f"{self.base_topic}/system/snowmelt",
            "ON" if state.snowmelt_enabled else "OFF"
        )
        self._publish_if_changed(
            f"{self.base_topic}/system/dhw",
            "ON" if state.dhw_enabled else "OFF"
        )
        self._publish_if_changed(
            f"{self.base_topic}/system/eco",
            "ON" if state.eco_enabled else "OFF"
        )
        
        # Publish state values
        self._publish_if_changed(
            f"{self.base_topic}/state/snowmelt_state",
            state.snowmelt_state.value
        )
        self._publish_if_changed(
            f"{self.base_topic}/state/dhw_state",
            state.dhw_state.value
        )
        self._publish_if_changed(
            f"{self.base_topic}/state/eco_active",
            "ON" if state.eco_active else "OFF"
        )
        
        # Publish setpoints
        self._publish_if_changed(
            f"{self.base_topic}/setpoint/glycol_high",
            str(state.glycol_setpoints.high_temp)
        )
        self._publish_if_changed(
            f"{self.base_topic}/setpoint/glycol_delta",
            str(state.glycol_setpoints.delta_t)
        )
        self._publish_if_changed(
            f"{self.base_topic}/setpoint/dhw_high",
            str(state.dhw_setpoints.high_temp)
        )
        self._publish_if_changed(
            f"{self.base_topic}/setpoint/dhw_delta",
            str(state.dhw_setpoints.delta_t)
        )
        self._publish_if_changed(
            f"{self.base_topic}/setpoint/eco_high",
            str(state.eco_setpoints.high_temp)
        )
        self._publish_if_changed(
            f"{self.base_topic}/setpoint/eco_delta",
            str(state.eco_setpoints.delta_t)
        )
    
    def _publish_if_changed(self, topic: str, value: str):
        """Only publish if value has changed"""
        if self._last_states.get(topic) != value:
            self.client.publish(topic, value, retain=True)
            self._last_states[topic] = value
    
    def publish_now(self):
        """Force immediate state publish"""
        if self._connected:
            self._publish_state()
    
    def disconnect(self):
        """Disconnect from MQTT broker"""
        self._stop_event.set()
        
        if self.client:
            self.client.publish(f"{self.base_topic}/status", "offline", retain=True)
            self.client.disconnect()
            self.client.loop_stop()
        
        logger.info("Disconnected from MQTT broker")
