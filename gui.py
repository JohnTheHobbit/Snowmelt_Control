"""
Snowmelt Control System - Touchscreen GUI
PyQt5-based interface for 7" Waveshare touchscreen (1024x600)
Optimized for fullscreen kiosk mode with touch-friendly controls
"""

import sys
import logging
import socket
import subprocess
from datetime import datetime
from typing import Dict, Optional, Callable

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QFrame, QTabWidget, QTabBar,
    QGroupBox, QDoubleSpinBox, QTimeEdit, QMessageBox,
    QButtonGroup, QSizePolicy, QSpacerItem, QStyleOptionTab, QStyle
)
from PyQt5.QtCore import Qt, QTimer, QTime, pyqtSignal, QSize
from PyQt5.QtGui import QFont, QPainter

from relays import EquipmentMode, RelayState
from control import ControlLogic, ControlState, SystemState

logger = logging.getLogger(__name__)

# Screen dimensions for Waveshare 7" (1024x600)
SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 600
TAB_COUNT = 3


class EqualTabBar(QTabBar):
    """Custom tab bar with equal-width tabs"""

    def tabSizeHint(self, index):
        # Calculate width: screen width minus margins, divided by tab count
        tab_width = (SCREEN_WIDTH - 12) // TAB_COUNT
        return QSize(tab_width, 45)


def get_local_ip() -> str:
    """Get the local IP address of the device"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "No Network"


def get_network_status() -> bool:
    """Check if network is available by verifying we have a valid local IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return not ip.startswith("127.")
    except OSError:
        return False


class StatusIndicator(QFrame):
    """Small status indicator with colored dot and label"""

    def __init__(self, label: str):
        super().__init__()
        self._connected = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        # Colored status dot
        self.dot = QLabel()
        self.dot.setFixedSize(12, 12)
        self._update_dot_style()

        # Label text
        self.label = QLabel(label)
        self.label.setStyleSheet("font-size: 11px; color: #adb5bd;")

        layout.addWidget(self.dot)
        layout.addWidget(self.label)

        self.setStyleSheet("background-color: transparent;")

    def _update_dot_style(self):
        color = "#51cf66" if self._connected else "#ff6b6b"
        self.dot.setStyleSheet(f"""
            background-color: {color};
            border-radius: 6px;
            min-width: 12px; max-width: 12px;
            min-height: 12px; max-height: 12px;
        """)

    def set_connected(self, connected: bool):
        if self._connected != connected:
            self._connected = connected
            self._update_dot_style()


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
            font-size: 13px;
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
            padding: 12px 0px;
            margin-right: 2px;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            font-size: 16px;
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
            font-size: 14px;
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
            font-size: 13px;
            font-weight: bold;
            min-height: 36px;
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
            font-size: 18px;
            font-weight: bold;
            min-height: 40px;
        }
        QDoubleSpinBox:focus, QTimeEdit:focus {
            border-color: #e94560;
        }
        QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
        QTimeEdit::up-button, QTimeEdit::down-button {
            width: 0px;
            height: 0px;
            border: none;
        }
        QLabel {
            font-size: 13px;
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
    
    @staticmethod
    def enable_button(enabled: bool) -> str:
        """Get style for system enable/disable buttons"""
        if enabled:
            return """
                QPushButton {
                    background-color: #51cf66;
                    color: #1a1a2e;
                    border: 2px solid #51cf66;
                    font-size: 14px;
                    font-weight: bold;
                    min-height: 40px;
                }
                QPushButton:hover {
                    background-color: #40c057;
                    border-color: #40c057;
                }
            """
        else:
            return """
                QPushButton {
                    background-color: #495057;
                    color: #adb5bd;
                    border: 2px solid #495057;
                    font-size: 14px;
                    font-weight: bold;
                    min-height: 40px;
                }
                QPushButton:hover {
                    background-color: #5a6268;
                    border-color: #5a6268;
                }
            """


class TemperatureDisplay(QFrame):
    """Custom widget for displaying temperature with label"""
    
    def __init__(self, label: str, unit: str = "°F"):
        super().__init__()
        self.unit = unit
        self._value: Optional[float] = None
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        
        self.label = QLabel(label)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("font-size: 12px; color: #adb5bd;")
        
        self.value_label = QLabel("--")
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setStyleSheet("font-size: 26px; font-weight: bold; color: #74c0fc;")
        
        layout.addWidget(self.label)
        layout.addWidget(self.value_label)
        
        self.setStyleSheet("""
            QFrame {
                background-color: #16213e;
                border: 2px solid #3d3d5c;
                border-radius: 8px;
            }
        """)
    
    def set_value(self, value: Optional[float], style: str = None):
        """Update the displayed value"""
        self._value = value
        if value is not None:
            self.value_label.setText(f"{value:.1f}{self.unit}")
        else:
            self.value_label.setText("--")
        if style:
            self.value_label.setStyleSheet(f"font-size: 26px; {style}")


class SystemEnableButton(QPushButton):
    """Toggle button for enabling/disabling systems"""
    
    toggled_state = pyqtSignal(str, bool)
    
    def __init__(self, system_id: str, label: str):
        super().__init__(label)
        self.system_id = system_id
        self._enabled = False
        self.setStyleSheet(StyleSheet.enable_button(False))
        self.clicked.connect(self._on_clicked)
    
    def _on_clicked(self):
        self._enabled = not self._enabled
        self.setStyleSheet(StyleSheet.enable_button(self._enabled))
        self.toggled_state.emit(self.system_id, self._enabled)
    
    def set_state(self, enabled: bool):
        """Set the button state without emitting signal"""
        if self._enabled != enabled:
            self._enabled = enabled
            self.setStyleSheet(StyleSheet.enable_button(self._enabled))


class TouchSpinBox(QFrame):
    """Touch-friendly spinbox with large +/- buttons"""
    
    valueChanged = pyqtSignal(float)
    
    def __init__(self, min_val: float, max_val: float, suffix: str = "", step: float = 1.0):
        super().__init__()
        self.min_val = min_val
        self.max_val = max_val
        self.suffix = suffix
        self.step = step
        self._value = min_val
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # Decrement button
        self.btn_minus = QPushButton("−")
        self.btn_minus.setFixedSize(50, 50)
        self.btn_minus.setStyleSheet("""
            QPushButton {
                background-color: #0f3460;
                color: #eaeaea;
                border: 2px solid #3d3d5c;
                border-radius: 8px;
                font-size: 24px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1a5276;
                border-color: #e94560;
            }
            QPushButton:pressed {
                background-color: #e94560;
            }
        """)
        self.btn_minus.clicked.connect(self._decrement)
        
        # Value display
        self.value_label = QLabel()
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setStyleSheet("""
            font-size: 20px;
            font-weight: bold;
            color: #eaeaea;
            background-color: #16213e;
            border: 2px solid #3d3d5c;
            border-radius: 6px;
            padding: 8px;
            min-width: 100px;
        """)
        self._update_display()
        
        # Increment button
        self.btn_plus = QPushButton("+")
        self.btn_plus.setFixedSize(50, 50)
        self.btn_plus.setStyleSheet("""
            QPushButton {
                background-color: #0f3460;
                color: #eaeaea;
                border: 2px solid #3d3d5c;
                border-radius: 8px;
                font-size: 24px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1a5276;
                border-color: #e94560;
            }
            QPushButton:pressed {
                background-color: #e94560;
            }
        """)
        self.btn_plus.clicked.connect(self._increment)
        
        layout.addWidget(self.btn_minus)
        layout.addWidget(self.value_label, 1)
        layout.addWidget(self.btn_plus)
        
        self.setStyleSheet("background-color: transparent;")
    
    def _increment(self):
        new_val = min(self._value + self.step, self.max_val)
        if new_val != self._value:
            self._value = new_val
            self._update_display()
            self.valueChanged.emit(self._value)
    
    def _decrement(self):
        new_val = max(self._value - self.step, self.min_val)
        if new_val != self._value:
            self._value = new_val
            self._update_display()
            self.valueChanged.emit(self._value)
    
    def _update_display(self):
        self.value_label.setText(f"{self._value:.1f}{self.suffix}")
    
    def value(self) -> float:
        return self._value
    
    def setValue(self, val: float):
        self._value = max(self.min_val, min(val, self.max_val))
        self._update_display()
    
    def blockSignals(self, block: bool):
        super().blockSignals(block)


class TouchTimeEdit(QFrame):
    """Touch-friendly time editor with large +/- buttons"""
    
    timeChanged = pyqtSignal(QTime)
    
    def __init__(self):
        super().__init__()
        self._time = QTime(0, 0)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # Decrement button
        self.btn_minus = QPushButton("−")
        self.btn_minus.setFixedSize(50, 50)
        self.btn_minus.setStyleSheet("""
            QPushButton {
                background-color: #0f3460;
                color: #eaeaea;
                border: 2px solid #3d3d5c;
                border-radius: 8px;
                font-size: 24px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1a5276; border-color: #e94560; }
            QPushButton:pressed { background-color: #e94560; }
        """)
        self.btn_minus.clicked.connect(self._decrement)
        
        # Value display
        self.value_label = QLabel()
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setStyleSheet("""
            font-size: 20px;
            font-weight: bold;
            color: #eaeaea;
            background-color: #16213e;
            border: 2px solid #3d3d5c;
            border-radius: 6px;
            padding: 8px;
            min-width: 80px;
        """)
        self._update_display()
        
        # Increment button
        self.btn_plus = QPushButton("+")
        self.btn_plus.setFixedSize(50, 50)
        self.btn_plus.setStyleSheet("""
            QPushButton {
                background-color: #0f3460;
                color: #eaeaea;
                border: 2px solid #3d3d5c;
                border-radius: 8px;
                font-size: 24px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1a5276; border-color: #e94560; }
            QPushButton:pressed { background-color: #e94560; }
        """)
        self.btn_plus.clicked.connect(self._increment)
        
        layout.addWidget(self.btn_minus)
        layout.addWidget(self.value_label, 1)
        layout.addWidget(self.btn_plus)
        
        self.setStyleSheet("background-color: transparent;")
    
    def _increment(self):
        self._time = self._time.addSecs(30 * 60)  # Add 30 minutes
        self._update_display()
        self.timeChanged.emit(self._time)
    
    def _decrement(self):
        self._time = self._time.addSecs(-30 * 60)  # Subtract 30 minutes
        self._update_display()
        self.timeChanged.emit(self._time)
    
    def _update_display(self):
        self.value_label.setText(self._time.toString("HH:mm"))
    
    def time(self) -> QTime:
        return self._time
    
    def setTime(self, time: QTime):
        self._time = time
        self._update_display()
    
    def blockSignals(self, block: bool):
        super().blockSignals(block)


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
        
        # Name label
        name_label = QLabel(name)
        name_label.setStyleSheet("font-size: 14px; font-weight: bold;")
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
            btn.setFixedSize(70, 40)
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
        self.setFixedHeight(55)
    
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
    """Main dashboard showing system overview with enable buttons"""
    
    system_toggled = pyqtSignal(str, bool)
    
    def __init__(self, control: ControlLogic):
        super().__init__()
        self.control = control
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)
        
        # Top section: System enable buttons and status
        top_layout = QHBoxLayout()
        top_layout.setSpacing(12)
        
        # System enable buttons
        enable_group = QGroupBox("System Control")
        enable_layout = QHBoxLayout(enable_group)
        enable_layout.setSpacing(10)
        
        self.btn_snowmelt = SystemEnableButton("snowmelt", "Snowmelt")
        self.btn_dhw = SystemEnableButton("dhw", "DHW")
        self.btn_eco = SystemEnableButton("eco", "Eco Mode")
        
        for btn in [self.btn_snowmelt, self.btn_dhw, self.btn_eco]:
            btn.setFixedHeight(45)
            btn.toggled_state.connect(self._on_system_toggled)
            enable_layout.addWidget(btn)
        
        # Status indicators
        status_group = QGroupBox("Status")
        status_layout = QHBoxLayout(status_group)
        status_layout.setSpacing(15)
        
        self.snowmelt_status = QLabel("IDLE")
        self.snowmelt_status.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.dhw_status = QLabel("IDLE")
        self.dhw_status.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.eco_status = QLabel("OFF")
        self.eco_status.setStyleSheet("font-size: 14px; font-weight: bold;")
        
        status_layout.addWidget(QLabel("Snowmelt:"))
        status_layout.addWidget(self.snowmelt_status)
        status_layout.addWidget(QLabel("DHW:"))
        status_layout.addWidget(self.dhw_status)
        status_layout.addWidget(QLabel("Eco:"))
        status_layout.addWidget(self.eco_status)
        
        top_layout.addWidget(enable_group, 2)
        top_layout.addWidget(status_group, 1)
        
        # Temperature section - grouped logically
        temp_layout = QHBoxLayout()
        temp_layout.setSpacing(8)
        
        # Glycol Loop group
        glycol_group = QGroupBox("Glycol Loop")
        glycol_layout = QHBoxLayout(glycol_group)
        glycol_layout.setSpacing(8)
        self.temp_glycol_supply = TemperatureDisplay("Supply")
        self.temp_glycol_return = TemperatureDisplay("Return")
        glycol_layout.addWidget(self.temp_glycol_supply)
        glycol_layout.addWidget(self.temp_glycol_return)
        
        # Heat Exchanger group
        hx_group = QGroupBox("Heat Exchanger")
        hx_layout = QHBoxLayout(hx_group)
        hx_layout.setSpacing(8)
        self.temp_hx_in = TemperatureDisplay("In")
        self.temp_hx_out = TemperatureDisplay("Out")
        self.temp_hx_delta = TemperatureDisplay("ΔT")
        hx_layout.addWidget(self.temp_hx_in)
        hx_layout.addWidget(self.temp_hx_out)
        hx_layout.addWidget(self.temp_hx_delta)
        
        # DHW Tank group
        dhw_group = QGroupBox("DHW Tank")
        dhw_layout = QHBoxLayout(dhw_group)
        self.temp_dhw = TemperatureDisplay("Temperature")
        dhw_layout.addWidget(self.temp_dhw)
        
        temp_layout.addWidget(glycol_group, 2)
        temp_layout.addWidget(hx_group, 3)
        temp_layout.addWidget(dhw_group, 1)
        
        # Bottom bar with status indicators and time
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 4, 0, 0)
        bottom_layout.setSpacing(12)

        # Status indicators on the left
        self.mqtt_indicator = StatusIndicator("MQTT")
        self.net_indicator = StatusIndicator("NET")
        bottom_layout.addWidget(self.mqtt_indicator)
        bottom_layout.addWidget(self.net_indicator)
        bottom_layout.addStretch()

        # Time display on the right
        self.time_label = QLabel()
        self.time_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #e94560;")
        self.time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bottom_layout.addWidget(self.time_label)

        layout.addLayout(top_layout)
        layout.addLayout(temp_layout, 1)
        layout.addLayout(bottom_layout)
    
    def _on_system_toggled(self, system: str, enabled: bool):
        self.system_toggled.emit(system, enabled)
    
    def update_display(self, state: ControlState):
        colors = {
            SystemState.IDLE: "#adb5bd",
            SystemState.HEATING: "#51cf66",
            SystemState.BYPASS: "#74c0fc",
            SystemState.ERROR: "#ff6b6b"
        }
        
        # Update status labels
        color = colors.get(state.snowmelt_state, "#adb5bd")
        self.snowmelt_status.setText(state.snowmelt_state.value.upper())
        self.snowmelt_status.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {color};")
        
        color = colors.get(state.dhw_state, "#adb5bd")
        self.dhw_status.setText(state.dhw_state.value.upper())
        self.dhw_status.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {color};")
        
        eco_color = "#51cf66" if state.eco_active else "#adb5bd"
        self.eco_status.setText("ON" if state.eco_active else "OFF")
        self.eco_status.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {eco_color};")
        
        # Update enable buttons
        self.btn_snowmelt.set_state(state.snowmelt_enabled)
        self.btn_dhw.set_state(state.dhw_enabled)
        self.btn_eco.set_state(state.eco_enabled)
        
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

    def update_connectivity(self, mqtt_connected: bool, net_connected: bool):
        """Update the connectivity status indicators"""
        self.mqtt_indicator.set_connected(mqtt_connected)
        self.net_indicator.set_connected(net_connected)


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
        layout.setSpacing(8)
        
        # Snowmelt equipment group
        snowmelt_group = QGroupBox("Snowmelt System")
        snowmelt_layout = QVBoxLayout(snowmelt_group)
        snowmelt_layout.setContentsMargins(8, 8, 8, 8)
        snowmelt_layout.setSpacing(8)
        
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
        dhw_layout.setContentsMargins(8, 8, 8, 8)
        dhw_layout.setSpacing(8)
        
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
    """Settings tab with setpoints and system controls"""

    setpoint_changed = pyqtSignal(str, float, float)
    system_toggled = pyqtSignal(str, bool)
    eco_schedule_changed = pyqtSignal(str, str)
    shutdown_requested = pyqtSignal()
    
    def __init__(self, control: ControlLogic):
        super().__init__()
        self.control = control
        self._setup_ui()
    
    def _setup_ui(self):
        # Use grid layout: left column (Snowmelt, DHW, System stacked), right column (Eco Mode)
        layout = QGridLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # --- Left column: Snowmelt and DHW side by side, System below ---
        left_column = QVBoxLayout()
        left_column.setSpacing(8)

        # Top row: Snowmelt and DHW side by side
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        # Snowmelt group
        snowmelt_group = QGroupBox("Snowmelt")
        snowmelt_layout = QVBoxLayout(snowmelt_group)
        snowmelt_layout.setContentsMargins(8, 8, 8, 8)
        snowmelt_layout.setSpacing(6)

        self.btn_snowmelt = SystemEnableButton("snowmelt", "Enable Snowmelt")
        self.btn_snowmelt.toggled_state.connect(lambda s, e: self.system_toggled.emit(s, e))
        snowmelt_layout.addWidget(self.btn_snowmelt)

        # High setpoint
        high_row = QHBoxLayout()
        high_label = QLabel("High:")
        high_label.setFixedWidth(50)
        high_label.setStyleSheet("font-size: 14px;")
        self.glycol_high = TouchSpinBox(50, 90, " °F", 5.0)
        self.glycol_high.valueChanged.connect(self._on_glycol_changed)
        high_row.addWidget(high_label)
        high_row.addWidget(self.glycol_high)
        snowmelt_layout.addLayout(high_row)

        # Delta setpoint
        delta_row = QHBoxLayout()
        delta_label = QLabel("Delta:")
        delta_label.setFixedWidth(45)
        delta_label.setStyleSheet("font-size: 13px;")
        self.glycol_delta = TouchSpinBox(5, 30, " °F", 1.0)
        self.glycol_delta.valueChanged.connect(self._on_glycol_changed)
        delta_row.addWidget(delta_label)
        delta_row.addWidget(self.glycol_delta)
        snowmelt_layout.addLayout(delta_row)

        self.glycol_low_label = QLabel("Low: --")
        self.glycol_low_label.setStyleSheet("color: #adb5bd; font-size: 12px;")
        self.glycol_low_label.setAlignment(Qt.AlignCenter)
        snowmelt_layout.addWidget(self.glycol_low_label)

        top_row.addWidget(snowmelt_group)

        # DHW group
        dhw_group = QGroupBox("DHW")
        dhw_layout = QVBoxLayout(dhw_group)
        dhw_layout.setContentsMargins(8, 8, 8, 8)
        dhw_layout.setSpacing(6)

        self.btn_dhw = SystemEnableButton("dhw", "Enable DHW")
        self.btn_dhw.toggled_state.connect(lambda s, e: self.system_toggled.emit(s, e))
        dhw_layout.addWidget(self.btn_dhw)

        # High setpoint
        high_row = QHBoxLayout()
        high_label = QLabel("High:")
        high_label.setFixedWidth(50)
        high_label.setStyleSheet("font-size: 14px;")
        self.dhw_high = TouchSpinBox(100, 130, " °F", 5.0)
        self.dhw_high.valueChanged.connect(self._on_dhw_changed)
        high_row.addWidget(high_label)
        high_row.addWidget(self.dhw_high)
        dhw_layout.addLayout(high_row)

        # Delta setpoint
        delta_row = QHBoxLayout()
        delta_label = QLabel("Delta:")
        delta_label.setFixedWidth(45)
        delta_label.setStyleSheet("font-size: 13px;")
        self.dhw_delta = TouchSpinBox(5, 20, " °F", 1.0)
        self.dhw_delta.valueChanged.connect(self._on_dhw_changed)
        delta_row.addWidget(delta_label)
        delta_row.addWidget(self.dhw_delta)
        dhw_layout.addLayout(delta_row)

        self.dhw_low_label = QLabel("Low: --")
        self.dhw_low_label.setStyleSheet("color: #adb5bd; font-size: 12px;")
        self.dhw_low_label.setAlignment(Qt.AlignCenter)
        dhw_layout.addWidget(self.dhw_low_label)

        top_row.addWidget(dhw_group)

        left_column.addLayout(top_row)

        # System group (below Snowmelt and DHW)
        system_group = QGroupBox("System")
        system_layout = QHBoxLayout(system_group)
        system_layout.setContentsMargins(8, 8, 8, 8)
        system_layout.setSpacing(10)

        # Shutdown button - prominent red styling
        self.btn_shutdown = QPushButton("Shutdown RPi")
        self.btn_shutdown.setStyleSheet("""
            QPushButton {
                background-color: #c0392b;
                color: #ffffff;
                border: 2px solid #a93226;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                min-height: 45px;
                padding: 8px 20px;
            }
            QPushButton:hover {
                background-color: #e74c3c;
                border-color: #c0392b;
            }
            QPushButton:pressed {
                background-color: #922b21;
            }
        """)
        self.btn_shutdown.clicked.connect(self._on_shutdown_clicked)
        system_layout.addWidget(self.btn_shutdown)

        # Read-only info style
        readonly_style = """
            background-color: #16213e;
            border: 1px solid #3d3d5c;
            border-radius: 4px;
            padding: 4px 8px;
            color: #adb5bd;
            font-size: 12px;
        """

        # MQTT Host field
        mqtt_frame = QFrame()
        mqtt_frame.setStyleSheet("background-color: transparent;")
        mqtt_layout_inner = QHBoxLayout(mqtt_frame)
        mqtt_layout_inner.setContentsMargins(0, 0, 0, 0)
        mqtt_layout_inner.setSpacing(6)
        mqtt_label = QLabel("MQTT:")
        mqtt_label.setStyleSheet("font-size: 12px; color: #adb5bd;")
        self.mqtt_host_value = QLabel("--")
        self.mqtt_host_value.setStyleSheet(readonly_style)
        mqtt_layout_inner.addWidget(mqtt_label)
        mqtt_layout_inner.addWidget(self.mqtt_host_value)
        system_layout.addWidget(mqtt_frame)

        # RPi IP field
        ip_frame = QFrame()
        ip_frame.setStyleSheet("background-color: transparent;")
        ip_layout_inner = QHBoxLayout(ip_frame)
        ip_layout_inner.setContentsMargins(0, 0, 0, 0)
        ip_layout_inner.setSpacing(6)
        ip_label = QLabel("IP:")
        ip_label.setStyleSheet("font-size: 12px; color: #adb5bd;")
        self.rpi_ip_value = QLabel(get_local_ip())
        self.rpi_ip_value.setStyleSheet(readonly_style)
        ip_layout_inner.addWidget(ip_label)
        ip_layout_inner.addWidget(self.rpi_ip_value)
        system_layout.addWidget(ip_frame)

        system_layout.addStretch()

        left_column.addWidget(system_group)

        # --- Right column: Eco Mode ---
        eco_group = QGroupBox("Eco Mode")
        eco_layout = QVBoxLayout(eco_group)
        eco_layout.setContentsMargins(8, 8, 8, 8)
        eco_layout.setSpacing(6)

        self.btn_eco = SystemEnableButton("eco", "Enable Eco Mode")
        self.btn_eco.toggled_state.connect(lambda s, e: self.system_toggled.emit(s, e))
        eco_layout.addWidget(self.btn_eco)

        # High setpoint
        high_row = QHBoxLayout()
        high_label = QLabel("High:")
        high_label.setFixedWidth(45)
        high_label.setStyleSheet("font-size: 13px;")
        self.eco_high = TouchSpinBox(100, 130, " °F", 1.0)
        self.eco_high.valueChanged.connect(self._on_eco_changed)
        high_row.addWidget(high_label)
        high_row.addWidget(self.eco_high)
        eco_layout.addLayout(high_row)

        # Delta setpoint
        delta_row = QHBoxLayout()
        delta_label = QLabel("Delta:")
        delta_label.setFixedWidth(45)
        delta_label.setStyleSheet("font-size: 13px;")
        self.eco_delta = TouchSpinBox(5, 25, " °F", 1.0)
        self.eco_delta.valueChanged.connect(self._on_eco_changed)
        delta_row.addWidget(delta_label)
        delta_row.addWidget(self.eco_delta)
        eco_layout.addLayout(delta_row)

        # Start time
        start_row = QHBoxLayout()
        start_label = QLabel("Start:")
        start_label.setFixedWidth(45)
        start_label.setStyleSheet("font-size: 13px;")
        self.eco_start = TouchTimeEdit()
        self.eco_start.timeChanged.connect(self._on_eco_schedule_changed)
        start_row.addWidget(start_label)
        start_row.addWidget(self.eco_start)
        eco_layout.addLayout(start_row)

        # End time
        end_row = QHBoxLayout()
        end_label = QLabel("End:")
        end_label.setFixedWidth(45)
        end_label.setStyleSheet("font-size: 13px;")
        self.eco_end = TouchTimeEdit()
        self.eco_end.timeChanged.connect(self._on_eco_schedule_changed)
        end_row.addWidget(end_label)
        end_row.addWidget(self.eco_end)
        eco_layout.addLayout(end_row)

        eco_layout.addStretch()

        # Add to grid: left column spans rows, eco on right
        layout.addLayout(left_column, 0, 0)
        layout.addWidget(eco_group, 0, 1)
        layout.setColumnStretch(0, 2)  # Left column gets more space
        layout.setColumnStretch(1, 1)  # Eco column

    def _on_shutdown_clicked(self):
        """Emit shutdown request signal"""
        self.shutdown_requested.emit()

    def _on_glycol_changed(self):
        high = self.glycol_high.value()
        delta = self.glycol_delta.value()
        low = high - delta
        self.glycol_low_label.setText(f"Low: {low:.1f} °F")
        self.setpoint_changed.emit("glycol", high, delta)
    
    def _on_dhw_changed(self):
        high = self.dhw_high.value()
        delta = self.dhw_delta.value()
        low = high - delta
        self.dhw_low_label.setText(f"Low: {low:.1f} °F")
        self.setpoint_changed.emit("dhw", high, delta)
    
    def _on_eco_changed(self):
        self.setpoint_changed.emit("eco", self.eco_high.value(), self.eco_delta.value())
    
    def _on_eco_schedule_changed(self):
        start = self.eco_start.time().toString("HH:mm")
        end = self.eco_end.time().toString("HH:mm")
        self.eco_schedule_changed.emit(start, end)
    
    def update_display(self, state: ControlState):
        # Block signals to avoid feedback loops
        widgets = [self.glycol_high, self.glycol_delta, self.dhw_high, self.dhw_delta,
                   self.eco_high, self.eco_delta, self.eco_start, self.eco_end]
        for widget in widgets:
            widget.blockSignals(True)
        
        self.btn_snowmelt.set_state(state.snowmelt_enabled)
        self.btn_dhw.set_state(state.dhw_enabled)
        self.btn_eco.set_state(state.eco_enabled)
        
        self.glycol_high.setValue(state.glycol_setpoints.high_temp)
        self.glycol_delta.setValue(state.glycol_setpoints.delta_t)
        self.glycol_low_label.setText(f"Low: {state.glycol_setpoints.low_temp:.1f} °F")
        
        self.dhw_high.setValue(state.dhw_setpoints.high_temp)
        self.dhw_delta.setValue(state.dhw_setpoints.delta_t)
        self.dhw_low_label.setText(f"Low: {state.dhw_setpoints.low_temp:.1f} °F")
        
        self.eco_high.setValue(state.eco_setpoints.high_temp)
        self.eco_delta.setValue(state.eco_setpoints.delta_t)
        
        self.eco_start.setTime(QTime.fromString(state.eco_start, "HH:mm"))
        self.eco_end.setTime(QTime.fromString(state.eco_end, "HH:mm"))
        
        # Unblock signals
        for widget in widgets:
            widget.blockSignals(False)

    def set_mqtt_host(self, host: str):
        """Set the MQTT host display value"""
        self.mqtt_host_value.setText(host)

    def update_ip_address(self):
        """Update the RPi IP address display"""
        self.rpi_ip_value.setText(get_local_ip())


class MainWindow(QMainWindow):
    """Main application window - fullscreen kiosk mode"""

    def __init__(self, control: ControlLogic):
        super().__init__()
        self.control = control
        self._mqtt_integration = None  # Optional MQTT integration reference
        self._updating = False  # Flag to prevent overlapping updates
        self._setup_ui()
        self._connect_signals()

        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_display)
        self.update_timer.start(500)  # Faster updates (500ms) since reads are now non-blocking

    def set_mqtt_integration(self, mqtt_integration):
        """Set the MQTT integration reference for status monitoring"""
        self._mqtt_integration = mqtt_integration
        if mqtt_integration:
            self.setpoints_tab.set_mqtt_host(mqtt_integration.broker)
    
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
        
        # Create tab widget with equal-width tabs
        self.tabs = QTabWidget()
        self.tabs.setTabBar(EqualTabBar())
        
        self.dashboard_tab = DashboardTab(self.control)
        self.equipment_tab = EquipmentTab(self.control)
        self.setpoints_tab = SetpointsTab(self.control)
        
        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.equipment_tab, "Equipment")
        self.tabs.addTab(self.setpoints_tab, "Settings")
        
        layout.addWidget(self.tabs)
    
    def _connect_signals(self):
        self.equipment_tab.mode_changed.connect(self._on_equipment_mode_changed)
        self.setpoints_tab.setpoint_changed.connect(self._on_setpoint_changed)
        self.setpoints_tab.system_toggled.connect(self._on_system_toggled)
        self.setpoints_tab.eco_schedule_changed.connect(self._on_eco_schedule_changed)
        self.setpoints_tab.shutdown_requested.connect(self._on_shutdown_requested)
        self.dashboard_tab.system_toggled.connect(self._on_system_toggled)
    
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

    def _on_shutdown_requested(self):
        """Handle shutdown request with confirmation dialog"""
        msg = QMessageBox(self)
        msg.setWindowTitle("Confirm Shutdown")
        msg.setText("Are you sure you want to shutdown the Raspberry Pi?")
        msg.setInformativeText("The system will power off and need to be manually restarted.")
        msg.setIcon(QMessageBox.Warning)
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        msg.setDefaultButton(QMessageBox.Cancel)

        # Style the dialog for touchscreen
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #1a1a2e;
            }
            QMessageBox QLabel {
                color: #eaeaea;
                font-size: 14px;
            }
            QPushButton {
                min-width: 80px;
                min-height: 40px;
                font-size: 14px;
            }
        """)

        if msg.exec_() == QMessageBox.Yes:
            logger.info("Shutdown requested by user - initiating system shutdown")
            try:
                subprocess.run(['sudo', 'shutdown', '-h', 'now'], check=True)
            except Exception as e:
                logger.error(f"Failed to initiate shutdown: {e}")
                error_msg = QMessageBox(self)
                error_msg.setWindowTitle("Shutdown Failed")
                error_msg.setText(f"Failed to shutdown: {e}")
                error_msg.setIcon(QMessageBox.Critical)
                error_msg.exec_()

    def _update_display(self):
        # Skip if already updating (prevents queue buildup)
        if self._updating:
            return

        self._updating = True
        try:
            state = self.control.get_state()
            relay_states = self.control.relays.get_all_states()

            self.dashboard_tab.update_display(state)
            self.equipment_tab.update_display(relay_states)

            if self.tabs.currentWidget() != self.setpoints_tab:
                self.setpoints_tab.update_display(state)

            # Update connectivity status indicators
            net_connected = get_network_status()
            mqtt_connected = self._mqtt_integration._connected if self._mqtt_integration else False
            self.dashboard_tab.update_connectivity(mqtt_connected, net_connected)

            # Update IP address in settings (in case it changed)
            self.setpoints_tab.update_ip_address()
        except Exception as e:
            logger.error(f"Error updating display: {e}")
        finally:
            self._updating = False
    
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
    font = QFont("DejaVu Sans", 11)
    app.setFont(font)
    
    window = MainWindow(control)
    window.showFullScreen()
    
    return app, window
