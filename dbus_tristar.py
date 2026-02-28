#!/usr/bin/env python3

"""
Morningstar TriStar MPPT driver for Venus OS
Reads charge controller data via Modbus TCP and publishes to D-Bus

Uses SettingsDevice for configuration via D-Bus
Configure via: dbus -y com.victronenergy.settings /Settings/TristarMPPT/...
"""

import logging
import sys
import signal
import dbus
import dbus.mainloop.glib
from gi.repository import GLib
from time import time, sleep
from datetime import datetime, time as dt_time, timezone, timedelta
import json
from pathlib import Path

# pymodbus v2.x (Venus OS) vs v3.x compatibility
try:
    from pymodbus.client import ModbusTcpClient
except ImportError:
    from pymodbus.client.sync import ModbusTcpClient

# Import Victron packages
sys.path.insert(1, '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python')
from vedbus import VeDbusService
from settingsdevice import SettingsDevice

VERSION = "2.2"  # WAN-optimized with watchdog, backoff, validation, and diagnostics
PRODUCT_ID = 0xABCD  # Placeholder - can be registered with Victron

# Persistent state file for yield tracking and 30-day history
STATE_FILE = Path("/data/dbus-tristar/state.json")

# Modbus register addresses (input registers)
REG_V_PU = 0           # Voltage scaling
REG_I_PU = 2           # Current scaling
REG_VER_SW = 4         # Software version
REG_V_BAT = 24         # Battery voltage
REG_I_CC = 28          # Charge current
REG_V_PV = 27          # PV array voltage
REG_I_PV = 29          # PV array current
REG_T_BAT = 37         # Battery temperature
REG_I_CC_1M = 39       # Charge current (1 min avg)
REG_CHARGE_STATE = 50  # Charge state
REG_V_TARGET = 51      # Target regulation voltage
REG_KWH_TOTAL_RES = 56 # kWh total resettable
REG_KWH_TOTAL = 57     # kWh total
REG_POUT = 58          # Output power
REG_V_BAT_MIN = 64     # Min battery voltage (daily)
REG_V_BAT_MAX = 65     # Max battery voltage (daily)
REG_V_PV_MAX = 66      # Max PV voltage (daily)
REG_WHC_DAILY = 68     # Wh daily
REG_POUT_MAX_DAILY = 70 # Max power (daily)
REG_T_ABS = 77         # Time in absorption
REG_T_FLOAT = 79       # Time in float
REG_EHW_VERSION = 57549 # Hardware version
REG_ESERIAL = 57536    # Serial number (4 registers)
REG_EMODEL = 57548     # Model number

# Additional diagnostic registers (already in batch read 24-79)
REG_V_BAT_TERM = 25      # Battery terminal voltage
REG_V_BAT_SENSE = 26     # Battery sense voltage
REG_I_CC_FAST = 28       # Charge current (fast/immediate) - Note: REG_I_CC already defined as 28
REG_12V_SUPPLY = 31      # Internal 12V supply (CORRECTED: was 30, which is solar input current!)
REG_3V_SUPPLY = 32       # Internal 3V supply (CORRECTED: was 31)
REG_METERBUS_V = 33      # MeterBus voltage (CORRECTED: was 32)
REG_1V8_SUPPLY = 34      # Internal 1.8V supply (CORRECTED: was 33)
REG_VREF = 34            # Reference voltage (spec: [35][0x0022] = address 34)
REG_T_HS = 35            # Heatsink temperature (spec: [36][0x0023] = address 35)
REG_T_RTS = 36           # RTS temperature
REG_V_BAT_SLOW = 38      # Battery voltage (slow filtered)
REG_V_BAT_MIN_ALL = 64   # Min battery voltage (overall) (CORRECTED: was 40!)
REG_V_BAT_MAX_ALL = 65   # Max battery voltage (overall) (CORRECTED: was 41!)
REG_FAULTS = 44          # Faults bitfield
REG_DIP_SWITCHES = 48    # DIP switches bitfield
REG_LED_STATE = 49       # LED state
REG_P_IN_SHADOW = 59     # PV input power shadow
REG_SWEEP_PMAX = 60      # Last sweep Pmax
REG_SWEEP_VMP = 61       # Last sweep Vmp
REG_SWEEP_VOC = 62       # Last sweep Voc
REG_AHC_DAILY = 67       # Daily Ah charged
REG_FLAGS_DAILY = 69     # Daily flags bitfield
REG_T_BAT_MIN_DAILY = 71 # Daily min battery temp
REG_T_BAT_MAX_DAILY = 72 # Daily max battery temp
REG_FAULTS_DAILY = 73    # Daily faults bitfield
REG_T_EQ_DAILY = 78      # Time in equalize today

# Modbus coils (read/write)
COIL_EQUALIZE = 0          # Equalize triggered
COIL_DISCONNECT = 2        # Charger disconnect
COIL_RESET_CTRL = 255      # Reset controller (momentary, only when dark!)
COIL_RESET_COMM = 4351     # Reset comm server (momentary)

# Charge states
CS_NIGHT = 3
CS_BULK = 5

# TriStar to Victron charge state mapping
CHARGE_STATE_MAP = {
    0: 0,   # START -> OFF
    1: 0,   # NIGHT_CHECK -> OFF
    2: 0,   # DISCONNECT -> OFF
    3: 0,   # NIGHT -> OFF
    4: 2,   # FAULT -> FAULT
    5: 3,   # MPPT -> BULK
    6: 4,   # ABSORPTION -> ABSORPTION
    7: 5,   # FLOAT -> FLOAT
    8: 7,   # EQUALIZE -> EQUALIZE
    9: 11   # SLAVE -> OTHER
}

# TriStar charge state text (raw TriStar values)
CHARGE_STATE_TEXT = {
    0: "START",
    1: "NIGHT_CHECK",
    2: "DISCONNECT",
    3: "NIGHT",
    4: "FAULT",
    5: "MPPT",
    6: "ABSORPTION",
    7: "FLOAT",
    8: "EQUALIZE",
    9: "SLAVE"
}

# Fault bitfield definitions (REG_FAULTS = 44, REG_FAULTS_DAILY = 73)
FAULT_BITS = {
    0: "Overcurrent",
    1: "FETsShorted",
    2: "SoftwareBug",
    3: "BatteryHVD",
    4: "ArrayHVD",
    5: "SettingsSwitchChanged",
    6: "CustomSettingsEdit",
    7: "RTsShorted",
    8: "RTsDisconnected",
    9: "EEPROMRetryLimit",
    10: "Reserved",
    11: "SlaveControlTimeout",
    12: "Fault12",
    13: "Fault13",
    14: "Fault14",
    15: "Fault15"
}

# Daily flags bitfield definitions (REG_FLAGS_DAILY = 69)
FLAGS_DAILY_BITS = {
    0: "ResetDetected",
    1: "EqualizeTriggered",
    2: "EnteredFloat",
    3: "AlarmOccurred",
    4: "FaultOccurred"
}


class TriStarDriver:
    """Main driver class for TriStar MPPT"""

    def __init__(self):
        self.bus = dbus.SystemBus()

        # Settings using Venus OS SettingsDevice (array format)
        # Format: [path, default, min, max]
        # Note: Interval is in milliseconds per Victron convention
        self.settings = SettingsDevice(
            bus=self.bus,
            supportedSettings={
                'ip_address': ['/Settings/TristarMPPT/IPAddress', '192.168.2.103', 0, 0],
                'modbus_port': ['/Settings/TristarMPPT/PortNumber', 502, 1, 65535],
                'poll_interval': ['/Settings/TristarMPPT/Interval', 5000, 1000, 60000],
                'slave_id': ['/Settings/TristarMPPT/SlaveID', 1, 1, 247],
                'device_instance': ['/Settings/TristarMPPT/DeviceInstance', 0, 0, 255],
            },
            eventCallback=self._setting_changed
        )

        # Device state
        self.initialized = False

        # Scaling factors (read from device)
        self.v_pu = 0.0
        self.i_pu = 0.0

        # Static device info
        self.firmware_version = 0
        self.hardware_version = ""
        self.serial_number = ""
        self.product_name = ""

        # Bulk charge timing
        self.t_bulk_ms = 0
        self.last_update = time()

        # Connection watchdog (track last successful read)
        self.last_successful_read = time()
        self.watchdog_timeout = 180  # 3 minutes - mark as disconnected if no successful reads

        # Statistics for diagnostics
        self.successful_reads = 0
        self.failed_reads = 0
        self.consecutive_failures = 0

        # Exponential backoff on persistent failures
        self.backoff_factor = 1  # Multiplier for poll interval (1x, 2x, 4x)

        # Load persistent state (total yield and 30-day history)
        self.state = self._load_state()

        # Daily value trackers (reset at midnight)
        self.daily_max_battery_current = 0.0
        self.daily_max_power = 0.0
        self.daily_max_battery_voltage = 0.0
        self.daily_min_battery_voltage = 999.0  # Will be updated to actual value
        self.daily_max_pv_voltage = 0.0

        # Nightly reset tracking
        self.last_reset_date = self.state.get('current_date')

        # Daily register reset detection (for post-midnight, pre-sunrise handling)
        self.daily_register_has_reset = False  # Reset when new day starts
        self.last_daily_register_value = 0

        # Track which history days have D-Bus paths created (for dynamic path creation)
        self.history_days_created = set()  # Set of day indices (1-29) that have paths

        # Note: State will be saved on first update (initialization) or at midnight rollover
        # No need to save here - we haven't changed anything yet!

        # Timer management
        self.timer_id = None

        # D-Bus service (use configurable device instance)
        instance = int(self.settings['device_instance'])
        service_name = f'com.victronenergy.solarcharger.tristar_{instance}'
        self.dbus = VeDbusService(service_name, register=False)
        self._setup_dbus_paths()
        self.dbus.register()

        # Start periodic updates
        self._start_timer()

        logging.info("TriStar MPPT driver initialized")
        logging.info(f"Settings: {self.settings['ip_address']}:{self.settings['modbus_port']}")

    def _load_state(self):
        """Load persistent state from JSON file"""
        try:
            if STATE_FILE.exists():
                with open(STATE_FILE, 'r') as f:
                    state = json.load(f)

                # Validate version
                if state.get('version') != 1:
                    logging.warning(f"State file version mismatch, starting fresh")
                    return self._create_fresh_state()

                logging.info(f"Loaded state: {len(state.get('history', []))} days of history")
                return state
            else:
                logging.info("No state file found, creating fresh state")
                return self._create_fresh_state()

        except Exception as e:
            logging.error(f"Error loading state file: {e}, starting fresh")
            return self._create_fresh_state()

    def _create_fresh_state(self):
        """Create fresh state structure"""
        return {
            "version": 1,
            "total_yield_kwh": 0.0,
            "last_update": datetime.utcnow().isoformat() + "Z",
            "current_date": self._get_local_date(),
            "history": []  # Will grow to 30 days
        }

    def _save_state(self):
        """Save state to JSON file atomically"""
        try:
            # Create directory if needed
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

            # Update timestamp
            self.state['last_update'] = datetime.utcnow().isoformat() + "Z"

            # Write atomically (temp file + rename)
            temp_file = STATE_FILE.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(self.state, f, indent=2)
            temp_file.replace(STATE_FILE)

            logging.debug("State saved successfully")

        except Exception as e:
            logging.error(f"Error saving state: {e}")

    def _get_local_date(self):
        """Get current date in local timezone (system time)"""
        try:
            # Use system local time (respects Venus OS timezone setting)
            return datetime.now().date().isoformat()

        except Exception as e:
            logging.error(f"Error getting local date: {e}")
            return datetime.now().date().isoformat()

    def _update_historical_days(self):
        """Update D-Bus paths for days 1-29 from state file (create paths dynamically)"""
        try:
            history = self.state.get('history', [])

            # Update DaysAvailable: number of historical days + today (day 0)
            days_available = min(len(history) + 1, 30)  # Max 30 days
            self.dbus['/History/Overall/DaysAvailable'] = days_available

            # Only create paths for days that have actual data (days 1-29)
            # This prevents Venus OS from thinking we have 30 days when we only have 1
            for history_index in range(len(history)):
                day_index = history_index + 1  # history[0] = day 1 (yesterday)

                if day_index > 29:
                    break  # Only support up to 29 historical days

                # Create D-Bus paths for this day if not already created
                if day_index not in self.history_days_created:
                    logging.info(f"Creating D-Bus paths for history day {day_index}")
                    self.dbus.add_path(f'/History/Daily/{day_index}/Yield', None, gettextcallback=lambda p, v: f"{v}kWh")
                    self.dbus.add_path(f'/History/Daily/{day_index}/MaxPower', None, gettextcallback=lambda p, v: f"{v}W")
                    self.dbus.add_path(f'/History/Daily/{day_index}/MaxPvVoltage', None, gettextcallback=lambda p, v: f"{v}V")
                    self.dbus.add_path(f'/History/Daily/{day_index}/MaxBatteryVoltage', None, gettextcallback=lambda p, v: f"{v}V")
                    self.dbus.add_path(f'/History/Daily/{day_index}/MinBatteryVoltage', None, gettextcallback=lambda p, v: f"{v}V")
                    self.dbus.add_path(f'/History/Daily/{day_index}/MaxBatteryCurrent', None, gettextcallback=lambda p, v: f"{v}A")
                    self.dbus.add_path(f'/History/Daily/{day_index}/TimeInBulk', None)
                    self.dbus.add_path(f'/History/Daily/{day_index}/TimeInAbsorption', None)
                    self.dbus.add_path(f'/History/Daily/{day_index}/TimeInFloat', None)
                    self.dbus.add_path(f'/History/Daily/{day_index}/TimeInEqualize', None)
                    self.history_days_created.add(day_index)

                # Update values from history data
                day_data = history[history_index]

                self.dbus[f'/History/Daily/{day_index}/Yield'] = day_data.get('yield', 0.0)
                self.dbus[f'/History/Daily/{day_index}/MaxPower'] = day_data.get('max_power', 0)
                self.dbus[f'/History/Daily/{day_index}/MaxPvVoltage'] = day_data.get('max_pv_voltage', 0.0)
                self.dbus[f'/History/Daily/{day_index}/MaxBatteryVoltage'] = day_data.get('max_battery_voltage', 0.0)
                self.dbus[f'/History/Daily/{day_index}/MinBatteryVoltage'] = day_data.get('min_battery_voltage', 0.0)
                self.dbus[f'/History/Daily/{day_index}/MaxBatteryCurrent'] = day_data.get('max_battery_current', 0.0)
                self.dbus[f'/History/Daily/{day_index}/TimeInBulk'] = day_data.get('time_bulk', 0)
                self.dbus[f'/History/Daily/{day_index}/TimeInAbsorption'] = day_data.get('time_absorption', 0)
                self.dbus[f'/History/Daily/{day_index}/TimeInFloat'] = day_data.get('time_float', 0)
                self.dbus[f'/History/Daily/{day_index}/TimeInEqualize'] = day_data.get('time_equalize', 0)

        except Exception as e:
            logging.error(f"Error updating historical days: {e}", exc_info=True)

    def _check_midnight_rollover(self, current_daily_kwh):
        """Check if date changed (midnight passed) and rotate history"""
        try:
            current_date = self._get_local_date()

            if self.last_reset_date is None:
                # First run, just set the date
                self.last_reset_date = current_date
                self.state['current_date'] = current_date
                return

            if current_date != self.last_reset_date:
                logging.info(f"Midnight detected! Date changed: {self.last_reset_date} → {current_date}")

                # Snapshot yesterday's final values (from day 0 before reset)
                # Capture current Day 0 values which have been tracking all day
                yesterday_snapshot = {
                    "date": self.last_reset_date,
                    "yield": current_daily_kwh,  # Use REG_WHC_DAILY before it resets
                    "max_power": self.daily_max_power,
                    "max_pv_voltage": self.daily_max_pv_voltage,
                    "max_battery_voltage": self.daily_max_battery_voltage,
                    "min_battery_voltage": self.daily_min_battery_voltage if self.daily_min_battery_voltage < 999 else 0.0,
                    "max_battery_current": self.daily_max_battery_current,
                    "time_bulk": int(self.t_bulk_ms / (1000 * 60)),
                    "time_absorption": self.dbus['/History/Daily/0/TimeInAbsorption'],
                    "time_float": self.dbus['/History/Daily/0/TimeInFloat'],
                    "time_equalize": self.dbus['/History/Daily/0/TimeInEqualize']
                }

                # Add yesterday's production to total
                self.state['total_yield_kwh'] += current_daily_kwh
                logging.info(f"Added {current_daily_kwh:.3f} kWh to total. New total: {self.state['total_yield_kwh']:.2f} kWh")

                # Insert yesterday at position 0, shifting everything
                self.state['history'].insert(0, yesterday_snapshot)

                # Keep only 29 days of history (day 0 = today, days 1-29 = history)
                if len(self.state['history']) > 29:
                    self.state['history'] = self.state['history'][:29]
                    logging.info(f"Trimmed history to 29 days (oldest day removed)")

                # Update current date
                self.last_reset_date = current_date
                self.state['current_date'] = current_date

                # Reset daily trackers for new day
                self.daily_max_battery_current = 0.0
                self.daily_max_power = 0.0
                self.daily_max_battery_voltage = 0.0
                self.daily_min_battery_voltage = 999.0
                self.daily_max_pv_voltage = 0.0
                self.t_bulk_ms = 0

                # Reset register flag (expect register to reset when sun comes up)
                self.daily_register_has_reset = False

                # Save state to file
                self._save_state()

                logging.info(f"History rotated. Now have {len(self.state['history'])} days of history")

        except Exception as e:
            logging.error(f"Error in midnight rollover: {e}")

    def _setup_dbus_paths(self):
        """Setup all D-Bus paths"""
        s = self.dbus

        # Management
        s.add_path('/Mgmt/ProcessName', __file__)
        s.add_path('/Mgmt/ProcessVersion', VERSION)
        s.add_path('/Mgmt/Connection', 'Modbus TCP')

        # Device info
        s.add_path('/ProductId', PRODUCT_ID)
        s.add_path('/ProductName', '')
        s.add_path('/FirmwareVersion', 0)
        s.add_path('/HardwareVersion', '')
        s.add_path('/Serial', '')
        s.add_path('/DeviceInstance', int(self.settings['device_instance']))
        s.add_path('/Connected', 0)
        s.add_path('/Mode', 1)
        s.add_path('/ErrorCode', 0)

        # Number of trackers (TriStar MPPT 60 is single-tracker)
        s.add_path('/NrOfTrackers', 1)

        # PV array
        s.add_path('/Pv/V', 0.0, gettextcallback=lambda p, v: f"{v}V")
        # Note: /Pv/I is deprecated since v2.80 - GUI calculates current from /Yield/Power / /Pv/V

        # Battery
        s.add_path('/Dc/0/Voltage', 0.0, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/Dc/0/Current', 0.0, gettextcallback=lambda p, v: f"{v}A")
        s.add_path('/Dc/0/Temperature', 0.0)

        # Power and state
        s.add_path('/Yield/Power', 0, gettextcallback=lambda p, v: f"{v}W")
        s.add_path('/State', 0)
        s.add_path('/MppOperationMode', 0)  # 0=Off, 1=Voltage/Current limited, 2=MPPT active

        # History
        s.add_path('/History/Overall/DaysAvailable', 1)
        # History - Day 0 (today, live values) - always created
        s.add_path('/History/Daily/0/Yield', 0.0, gettextcallback=lambda p, v: f"{v}kWh")
        s.add_path('/History/Daily/0/MaxPower', 0, gettextcallback=lambda p, v: f"{v}W")
        s.add_path('/History/Daily/0/MaxPvVoltage', 0.0, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/History/Daily/0/MaxBatteryVoltage', 0.0, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/History/Daily/0/MinBatteryVoltage', 0.0, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/History/Daily/0/MaxBatteryCurrent', 0.0, gettextcallback=lambda p, v: f"{v}A")
        s.add_path('/History/Daily/0/TimeInBulk', 0)
        s.add_path('/History/Daily/0/TimeInAbsorption', 0)
        s.add_path('/History/Daily/0/TimeInFloat', 0)
        s.add_path('/History/Daily/0/TimeInEqualize', 0)

        # History - Days 1-29 will be created dynamically as history accumulates
        # This prevents Venus OS from thinking we have 30 days of data when we don't

        # Total yield
        s.add_path('/Yield/User', 0.0, gettextcallback=lambda p, v: f"{v}kWh")
        s.add_path('/Yield/System', 0.0, gettextcallback=lambda p, v: f"{v}kWh")

        # Control (coils) - writable
        s.add_path('/Control/EqualizeTriggered', 0, writeable=True, onchangecallback=self._on_coil_write)
        s.add_path('/Control/ChargerDisconnect', 0, writeable=True, onchangecallback=self._on_coil_write)
        s.add_path('/Control/ResetController', 0, writeable=True, onchangecallback=self._on_coil_write)
        s.add_path('/Control/ResetCommServer', 0, writeable=True, onchangecallback=self._on_coil_write)

        # Statistics for diagnostics and health monitoring
        s.add_path('/Custom/Stats/SuccessfulReads', 0, writeable=False)
        s.add_path('/Custom/Stats/FailedReads', 0, writeable=False)
        s.add_path('/Custom/Stats/ConsecutiveFailures', 0, writeable=False)
        s.add_path('/Custom/Stats/LastSuccessTime', 0, writeable=False)  # Unix timestamp
        s.add_path('/Custom/Stats/BackoffFactor', 1, writeable=False)  # Poll interval multiplier

        # TriStar-specific charge state (raw values from TriStar)
        s.add_path('/Custom/ChargeState', None, writeable=False)  # Raw TriStar charge state (0-9)
        s.add_path('/Custom/ChargeStateText', None, writeable=False)  # Text representation
        s.add_path('/Custom/TargetRegulationVoltage', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")  # Target regulation voltage

        # Battery diagnostics
        s.add_path('/Custom/Battery/TerminalVoltage', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/Custom/Battery/SenseVoltage', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/Custom/Battery/CurrentFast', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}A")
        s.add_path('/Custom/Battery/VoltageSlow', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")

        # Internal power supply monitoring
        s.add_path('/Custom/InternalSupply/Rail12V', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/Custom/InternalSupply/Rail3V', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/Custom/InternalSupply/MeterBusV', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/Custom/InternalSupply/Rail1V8', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/Custom/InternalSupply/Vref', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")

        # Temperature sensors
        s.add_path('/Custom/Temperature/Heatsink', 0.0, writeable=False)
        s.add_path('/Custom/Temperature/RTS', 0.0, writeable=False)

        # Min/Max tracking
        s.add_path('/Custom/MinMax/MinBatteryVoltage', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/Custom/MinMax/MaxBatteryVoltage', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")

        # Diagnostic bitfields (raw)
        s.add_path('/Custom/Faults/Bitfield', None, writeable=False)
        s.add_path('/Custom/DipSwitches/Bitfield', None, writeable=False)
        s.add_path('/Custom/Led/State', None, writeable=False)

        # Fault bitfield decoded paths
        for bit, name in FAULT_BITS.items():
            s.add_path(f'/Custom/Faults/{name}', None, writeable=False)

        # DIP switch bitfield decoded paths (8 switches)
        for i in range(8):
            s.add_path(f'/Custom/DipSwitches/Switch{i+1}', None, writeable=False)

        # PV/MPPT data
        s.add_path('/Custom/Pv/PowerInputShadow', 0, writeable=False, gettextcallback=lambda p, v: f"{v}W")
        s.add_path('/Custom/MPPT/LastSweep/Pmax', 0, writeable=False, gettextcallback=lambda p, v: f"{v}W")
        s.add_path('/Custom/MPPT/LastSweep/Vmp', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/Custom/MPPT/LastSweep/Voc', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")

        # Daily history
        s.add_path('/Custom/Daily/ChargeAh', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}Ah")
        s.add_path('/Custom/Daily/FlagsBitfield', None, writeable=False)
        s.add_path('/Custom/Daily/MinBatteryTemperature', 0.0, writeable=False)
        s.add_path('/Custom/Daily/MaxBatteryTemperature', 0.0, writeable=False)
        s.add_path('/Custom/Daily/FaultsBitfield', None, writeable=False)
        s.add_path('/Custom/Daily/TimeInEqualize', 0, writeable=False, gettextcallback=lambda p, v: f"{v}min")

        # Daily flags bitfield decoded paths
        for bit, name in FLAGS_DAILY_BITS.items():
            s.add_path(f'/Custom/Daily/Flags/{name}', None, writeable=False)

        # Daily faults bitfield decoded paths (same as FAULT_BITS)
        for bit, name in FAULT_BITS.items():
            s.add_path(f'/Custom/Daily/Faults/{name}', None, writeable=False)

    def _start_timer(self):
        """Start or restart the periodic update timer (with exponential backoff support)"""
        # Stop existing timer if running
        if self.timer_id is not None:
            GLib.source_remove(self.timer_id)
            logging.debug(f"Removed previous timer (ID: {self.timer_id})")

        # Convert milliseconds to seconds and apply backoff
        poll_interval_ms = int(self.settings['poll_interval']) * self.backoff_factor
        poll_interval_sec = int(poll_interval_ms // 1000)

        # Start new timer
        self.timer_id = GLib.timeout_add_seconds(poll_interval_sec, self.update)

        if self.backoff_factor > 1:
            logging.info(f"Timer started with backoff: {poll_interval_sec}s ({self.backoff_factor}x base interval), ID: {self.timer_id}")
        else:
            logging.info(f"Timer started with interval: {poll_interval_sec} seconds ({int(self.settings['poll_interval'])}ms), ID: {self.timer_id}")

    def _setting_changed(self, setting, old, new):
        """Called when a setting changes in the GUI"""
        logging.info(f"Setting '{setting}' changed from '{old}' to '{new}'")

        if setting == 'poll_interval':
            # Restart timer with new interval
            logging.info("Restarting timer with new poll interval")
            self._start_timer()
        elif setting in ['ip_address', 'modbus_port', 'slave_id']:
            # Force re-initialization with new settings
            logging.info("Connection settings changed - will re-initialize on next update")
            self.initialized = False

    def _on_coil_write(self, path, value):
        """Called when a coil control is written via D-Bus"""
        logging.info(f"Coil write request: {path} = {value}")

        # Map D-Bus path to coil address
        coil_map = {
            '/Control/EqualizeTriggered': COIL_EQUALIZE,
            '/Control/ChargerDisconnect': COIL_DISCONNECT,
            '/Control/ResetController': COIL_RESET_CTRL,
            '/Control/ResetCommServer': COIL_RESET_COMM,
        }

        coil_addr = coil_map.get(path)
        if coil_addr is None:
            logging.error(f"Unknown coil path: {path}")
            return False

        # Write coil
        success = self.write_coil(coil_addr, bool(value))

        # For momentary buttons, reset to 0 immediately
        if coil_addr in [COIL_RESET_CTRL, COIL_RESET_COMM]:
            return 0  # Fire-and-forget

        # For stateful coils, keep the written value
        return value if success else not value

    def read_input_registers(self, address, count):
        """
        Read input registers with C++ pattern: connect → read → close
        Matches original C++ driver behavior exactly
        """
        ip = self.settings['ip_address']
        port = self.settings['modbus_port']
        slave_id = self.settings['slave_id']

        for attempt in range(5):
            # Create new client for each attempt (like C++)
            # Use short timeout for WAN, no internal retries (we handle retries ourselves)
            client = ModbusTcpClient(
                host=ip,
                port=port,
                timeout=1,  # 1 second - enough for WAN roundtrip
                retries=0   # No internal retries - we handle it in our loop
            )

            try:
                # Connect
                if not client.connect():
                    if attempt < 4:
                        logging.debug(f"Connection failed, retry {attempt + 1}/5")
                        continue
                    else:
                        logging.error(f"Failed to connect to {ip}:{port} after 5 retries")
                        return None

                # Read
                result = client.read_input_registers(
                    address=address,
                    count=count,
                    unit=slave_id
                )

                # Check result
                if result.isError():
                    if attempt < 4:
                        logging.debug(f"Modbus error, retry {attempt + 1}/5")
                        client.close()
                        continue
                    else:
                        logging.error("Modbus error after 5 retries")
                        client.close()
                        return None

                # Success - close and return
                registers = result.registers
                client.close()
                return registers

            except Exception as e:
                if attempt < 4:
                    logging.debug(f"Exception, retry {attempt + 1}/5: {e}")
                else:
                    logging.error(f"Exception after 5 retries: {e}")

                try:
                    client.close()
                except:
                    pass

                if attempt == 4:
                    return None

        return None

    def read_coils(self, address, count):
        """
        Read coils with connect → read → close pattern
        """
        ip = self.settings['ip_address']
        port = self.settings['modbus_port']
        slave_id = self.settings['slave_id']

        for attempt in range(5):
            client = ModbusTcpClient(host=ip, port=port, timeout=1, retries=0)

            try:
                if not client.connect():
                    if attempt < 4:
                        continue
                    else:
                        logging.error(f"Failed to connect for coil read after 5 retries")
                        return None

                result = client.read_coils(address=address, count=count, unit=slave_id)

                if result.isError():
                    if attempt < 4:
                        client.close()
                        continue
                    else:
                        logging.error("Coil read error after 5 retries")
                        client.close()
                        return None

                bits = result.bits[:count]
                client.close()
                return bits

            except Exception as e:
                if attempt < 4:
                    logging.debug(f"Coil read exception, retry {attempt + 1}/5: {e}")
                else:
                    logging.error(f"Coil read exception after 5 retries: {e}")

                try:
                    client.close()
                except:
                    pass

                if attempt == 4:
                    return None

        return None

    def write_coil(self, address, value):
        """
        Write single coil with connect → write → close pattern
        For critical coils (EQUALIZE, DISCONNECT), verify write with read-back
        For reset coils (RESET_CTRL, RESET_COMM), timeout is expected behavior
        """
        ip = self.settings['ip_address']
        port = self.settings['modbus_port']
        slave_id = self.settings['slave_id']

        # Reset coils drop connection immediately - timeout is expected
        is_reset_coil = address in [COIL_RESET_CTRL, COIL_RESET_COMM]

        for attempt in range(5):
            client = ModbusTcpClient(host=ip, port=port, timeout=1, retries=0)

            try:
                if not client.connect():
                    if attempt < 4:
                        continue
                    else:
                        # For reset coils, connection failure is expected
                        if is_reset_coil:
                            logging.info(f"Reset coil {address} sent (connection dropped as expected)")
                            return True
                        logging.error(f"Failed to connect for coil write after 5 retries")
                        return False

                result = client.write_coil(address=address, value=value, unit=slave_id)

                if result.isError():
                    if attempt < 4:
                        client.close()
                        continue
                    else:
                        logging.error(f"Coil write error after 5 retries")
                        client.close()
                        return False

                client.close()
                logging.info(f"Successfully wrote coil {address} = {value}")

                # Critical coils: verify write succeeded by reading back
                if address in [COIL_EQUALIZE, COIL_DISCONNECT]:
                    sleep(0.1)  # Give TriStar time to process
                    verify = self.read_coils(address, 1)
                    if verify is None:
                        logging.warning(f"Coil write verification failed: could not read back coil {address}")
                        return False
                    elif verify[0] != value:
                        logging.error(f"Coil write verification failed for {address}: wrote {value}, read back {verify[0]}")
                        return False
                    else:
                        logging.debug(f"Coil {address} verified: {value}")

                return True

            except Exception as e:
                # For reset coils, timeout/exception is expected - TriStar resets and drops connection
                if is_reset_coil and attempt == 4:
                    logging.info(f"Reset coil {address} sent (timeout expected - comm server reset)")
                    return True

                if attempt < 4:
                    logging.debug(f"Coil write exception, retry {attempt + 1}/5: {e}")
                else:
                    logging.error(f"Coil write exception after 5 retries: {e}")

                try:
                    client.close()
                except:
                    pass

                if attempt == 4:
                    return False

        return False

    def initialize(self):
        """Read static device information"""
        if self.initialized:
            return True

        logging.info("Initializing TriStar MPPT...")

        # Read scaling factors and firmware version
        regs = self.read_input_registers(REG_V_PU, 6)
        if regs is None:
            return False

        # Voltage scaling
        self.v_pu = float(regs[0]) + (float(regs[1]) / 65536.0)
        self.i_pu = float(regs[2]) + (float(regs[3]) / 65536.0)
        logging.info(f"Scaling: V_PU={self.v_pu:.6f}, I_PU={self.i_pu:.6f}")

        # Firmware version (BCD)
        ver = regs[4]
        self.firmware_version = (
            ((ver >> 12) & 0x0f) * 1000 +
            ((ver >> 8) & 0x0f) * 100 +
            ((ver >> 4) & 0x0f) * 10 +
            (ver & 0x0f)
        )

        # Hardware version
        regs = self.read_input_registers(REG_EHW_VERSION, 1)
        if regs is None:
            return False
        self.hardware_version = f"{regs[0] >> 8}.{regs[0] & 0xff}"

        # Model name
        regs = self.read_input_registers(REG_EMODEL, 1)
        if regs is None:
            return False
        model_map = {
            0: "TriStar MPPT 45",
            1: "TriStar MPPT 60",
            2: "TriStar MPPT 30"
        }
        self.product_name = model_map.get(regs[0], "TriStar MPPT")

        # Serial number
        regs = self.read_input_registers(REG_ESERIAL, 4)
        if regs is None:
            return False

        serial = 0
        for reg in regs:
            low = (reg & 0xff) - 0x30
            high = (reg >> 8) - 0x30
            serial = serial * 100 + high * 10 + low
        self.serial_number = str(serial)

        # Update D-Bus with static info
        self.dbus['/ProductName'] = self.product_name
        self.dbus['/FirmwareVersion'] = self.firmware_version
        self.dbus['/HardwareVersion'] = self.hardware_version
        self.dbus['/Serial'] = self.serial_number

        logging.info(f"{self.product_name} initialized")
        logging.info(f"  Serial: {self.serial_number}")
        logging.info(f"  HW: v{self.hardware_version}, FW: {self.firmware_version}")

        self.initialized = True
        return True

    def update(self):
        """Periodic update - read values and publish to D-Bus"""
        logging.info("update() called")
        try:
            if not self.initialized:
                logging.info("Not initialized, attempting to initialize...")
                if not self.initialize():
                    self.dbus['/Connected'] = 0
                    return True  # Continue timer

            # Read all dynamic registers (batch read: 24-79 = 56 registers)
            # This reduces Modbus round-trips from 20+ to 1
            regs = self.read_input_registers(REG_V_BAT, REG_T_FLOAT - REG_V_BAT + 1)
            if regs is None:
                # Update failure statistics
                self.failed_reads += 1
                self.consecutive_failures += 1
                self.dbus['/Custom/Stats/FailedReads'] = self.failed_reads
                self.dbus['/Custom/Stats/ConsecutiveFailures'] = self.consecutive_failures

                # Check watchdog timeout
                time_since_success = time() - self.last_successful_read
                if time_since_success > self.watchdog_timeout:
                    logging.warning(f"Connection watchdog timeout ({time_since_success:.0f}s > {self.watchdog_timeout}s)")
                    self.dbus['/Connected'] = 0
                    self.initialized = False

                # Exponential backoff on persistent failures
                if self.consecutive_failures >= 10:  # 10 failures = 50 seconds at 5s interval
                    new_backoff = min(4, self.backoff_factor * 2)  # Max 4x interval
                    if new_backoff != self.backoff_factor:
                        self.backoff_factor = new_backoff
                        self.dbus['/Custom/Stats/BackoffFactor'] = self.backoff_factor
                        logging.warning(f"Too many consecutive failures ({self.consecutive_failures}), backing off to {self.backoff_factor}x poll interval")
                        self._start_timer()

                return True

            # Mark as connected and update watchdog
            self.dbus['/Connected'] = 1
            self.last_successful_read = time()

            # Update success statistics
            self.successful_reads += 1
            self.dbus['/Custom/Stats/SuccessfulReads'] = self.successful_reads
            self.dbus['/Custom/Stats/LastSuccessTime'] = int(time())

            # Reset consecutive failures and backoff if recovered
            if self.consecutive_failures > 0:
                logging.info(f"Connection recovered after {self.consecutive_failures} failures")
                self.consecutive_failures = 0
                self.dbus['/Custom/Stats/ConsecutiveFailures'] = 0

                if self.backoff_factor > 1:
                    self.backoff_factor = 1
                    self.dbus['/Custom/Stats/BackoffFactor'] = 1
                    logging.info("Resetting to normal poll interval")
                    self._start_timer()

            # Helper to get register by address
            def reg(addr):
                return regs[addr - REG_V_BAT]

            # Calculate time delta for bulk charge tracking
            now = time()
            dt_ms = (now - self.last_update) * 1000
            self.last_update = now

            # Parse and convert values using TriStar scaling factors
            # TriStar uses 16-bit signed registers with per-unit scaling:
            #   - Voltage/Current: register_value × PU / 2^15 (32768)
            #   - Power: (V × I) uses 2^17 scaling (131072)
            v_bat = reg(REG_V_BAT) * self.v_pu / 32768.0
            i_cc = max(0.0, self._to_signed(reg(REG_I_CC_1M)) * self.i_pu / 32768.0)
            v_pv = reg(REG_V_PV) * self.v_pu / 32768.0
            i_pv = reg(REG_I_PV) * self.i_pu / 32768.0
            p_out = reg(REG_POUT) * self.i_pu * self.v_pu / 131072.0  # 2^17 for power (V×I product)
            v_target = reg(REG_V_TARGET) * self.v_pu / 32768.0

            # Sanity checks on critical values (protect against Modbus corruption over WAN)
            # LiFePO4 7S nominal: 21V-29.4V, allow margin for system voltage variations
            if not (18.0 <= v_bat <= 35.0):
                logging.warning(f"Unrealistic battery voltage: {v_bat:.2f}V - possible Modbus corruption, skipping update")
                # Don't update statistics on corrupt data
                return True

            # TriStar MPPT 60: max PV input 150V
            if not (0 <= v_pv <= 160.0):
                logging.warning(f"Unrealistic PV voltage: {v_pv:.2f}V - possible Modbus corruption, skipping update")
                return True

            # TriStar MPPT 60: max charge current 60A
            if not (0 <= i_cc <= 70.0):
                logging.warning(f"Unrealistic charge current: {i_cc:.2f}A - possible Modbus corruption, skipping update")
                return True

            # Max output power sanity check (60A × 35V = 2100W, allow margin)
            if not (0 <= p_out <= 2500.0):
                logging.warning(f"Unrealistic output power: {p_out:.0f}W - possible Modbus corruption, skipping update")
                return True

            # Charge state
            cs_raw = reg(REG_CHARGE_STATE)
            cs = CHARGE_STATE_MAP.get(cs_raw, 0)

            # Calculate bulk time
            if cs_raw == CS_BULK:
                self.t_bulk_ms += dt_ms
            elif cs_raw == CS_NIGHT:
                self.t_bulk_ms = 0

            # Update D-Bus
            self.dbus['/Pv/V'] = round(v_pv, 2)
            # /Pv/I removed - deprecated since v2.80, GUI calculates from Power/Voltage
            self.dbus['/Dc/0/Voltage'] = round(v_bat, 2)
            self.dbus['/Dc/0/Current'] = round(i_cc, 2)
            self.dbus['/Dc/0/Temperature'] = round(self._to_signed(reg(REG_T_BAT)), 1)
            self.dbus['/Yield/Power'] = round(p_out, 0)
            self.dbus['/State'] = cs
            # MppOperationMode: 0=Off, 1=V/I limited, 2=MPPT active
            if cs == 0 or cs == 2:
                self.dbus['/MppOperationMode'] = 0  # Off or Fault
            else:
                self.dbus['/MppOperationMode'] = 2  # MPPT tracking active

            # Custom TriStar-specific values
            self.dbus['/Custom/ChargeState'] = cs_raw
            self.dbus['/Custom/ChargeStateText'] = CHARGE_STATE_TEXT.get(cs_raw, "UNKNOWN")
            self.dbus['/Custom/TargetRegulationVoltage'] = round(v_target, 2)

            # Battery diagnostics
            self.dbus['/Custom/Battery/TerminalVoltage'] = round(reg(REG_V_BAT_TERM) * self.v_pu / 32768.0, 2)
            self.dbus['/Custom/Battery/SenseVoltage'] = round(reg(REG_V_BAT_SENSE) * self.v_pu / 32768.0, 2)
            self.dbus['/Custom/Battery/CurrentFast'] = round(self._to_signed(reg(REG_I_CC_FAST)) * self.i_pu / 32768.0, 2)
            self.dbus['/Custom/Battery/VoltageSlow'] = round(reg(REG_V_BAT_SLOW) * self.v_pu / 32768.0, 2)

            # Internal power supply - use FIXED scaling constants per spec (NOT v_pu!)
            # Spec: MS-002582_v11.pdf, registers 31-35 use fixed voltage scaling
            self.dbus['/Custom/InternalSupply/Rail12V'] = round(reg(REG_12V_SUPPLY) * 18.612 / 32768.0, 2)
            self.dbus['/Custom/InternalSupply/Rail3V'] = round(reg(REG_3V_SUPPLY) * 6.6 / 32768.0, 2)
            self.dbus['/Custom/InternalSupply/MeterBusV'] = round(reg(REG_METERBUS_V) * 18.612 / 32768.0, 2)
            self.dbus['/Custom/InternalSupply/Rail1V8'] = round(reg(REG_1V8_SUPPLY) * 3.0 / 32768.0, 2)
            self.dbus['/Custom/InternalSupply/Vref'] = round(reg(REG_VREF) * 3.0 / 32768.0, 2)

            # Temperature sensors (with RTS disconnect handling)
            self.dbus['/Custom/Temperature/Heatsink'] = round(self._to_signed(reg(REG_T_HS)), 1)
            rts_raw = reg(REG_T_RTS)
            if rts_raw == 0x80:
                self.dbus['/Custom/Temperature/RTS'] = None  # Sensor disconnected
            else:
                self.dbus['/Custom/Temperature/RTS'] = round(self._to_signed(rts_raw), 1)

            # Min/Max tracking
            self.dbus['/Custom/MinMax/MinBatteryVoltage'] = round(reg(REG_V_BAT_MIN_ALL) * self.v_pu / 32768.0, 2)
            self.dbus['/Custom/MinMax/MaxBatteryVoltage'] = round(reg(REG_V_BAT_MAX_ALL) * self.v_pu / 32768.0, 2)

            # Diagnostic bitfields (raw)
            faults = reg(REG_FAULTS)
            dip_switches = reg(REG_DIP_SWITCHES)
            led_state = reg(REG_LED_STATE)
            self.dbus['/Custom/Faults/Bitfield'] = faults
            self.dbus['/Custom/DipSwitches/Bitfield'] = dip_switches
            self.dbus['/Custom/Led/State'] = led_state

            # Decode fault bitfield
            for bit, name in FAULT_BITS.items():
                self.dbus[f'/Custom/Faults/{name}'] = bool(faults & (1 << bit))

            # Decode DIP switches bitfield (8 switches)
            for i in range(8):
                self.dbus[f'/Custom/DipSwitches/Switch{i+1}'] = bool(dip_switches & (1 << i))

            # PV/MPPT data
            self.dbus['/Custom/Pv/PowerInputShadow'] = round(reg(REG_P_IN_SHADOW) * self.i_pu * self.v_pu / 131072.0, 0)
            self.dbus['/Custom/MPPT/LastSweep/Pmax'] = round(reg(REG_SWEEP_PMAX) * self.i_pu * self.v_pu / 131072.0, 0)
            self.dbus['/Custom/MPPT/LastSweep/Vmp'] = round(reg(REG_SWEEP_VMP) * self.v_pu / 32768.0, 2)
            self.dbus['/Custom/MPPT/LastSweep/Voc'] = round(reg(REG_SWEEP_VOC) * self.v_pu / 32768.0, 2)

            # Daily history
            self.dbus['/Custom/Daily/ChargeAh'] = round(reg(REG_AHC_DAILY) * 0.1, 2)  # Spec: units of 0.1 Ah
            flags_daily = reg(REG_FLAGS_DAILY)
            faults_daily = reg(REG_FAULTS_DAILY)
            self.dbus['/Custom/Daily/FlagsBitfield'] = flags_daily
            self.dbus['/Custom/Daily/MinBatteryTemperature'] = round(self._to_signed(reg(REG_T_BAT_MIN_DAILY)), 1)
            self.dbus['/Custom/Daily/MaxBatteryTemperature'] = round(self._to_signed(reg(REG_T_BAT_MAX_DAILY)), 1)
            self.dbus['/Custom/Daily/FaultsBitfield'] = faults_daily
            self.dbus['/Custom/Daily/TimeInEqualize'] = reg(REG_T_EQ_DAILY) // 60  # Convert seconds to minutes

            # Decode daily flags bitfield
            for bit, name in FLAGS_DAILY_BITS.items():
                self.dbus[f'/Custom/Daily/Flags/{name}'] = bool(flags_daily & (1 << bit))

            # Decode daily faults bitfield (same as FAULT_BITS)
            for bit, name in FAULT_BITS.items():
                self.dbus[f'/Custom/Daily/Faults/{name}'] = bool(faults_daily & (1 << bit))

            # Track daily max/min values (for our own tracking, not from Modbus)
            self.daily_max_battery_current = max(self.daily_max_battery_current, i_cc)
            self.daily_max_power = max(self.daily_max_power, p_out)
            self.daily_max_battery_voltage = max(self.daily_max_battery_voltage, v_bat)
            if v_bat > 0:  # Only update min if we have a valid reading
                self.daily_min_battery_voltage = min(self.daily_min_battery_voltage, v_bat)
            self.daily_max_pv_voltage = max(self.daily_max_pv_voltage, v_pv)

            # Calculate daily yield with register reset detection
            # (used for history, yield calculation, and midnight rollover)
            current_daily_wh = reg(REG_WHC_DAILY)

            # Detect register reset (value decreased = sun came up and register reset)
            if current_daily_wh < self.last_daily_register_value:
                self.daily_register_has_reset = True
                logging.info(f"Detected REG_WHC_DAILY reset: {self.last_daily_register_value} → {current_daily_wh} Wh (sun came up)")

            # On first update, infer reset state from charge state
            if self.last_daily_register_value == 0:  # First update
                if cs >= 3:  # Bulk, Absorption, Float, Equalize (actively charging)
                    self.daily_register_has_reset = True
                    logging.info("First update while charging - assuming register has reset")

            self.last_daily_register_value = current_daily_wh

            # If post-midnight but pre-sunrise (register hasn't reset), use 0
            if not self.daily_register_has_reset:
                daily_kwh = 0.0  # Don't use yesterday's stale value
                logging.debug("Post-midnight, pre-sunrise: using 0 for daily yield")
            else:
                daily_kwh = current_daily_wh / 1000.0

            # Check for midnight (date changed) - do this BEFORE updating history paths
            self._check_midnight_rollover(daily_kwh)

            # History - Day 0 (today, live values)
            # Use 0 for all values if post-midnight but register hasn't reset yet
            self.dbus['/History/Daily/0/Yield'] = round(daily_kwh, 2)

            if not self.daily_register_has_reset:
                # Post-midnight, pre-sunrise: use 0 for all daily register values
                self.dbus['/History/Daily/0/MaxPower'] = 0
                self.dbus['/History/Daily/0/MaxPvVoltage'] = 0.0
                self.dbus['/History/Daily/0/MaxBatteryVoltage'] = 0.0
                self.dbus['/History/Daily/0/MinBatteryVoltage'] = 0.0
                self.dbus['/History/Daily/0/TimeInAbsorption'] = 0
                self.dbus['/History/Daily/0/TimeInFloat'] = 0
                self.dbus['/History/Daily/0/TimeInEqualize'] = 0
            else:
                # Register has reset: use actual values from Modbus
                self.dbus['/History/Daily/0/MaxPower'] = round(
                    reg(REG_POUT_MAX_DAILY) * self.i_pu * self.v_pu / 131072.0, 0
                )
                self.dbus['/History/Daily/0/MaxPvVoltage'] = round(
                    reg(REG_V_PV_MAX) * self.v_pu / 32768.0, 2
                )
                self.dbus['/History/Daily/0/MaxBatteryVoltage'] = round(
                    reg(REG_V_BAT_MAX) * self.v_pu / 32768.0, 2
                )
                self.dbus['/History/Daily/0/MinBatteryVoltage'] = round(
                    reg(REG_V_BAT_MIN) * self.v_pu / 32768.0, 2
                )
                self.dbus['/History/Daily/0/TimeInAbsorption'] = reg(REG_T_ABS) // 60
                self.dbus['/History/Daily/0/TimeInFloat'] = reg(REG_T_FLOAT) // 60
                self.dbus['/History/Daily/0/TimeInEqualize'] = reg(REG_T_EQ_DAILY) // 60

            # These values are tracked by us (reset at midnight), so always use them
            self.dbus['/History/Daily/0/MaxBatteryCurrent'] = round(self.daily_max_battery_current, 2)
            self.dbus['/History/Daily/0/TimeInBulk'] = int(self.t_bulk_ms / (1000 * 60))

            # Update historical days 1-29 from state file
            self._update_historical_days()

            # Total yield (use persistent counter to avoid double-counting)
            # Initialize total_yield_kwh from controller on first run
            if self.state['total_yield_kwh'] == 0.0:
                lifetime_kwh = reg(REG_KWH_TOTAL_RES)
                if lifetime_kwh > 0:
                    logging.info(f"Initializing total_yield_kwh from controller: {lifetime_kwh} kWh")
                    self.state['total_yield_kwh'] = float(lifetime_kwh)
                    self._save_state()

            # Total yield: persistent total + today's calculated yield (already handled above)
            self.dbus['/Yield/User'] = round(self.state['total_yield_kwh'] + daily_kwh, 2)
            self.dbus['/Yield/System'] = round(self.state['total_yield_kwh'] + daily_kwh, 2)

            # Read stateful coils
            coils = self.read_coils(COIL_EQUALIZE, 3)  # Read coils 0, 1, 2
            if coils is not None:
                self.dbus['/Control/EqualizeTriggered'] = int(coils[0])
                self.dbus['/Control/ChargerDisconnect'] = int(coils[2])
            else:
                logging.warning("Failed to read coils - control status may be stale")

            # Nightly reset at 03:00
            self._check_nightly_reset()

        except Exception as e:
            logging.error(f"Update error: {e}", exc_info=True)

        return True  # Continue timer

    def _check_nightly_reset(self):
        """Check if we should perform nightly comm server reset at 03:00"""
        now = datetime.now()
        current_date = now.date()
        current_hour = now.hour
        current_minute = now.minute

        # Check if it's 03:00-03:04 (5-minute window to catch it)
        if current_hour == 3 and current_minute < 5:
            # Only attempt reset once per day
            if self.last_reset_date != current_date:
                # Mark as attempted BEFORE trying (prevent retry spam if write fails)
                self.last_reset_date = current_date

                logging.info("Performing nightly comm server reset and daily counters reset at 03:00")

                # Reset daily counters
                self.t_bulk_ms = 0

                # Reset comm server
                success = self.write_coil(COIL_RESET_COMM, True)
                if success:
                    logging.info("Nightly reset completed successfully")
                else:
                    logging.error("Nightly reset failed - will retry tomorrow")

    @staticmethod
    def _to_signed(value):
        """Convert 16-bit unsigned to signed"""
        if value >= 32768:
            return value - 65536
        return value


def main():
    """Main entry point"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)-8s %(message)s'
    )

    logging.info(f"dbus-tristar v{VERSION} starting")
    logging.info("Venus OS compatible using SettingsDevice")

    # Setup graceful shutdown handlers
    mainloop = None

    def cleanup_and_exit(signum=None, frame=None):
        """Handle shutdown signals gracefully"""
        sig_name = signal.Signals(signum).name if signum else "unknown"
        logging.info(f"Received signal {sig_name} - shutting down gracefully...")
        if mainloop:
            mainloop.quit()
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup_and_exit)
    signal.signal(signal.SIGINT, cleanup_and_exit)

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    driver = TriStarDriver()

    logging.info("✓ Driver initialized")
    logging.info("Configure via: dbus -y com.victronenergy.settings /Settings/TristarMPPT/...")
    logging.info("Entering main loop...")

    mainloop = GLib.MainLoop()
    mainloop.run()


if __name__ == '__main__':
    main()
