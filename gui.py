"""
Snowmelt Control System - Touchscreen GUI
PyQt5-based interface for 7" Waveshare touchscreen (800x480)
Optimized for fullscreen kiosk mode
"""

import sys
import logging
from datetime import datetime
from typing import Dict, Optional

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QFrame, QTabWidget,
    QGroupBox, QDoubleSpinBox, QTimeEdit, QCheckBox,
    QButtonGroup, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, QTime, pyqtSignal
from PyQt5.QtGui import QFont

from relays import EquipmentMode, RelayState
from control import ControlLogic, ControlState, SystemState

logger = logging.getLogger(__name__)

# Screen dimensions for Waveshare 7" (1024x600)
SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 600


class StyleSheet:
    """Centralized stylesheet for the application"""
    
    MAIN = """
        QMainWindow {
            background-color: #1a1a2e;
        }
        QWidget {
            background-color: #1a1a2e;
            color: #eaeaea;
            font-family: 'DejaVu Sans', sans-serif;
            font-size: 12px;
        }
        QTabWidget::pane {
            border: 2px solid #3d3d5c;
            border-radius: 8px;
            background-color: #16213e;
            padding: 4px;
        }
        QTabBar::tab {
            background-color: #0f3460;
            color: #eaeaea;
            padding: 10px 35px;
            margin-right: 3px;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            font-size: 14px;
            font-weight: bold;
        }
        QTabBar::tab:selected {
            background-color: #e94560;
        }
        QTabBar::tab:hover:!selected {
            background-color: #1a5276;
        }
        QGroupBox {
            border: 2px solid #3d3d5c;
            border-radius: 8px;
            margin-top: 10px;
            padding: 6px;
            padding-top: 14px;
            font-size: 13px;
            font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 6px;
            color: #e94560;
        }
        QPushButton {
            background-color: #0f3460;
            color: #eaeaea;
            border: 2px solid #3d3d5c;
            border-radius: 6px;
            padding: 6px 12px;
            font-size: 12px;
            font-weight: bold;
            min-height: 32px;
            min-width: 55px;
        }
        QPushButton:hover {
            background-color: #1a5276;
            border-color: #e94560;
        }
        QPushButton:pressed {
            background-color: #e94560;
        }
        QPushButton:checked {
            background-color: #e94560;
            border-color: #e94560;
        }
        QPushButton:disabled {
            background-color: #2d2d44;
            color: #666666;
        }
        QDoubleSpinBox, QTimeEdit {
            background-color: #16213e;
            border: 2px solid #3d3d5c;
            border-radius: 6px;
            padding: 4px 6px;
            font-size: 13px;
            min-height: 28px;
            max-width: 110px;
        }
        QDoubleSpinBox:focus, QTimeEdit:focus {
            border-color: #e94560;
        }
        QCheckBox {
            font-size: 13px;
            spacing: 8px;
        }
        QCheckBox::indicator {
            width: 22px;
            height: 22px;
            border-radius: 4px;
            border: 2px solid #3d3d5c;
            background-color: #16213e;
        }
        QCheckBox::indicator:checked {
            background-color: #e94560;
            border-color: #e94560;
        }
        QLabel {
            font-size: 12px;
        }
    """
    
    @staticmethod
    def temp_display(temp: Optional[float], high: float = None, low: float = None) -> str:
        """Get color style based on temperature status"""
        if temp is None:
            return "color: #ff6b6b; font-weight: bold;"
        if high is not None and temp >= high:
            return "color: #51cf66; font-weight: bold;"
        elif low is not None and temp <= low:
            return "color: #ffa94d; font-weight: bold;"
        else:
            return "color: #74c0fc; font-weight: bold;"
    
    @staticmethod
    def status_indicator(active: bool) -> str:
        """Get style for status indicator"""
        color = "#51cf66" if active else "#495057"
        return f"""
            background-color: {color};
            border-radius: 10px;
            min-width: 20px; max-width: 20px;
            min-height: 20px; max-height: 20px;
        """


class TemperatureDisplay(QFrame):
    """Custom widget for displaying temperature with label"""
    
    def __init__(self, label: str, unit: str = "°F"):
        super().__init__()
        self.unit = unit
        self._value: Optional[float] = None
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        
        self.label = QLabel(label)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("font-size: 12px; color: #adb5bd;")
        
        self.value_label = QLabel("--")
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #74c0fc;")
        
        layout.addWidget(self.label)
        layout.addWidget(self.value_label)
        
        self.setStyleSheet("""
            QFrame {
                background-color: #16213e;
                border: 2px solid #3d3d5c;
                border-radius: 8px;
            }
        """)
        self.setMinimumHeight(70)
        self.setMaximumHeight(90)
    
    def set_value(self, value: Optional[float], style: str = None):
        """Update the displayed value"""
        self._value = value
        if value is not None:
            self.value_label.setText(f"{value:.1f}{self.unit}")
        else:
            self.value_label.setText("--")
        if style:
            self.value_label.setStyleSheet(f"font-size: 22px; {style}")


class EquipmentControl(QFrame):
    """Custom widget for controlling equipment with mode selection"""
    
    mode_changed = pyqtSignal(str, str)
    
    def __init__(self, equipment_id: str, name: str):
        super().__init__()
        self.equipment_id = equipment_id
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(12)
        
        # Status indicator
        self.status_indicator = QLabel()
        self.status_indicator.setStyleSheet(StyleSheet.status_indicator(False))
        self.status_indicator.setFixedSize(20, 20)
        
        # Name label - fixed width to prevent overflow
        name_label = QLabel(name)
        name_label.setStyleSheet("font-size: 13px; font-weight: bold;")
        name_label.setFixedWidth(160)
        
        layout.addWidget(self.status_indicator)
        layout.addWidget(name_label)
        layout.addStretch()
        
        # Mode buttons
        self.btn_group = QButtonGroup(self)
        self.btn_auto = QPushButton("Auto")
        self.btn_on = QPushButton("On")
        self.btn_off = QPushButton("Off")
        
        for btn in [self.btn_auto, self.btn_on, self.btn_off]:
            btn.setCheckable(True)
            btn.setFixedWidth(65)
            btn.setFixedHeight(34)
            self.btn_group.addButton(btn)
            layout.addWidget(btn)
        
        self.btn_auto.setChecked(True)
        self.btn_auto.clicked.connect(lambda: self._on_mode_clicked("auto"))
        self.btn_on.clicked.connect(lambda: self._on_mode_clicked("on"))
        self.btn_off.clicked.connect(lambda: self._on_mode_clicked("off"))
        
        self.setStyleSheet("""
            QFrame {
                background-color: #16213e;
                border: 2px solid #3d3d5c;
                border-radius: 8px;
            }
        """)
        self.setFixedHeight(50)
    
    def _on_mode_clicked(self, mode: str):
        self.mode_changed.emit(self.equipment_id, mode)
    
    def update_state(self, state: RelayState):
        self.status_indicator.setStyleSheet(StyleSheet.status_indicator(state.is_energized))
        mode_map = {
            EquipmentMode.AUTO: self.btn_auto,
            EquipmentMode.ON: self.btn_on,
            EquipmentMode.OFF: self.btn_off
        }
        btn = mode_map.get(state.mode)
        if btn and not btn.isChecked():
            btn.setChecked(True)


class DashboardTab(QWidget):
    """Main dashboard showing system overview"""
    
    def __init__(self, control: ControlLogic):
        super().__init__()
        self.control = control
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        
        # Status row - horizontal layout
        status_group = QGroupBox("System Status")
        status_layout = QHBoxLayout(status_group)
        status_layout.setContentsMargins(12, 6, 12, 6)
        status_layout.setSpacing(30)
        
        self.snowmelt_status = QLabel("Snowmelt: IDLE")
        self.snowmelt_status.setStyleSheet("font-size: 15px; font-weight: bold;")
        
        self.dhw_status = QLabel("DHW: IDLE")
        self.dhw_status.setStyleSheet("font-size: 15px; font-weight: bold;")
        
        self.eco_status = QLabel("Eco: OFF")
        self.eco_status.setStyleSheet("font-size: 15px; font-weight: bold;")
        
        status_layout.addWidget(self.snowmelt_status)
        status_layout.addWidget(self.dhw_status)
        status_layout.addWidget(self.eco_status)
        status_layout.addStretch()
        
        # Temperature displays - 2 rows x 3 columns
        temp_group = QGroupBox("Temperatures")
        temp_layout = QGridLayout(temp_group)
        temp_layout.setContentsMargins(6, 6, 6, 6)
        temp_layout.setSpacing(8)
        
        self.temp_glycol_return = TemperatureDisplay("Glycol Return")
        self.temp_glycol_supply = TemperatureDisplay("Glycol Supply")
        self.temp_hx_in = TemperatureDisplay("HX In")
        self.temp_hx_out = TemperatureDisplay("HX Out")
        self.temp_dhw = TemperatureDisplay("DHW Tank")
        self.temp_hx_delta = TemperatureDisplay("HX ΔT")
        
        temp_layout.addWidget(self.temp_glycol_return, 0, 0)
        temp_layout.addWidget(self.temp_glycol_supply, 0, 1)
        temp_layout.addWidget(self.temp_hx_in, 0, 2)
        temp_layout.addWidget(self.temp_hx_out, 1, 0)
        temp_layout.addWidget(self.temp_dhw, 1, 1)
        temp_layout.addWidget(self.temp_hx_delta, 1, 2)
        
        # Time display at bottom
        self.time_label = QLabel()
        self.time_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #e94560;")
        self.time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        layout.addWidget(status_group)
        layout.addWidget(temp_group, 1)
        layout.addWidget(self.time_label)
    
    def update_display(self, state: ControlState):
        colors = {
            SystemState.IDLE: "#adb5bd",
            SystemState.HEATING: "#51cf66",
            SystemState.BYPASS: "#74c0fc",
            SystemState.ERROR: "#ff6b6b"
        }
        
        color = colors.get(state.snowmelt_state, "#adb5bd")
        self.snowmelt_status.setText(f"Snowmelt: {state.snowmelt_state.value.upper()}")
        self.snowmelt_status.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {color};")
        
        color = colors.get(state.dhw_state, "#adb5bd")
        self.dhw_status.setText(f"DHW: {state.dhw_state.value.upper()}")
        self.dhw_status.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {color};")
        
        eco_color = "#51cf66" if state.eco_active else "#adb5bd"
        self.eco_status.setText(f"Eco: {'ON' if state.eco_active else 'OFF'}")
        self.eco_status.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {eco_color};")
        
        # Update temperatures
        glycol_sp = state.glycol_setpoints
        self.temp_glycol_return.set_value(
            state.glycol_return_temp,
            StyleSheet.temp_display(state.glycol_return_temp, glycol_sp.high_temp, glycol_sp.low_temp)
        )
        self.temp_glycol_supply.set_value(state.glycol_supply_temp)
        self.temp_hx_in.set_value(state.hx_in_temp)
        self.temp_hx_out.set_value(state.hx_out_temp)
        
        dhw_sp = state.eco_setpoints if state.eco_active else state.dhw_setpoints
        self.temp_dhw.set_value(
            state.dhw_tank_temp,
            StyleSheet.temp_display(state.dhw_tank_temp, dhw_sp.high_temp, dhw_sp.low_temp)
        )
        self.temp_hx_delta.set_value(state.hx_delta_t)
        
        # Update time
        now = datetime.now()
        self.time_label.setText(now.strftime("%H:%M:%S   %Y-%m-%d"))


class EquipmentTab(QWidget):
    """Equipment control tab"""
    
    mode_changed = pyqtSignal(str, str)
    
    def __init__(self, control: ControlLogic):
        super().__init__()
        self.control = control
        self.equipment_widgets: Dict[str, EquipmentControl] = {}
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        
        # Snowmelt equipment group
        snowmelt_group = QGroupBox("Snowmelt System")
        snowmelt_layout = QVBoxLayout(snowmelt_group)
        snowmelt_layout.setContentsMargins(6, 6, 6, 6)
        snowmelt_layout.setSpacing(6)
        
        glycol_pump = EquipmentControl("glycol_pump", "Glycol Pump")
        primary_pump = EquipmentControl("primary_pump", "Primary Pump")
        bypass_valve = EquipmentControl("bypass_valve", "Bypass Valve")
        
        for widget in [glycol_pump, primary_pump, bypass_valve]:
            widget.mode_changed.connect(self._on_mode_changed)
            snowmelt_layout.addWidget(widget)
            self.equipment_widgets[widget.equipment_id] = widget
        
        # DHW equipment group
        dhw_group = QGroupBox("DHW System")
        dhw_layout = QVBoxLayout(dhw_group)
        dhw_layout.setContentsMargins(6, 6, 6, 6)
        dhw_layout.setSpacing(6)
        
        dhw_pump = EquipmentControl("dhw_pump", "DHW Recirc Pump")
        dhw_pump.mode_changed.connect(self._on_mode_changed)
        dhw_layout.addWidget(dhw_pump)
        self.equipment_widgets["dhw_pump"] = dhw_pump
        
        layout.addWidget(snowmelt_group)
        layout.addWidget(dhw_group)
        layout.addStretch()
    
    def _on_mode_changed(self, equipment_id: str, mode: str):
        self.mode_changed.emit(equipment_id, mode)
    
    def update_display(self, relay_states: Dict[str, RelayState]):
        for equip_id, widget in self.equipment_widgets.items():
            if equip_id in relay_states:
                widget.update_state(relay_states[equip_id])


class SetpointsTab(QWidget):
    """Setpoints configuration tab - compact layout for 800x480"""
    
    setpoint_changed = pyqtSignal(str, float, float)
    system_toggled = pyqtSignal(str, bool)
    eco_schedule_changed = pyqtSignal(str, str)
    
    def __init__(self, control: ControlLogic):
        super().__init__()
        self.control = control
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)
        
        # Left column - Snowmelt
        snowmelt_group = QGroupBox("Snowmelt")
        snowmelt_layout = QGridLayout(snowmelt_group)
        snowmelt_layout.setContentsMargins(10, 10, 10, 10)
        snowmelt_layout.setSpacing(8)
        snowmelt_layout.setColumnStretch(1, 1)
        
        self.snowmelt_enabled = QCheckBox("Enable")
        self.snowmelt_enabled.toggled.connect(lambda checked: self.system_toggled.emit("snowmelt", checked))
        snowmelt_layout.addWidget(self.snowmelt_enabled, 0, 0, 1, 2)
        
        snowmelt_layout.addWidget(QLabel("High:"), 1, 0)
        self.glycol_high = QDoubleSpinBox()
        self.glycol_high.setRange(80, 140)
        self.glycol_high.setSuffix(" °F")
        self.glycol_high.valueChanged.connect(self._on_glycol_changed)
        snowmelt_layout.addWidget(self.glycol_high, 1, 1)
        
        snowmelt_layout.addWidget(QLabel("Delta:"), 2, 0)
        self.glycol_delta = QDoubleSpinBox()
        self.glycol_delta.setRange(5, 30)
        self.glycol_delta.setSuffix(" °F")
        self.glycol_delta.valueChanged.connect(self._on_glycol_changed)
        snowmelt_layout.addWidget(self.glycol_delta, 2, 1)
        
        self.glycol_low_label = QLabel("Low: --")
        self.glycol_low_label.setStyleSheet("color: #adb5bd; font-size: 11px;")
        snowmelt_layout.addWidget(self.glycol_low_label, 3, 0, 1, 2)
        
        # Middle column - DHW
        dhw_group = QGroupBox("DHW")
        dhw_layout = QGridLayout(dhw_group)
        dhw_layout.setContentsMargins(10, 10, 10, 10)
        dhw_layout.setSpacing(8)
        dhw_layout.setColumnStretch(1, 1)
        
        self.dhw_enabled = QCheckBox("Enable")
        self.dhw_enabled.toggled.connect(lambda checked: self.system_toggled.emit("dhw", checked))
        dhw_layout.addWidget(self.dhw_enabled, 0, 0, 1, 2)
        
        dhw_layout.addWidget(QLabel("High:"), 1, 0)
        self.dhw_high = QDoubleSpinBox()
        self.dhw_high.setRange(100, 140)
        self.dhw_high.setSuffix(" °F")
        self.dhw_high.valueChanged.connect(self._on_dhw_changed)
        dhw_layout.addWidget(self.dhw_high, 1, 1)
        
        dhw_layout.addWidget(QLabel("Delta:"), 2, 0)
        self.dhw_delta = QDoubleSpinBox()
        self.dhw_delta.setRange(5, 20)
        self.dhw_delta.setSuffix(" °F")
        self.dhw_delta.valueChanged.connect(self._on_dhw_changed)
        dhw_layout.addWidget(self.dhw_delta, 2, 1)
        
        self.dhw_low_label = QLabel("Low: --")
        self.dhw_low_label.setStyleSheet("color: #adb5bd; font-size: 11px;")
        dhw_layout.addWidget(self.dhw_low_label, 3, 0, 1, 2)
        
        # Right column - Eco Mode
        eco_group = QGroupBox("Eco Mode")
        eco_layout = QGridLayout(eco_group)
        eco_layout.setContentsMargins(10, 10, 10, 10)
        eco_layout.setSpacing(8)
        eco_layout.setColumnStretch(1, 1)
        
        self.eco_enabled = QCheckBox("Enable")
        self.eco_enabled.toggled.connect(lambda checked: self.system_toggled.emit("eco", checked))
        eco_layout.addWidget(self.eco_enabled, 0, 0, 1, 2)
        
        eco_layout.addWidget(QLabel("High:"), 1, 0)
        self.eco_high = QDoubleSpinBox()
        self.eco_high.setRange(100, 130)
        self.eco_high.setSuffix(" °F")
        self.eco_high.valueChanged.connect(self._on_eco_changed)
        eco_layout.addWidget(self.eco_high, 1, 1)
        
        eco_layout.addWidget(QLabel("Delta:"), 2, 0)
        self.eco_delta = QDoubleSpinBox()
        self.eco_delta.setRange(5, 25)
        self.eco_delta.setSuffix(" °F")
        self.eco_delta.valueChanged.connect(self._on_eco_changed)
        eco_layout.addWidget(self.eco_delta, 2, 1)
        
        eco_layout.addWidget(QLabel("Start:"), 3, 0)
        self.eco_start = QTimeEdit()
        self.eco_start.setDisplayFormat("HH:mm")
        self.eco_start.timeChanged.connect(self._on_eco_schedule_changed)
        eco_layout.addWidget(self.eco_start, 3, 1)
        
        eco_layout.addWidget(QLabel("End:"), 4, 0)
        self.eco_end = QTimeEdit()
        self.eco_end.setDisplayFormat("HH:mm")
        self.eco_end.timeChanged.connect(self._on_eco_schedule_changed)
        eco_layout.addWidget(self.eco_end, 4, 1)
        
        layout.addWidget(snowmelt_group)
        layout.addWidget(dhw_group)
        layout.addWidget(eco_group)
    
    def _on_glycol_changed(self):
        high = self.glycol_high.value()
        delta = self.glycol_delta.value()
        low = high - delta
        self.glycol_low_label.setText(f"Low: {low:.1f}°F")
        self.setpoint_changed.emit("glycol", high, delta)
    
    def _on_dhw_changed(self):
        high = self.dhw_high.value()
        delta = self.dhw_delta.value()
        low = high - delta
        self.dhw_low_label.setText(f"Low: {low:.1f}°F")
        self.setpoint_changed.emit("dhw", high, delta)
    
    def _on_eco_changed(self):
        self.setpoint_changed.emit("eco", self.eco_high.value(), self.eco_delta.value())
    
    def _on_eco_schedule_changed(self):
        start = self.eco_start.time().toString("HH:mm")
        end = self.eco_end.time().toString("HH:mm")
        self.eco_schedule_changed.emit(start, end)
    
    def update_display(self, state: ControlState):
        # Block signals to avoid feedback loops
        widgets = [self.snowmelt_enabled, self.dhw_enabled, self.eco_enabled,
                   self.glycol_high, self.glycol_delta, self.dhw_high, self.dhw_delta,
                   self.eco_high, self.eco_delta, self.eco_start, self.eco_end]
        for widget in widgets:
            widget.blockSignals(True)
        
        self.snowmelt_enabled.setChecked(state.snowmelt_enabled)
        self.dhw_enabled.setChecked(state.dhw_enabled)
        self.eco_enabled.setChecked(state.eco_enabled)
        
        self.glycol_high.setValue(state.glycol_setpoints.high_temp)
        self.glycol_delta.setValue(state.glycol_setpoints.delta_t)
        self.glycol_low_label.setText(f"Low: {state.glycol_setpoints.low_temp:.1f}°F")
        
        self.dhw_high.setValue(state.dhw_setpoints.high_temp)
        self.dhw_delta.setValue(state.dhw_setpoints.delta_t)
        self.dhw_low_label.setText(f"Low: {state.dhw_setpoints.low_temp:.1f}°F")
        
        self.eco_high.setValue(state.eco_setpoints.high_temp)
        self.eco_delta.setValue(state.eco_setpoints.delta_t)
        
        self.eco_start.setTime(QTime.fromString(state.eco_start, "HH:mm"))
        self.eco_end.setTime(QTime.fromString(state.eco_end, "HH:mm"))
        
        # Unblock signals
        for widget in widgets:
            widget.blockSignals(False)


class MainWindow(QMainWindow):
    """Main application window - fullscreen kiosk mode"""
    
    def __init__(self, control: ControlLogic):
        super().__init__()
        self.control = control
        self._setup_ui()
        self._connect_signals()
        
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_display)
        self.update_timer.start(1000)
    
    def _setup_ui(self):
        self.setWindowTitle("Snowmelt Control System")
        self.setStyleSheet(StyleSheet.MAIN)
        
        # Fullscreen with no window decorations
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setFixedSize(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.move(0, 0)
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)
        
        self.tabs = QTabWidget()
        
        self.dashboard_tab = DashboardTab(self.control)
        self.equipment_tab = EquipmentTab(self.control)
        self.setpoints_tab = SetpointsTab(self.control)
        
        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.equipment_tab, "Equipment")
        self.tabs.addTab(self.setpoints_tab, "Setpoints")
        
        layout.addWidget(self.tabs)
    
    def _connect_signals(self):
        self.equipment_tab.mode_changed.connect(self._on_equipment_mode_changed)
        self.setpoints_tab.setpoint_changed.connect(self._on_setpoint_changed)
        self.setpoints_tab.system_toggled.connect(self._on_system_toggled)
        self.setpoints_tab.eco_schedule_changed.connect(self._on_eco_schedule_changed)
    
    def _on_equipment_mode_changed(self, equipment_id: str, mode: str):
        try:
            mode_enum = EquipmentMode(mode)
            self.control.set_equipment_mode(equipment_id, mode_enum)
        except Exception as e:
            logger.error(f"Error setting equipment mode: {e}")
    
    def _on_setpoint_changed(self, setpoint_type: str, high: float, delta: float):
        try:
            if setpoint_type == "glycol":
                self.control.set_glycol_setpoints(high, delta)
            elif setpoint_type == "dhw":
                self.control.set_dhw_setpoints(high, delta)
            elif setpoint_type == "eco":
                self.control.set_eco_setpoints(high, delta)
        except Exception as e:
            logger.error(f"Error setting setpoints: {e}")
    
    def _on_system_toggled(self, system: str, enabled: bool):
        try:
            if system == "snowmelt":
                self.control.set_snowmelt_enabled(enabled)
            elif system == "dhw":
                self.control.set_dhw_enabled(enabled)
            elif system == "eco":
                self.control.set_eco_enabled(enabled)
        except Exception as e:
            logger.error(f"Error toggling system: {e}")
    
    def _on_eco_schedule_changed(self, start: str, end: str):
        try:
            self.control.set_eco_schedule(start, end)
        except Exception as e:
            logger.error(f"Error setting eco schedule: {e}")
    
    def _update_display(self):
        try:
            state = self.control.get_state()
            relay_states = self.control.relays.get_all_states()
            
            self.dashboard_tab.update_display(state)
            self.equipment_tab.update_display(relay_states)
            
            if self.tabs.currentWidget() != self.setpoints_tab:
                self.setpoints_tab.update_display(state)
        except Exception as e:
            logger.error(f"Error updating display: {e}")
    
    def keyPressEvent(self, event):
        """Handle key press events - ESC to exit fullscreen"""
        if event.key() == Qt.Key_Escape:
            self.close()
        super().keyPressEvent(event)
    
    def closeEvent(self, event):
        self.update_timer.stop()
        event.accept()


def create_gui(control: ControlLogic) -> QApplication:
    """Create and return the GUI application"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # Set default font
    font = QFont("DejaVu Sans", 10)
    app.setFont(font)
    
    window = MainWindow(control)
    window.showFullScreen()
    
    return app, window
