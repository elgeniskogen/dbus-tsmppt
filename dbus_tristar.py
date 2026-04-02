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
import os
import dbus
import dbus.mainloop.glib
from gi.repository import GLib
from time import time, sleep
import time as time_module
from datetime import datetime, time as dt_time, timezone, timedelta
import json
from pathlib import Path
import threading

# pymodbus v2.x (Venus OS) vs v3.x compatibility
try:
    from pymodbus.client import ModbusTcpClient
except ImportError:
    from pymodbus.client.sync import ModbusTcpClient

# Import Victron packages
sys.path.insert(1, '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python')
from vedbus import VeDbusService
from settingsdevice import SettingsDevice

VERSION = "2.34"  # Fix: Add time offsets for absorption/float/equalize across controller resets
PRODUCT_ID = 0xABCD  # Placeholder - can be registered with Victron

# ============================================================================
# CONFIGURATION - Edit these values to customize driver behavior
# ============================================================================

CONFIG = {
    # Device connection (can also be set via D-Bus /Settings/TristarMPPT/...)
    'default_ip': '192.168.2.103',
    'default_modbus_port': 502,
    'default_slave_id': 1,
    'default_device_instance': 0,
    'default_poll_interval_ms': 5000,  # Update interval (milliseconds)

    # Timing
    'state_save_interval_sec': 300,    # Save state.json every 5 minutes
    'watchdog_timeout_sec': 180,       # Mark disconnected after 3 min without Modbus
    'nightly_reset_hour': 3,           # TriStar comm reset at 03:00 local time

    # Voltage override settings
    'excess_power_threshold': 100,          # Watts - minimum excess before override considered
    'max_voltage_override_voltage': 28.7,   # Volts - SAFETY LIMIT (driver never exceeds this)
    'max_voltage_override_time': 7200,      # Seconds/day - max time at override voltage (2 hours)
    'battery_full_current': 2.0,            # Amps - tail current threshold for full detection
    'tail_current_time': 300,               # Seconds - sustained tail current time (5 min)

    # Device identification
    'custom_name': 'TriStar MPPT 60',
}

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

# EEPROM registers (read/write) - Charge settings
REG_EEPROM_EV_ABSORP = 0xE000        # Absorption voltage
REG_EEPROM_EV_FLOAT = 0xE001         # Float voltage
REG_EEPROM_ET_ABSORP = 0xE002        # Absorption time (seconds)
REG_EEPROM_EV_FLOAT_CANCEL = 0xE005  # Float cancel voltage

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
    9: 4    # SLAVE -> ABSORPTION (actively regulating to target voltage)
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
                'ip_address': ['/Settings/TristarMPPT/IPAddress', CONFIG['default_ip'], 0, 0],
                'modbus_port': ['/Settings/TristarMPPT/PortNumber', CONFIG['default_modbus_port'], 1, 65535],
                'poll_interval': ['/Settings/TristarMPPT/Interval', CONFIG['default_poll_interval_ms'], 1000, 60000],
                'slave_id': ['/Settings/TristarMPPT/SlaveID', CONFIG['default_slave_id'], 1, 247],
                'device_instance': ['/Settings/TristarMPPT/DeviceInstance', CONFIG['default_device_instance'], 0, 255],
                'state_save_interval': ['/Settings/TristarMPPT/StateSaveInterval', CONFIG['state_save_interval_sec'], 60, 3600],
                'watchdog_timeout': ['/Settings/TristarMPPT/WatchdogTimeout', CONFIG['watchdog_timeout_sec'], 30, 600],
                'nightly_reset_hour': ['/Settings/TristarMPPT/NightlyResetHour', CONFIG['nightly_reset_hour'], 0, 23],
                'excess_power_threshold': ['/Settings/TristarMPPT/ExcessPowerThreshold', CONFIG['excess_power_threshold'], -1, 5000],
                'max_voltage_override_voltage': ['/Settings/TristarMPPT/MaxVoltageOverrideVoltage', CONFIG['max_voltage_override_voltage'], 24.0, 32.0],
                'max_voltage_override_time': ['/Settings/TristarMPPT/MaxVoltageOverrideTime', CONFIG['max_voltage_override_time'], 0, 86400],
                'battery_full_current': ['/Settings/TristarMPPT/BatteryFullCurrent', CONFIG['battery_full_current'], 0.0, 100.0],
                'tail_current_time': ['/Settings/TristarMPPT/TailCurrentTime', CONFIG['tail_current_time'], 0, 3600],
                # Charge profile settings (Summer)
                'profile_summer_absorption_v': ['/Settings/TristarMPPT/ChargeProfiles/Summer/AbsorptionVoltage', 28.4, 26.0, 32.0],
                'profile_summer_float_v': ['/Settings/TristarMPPT/ChargeProfiles/Summer/FloatVoltage', 27.2, 24.0, 30.0],
                'profile_summer_absorption_time': ['/Settings/TristarMPPT/ChargeProfiles/Summer/AbsorptionTime', 7200, 0, 86400],
                'profile_summer_float_cancel_v': ['/Settings/TristarMPPT/ChargeProfiles/Summer/FloatCancelVoltage', 26.0, 0.0, 32.0],
                # Charge profile settings (Winter)
                'profile_winter_absorption_v': ['/Settings/TristarMPPT/ChargeProfiles/Winter/AbsorptionVoltage', 28.8, 26.0, 32.0],
                'profile_winter_float_v': ['/Settings/TristarMPPT/ChargeProfiles/Winter/FloatVoltage', 27.6, 24.0, 30.0],
                'profile_winter_absorption_time': ['/Settings/TristarMPPT/ChargeProfiles/Winter/AbsorptionTime', 9000, 0, 86400],
                'profile_winter_float_cancel_v': ['/Settings/TristarMPPT/ChargeProfiles/Winter/FloatCancelVoltage', 26.4, 0.0, 32.0],
                # Charge profile settings (Custom)
                'profile_custom_absorption_v': ['/Settings/TristarMPPT/ChargeProfiles/Custom/AbsorptionVoltage', 28.6, 26.0, 32.0],
                'profile_custom_float_v': ['/Settings/TristarMPPT/ChargeProfiles/Custom/FloatVoltage', 27.4, 24.0, 30.0],
                'profile_custom_absorption_time': ['/Settings/TristarMPPT/ChargeProfiles/Custom/AbsorptionTime', 8400, 0, 86400],
                'profile_custom_float_cancel_v': ['/Settings/TristarMPPT/ChargeProfiles/Custom/FloatCancelVoltage', 26.2, 0.0, 32.0],
            },
            eventCallback=self._setting_changed
        )

        # Device state
        self.initialized = False

        # Scaling factors (read from device)
        self.v_pu = 0.0
        self.i_pu = 0.0
        self.system_voltage_scale = 1  # Multiplier for EEPROM voltages (1=12V, 2=24V, 4=48V)

        # Static device info
        self.firmware_version = 0
        self.hardware_version = ""
        self.serial_number = ""
        self.product_name = ""

        # Bulk charge timing
        self.t_bulk_ms = 0
        self.last_update = time()

        # Periodic state saving
        self.last_state_save_time = time()
        self.state_save_interval = self.settings['state_save_interval']

        # Connection watchdog (track last successful read)
        self.last_successful_read = time()
        self.watchdog_timeout = self.settings['watchdog_timeout']

        # Statistics for diagnostics
        self.successful_reads = 0
        self.failed_reads = 0
        self.consecutive_failures = 0

        # Exponential backoff on persistent failures
        self.backoff_factor = 1  # Multiplier for poll interval (1x, 2x, 4x)

        # EEPROM read optimization (avoid reading every poll per Morningstar recommendation)
        self.eeprom_refresh_needed = True   # Flag to refresh charge settings (read at startup)
        self.eeprom_kwh_counter = 0         # Counter for lifetime kWh reads
        self.eeprom_kwh_interval = 360      # Read every 30 min (360 × 5s = 1800s)

        # Voltage override control
        self.pending_voltage_override = None       # Register value to write (None = disabled)
        self.last_voltage_override_write = 0       # Timestamp of last write
        self.voltage_override_interval = 30        # Write every 30 seconds
        self.voltage_override_active = False       # Is override currently active?

        # Time tracking for voltage override
        self.time_at_override_today = 0            # Accumulated seconds at override today (deprecated)
        self.time_above_target_accumulated = 0     # Cumulative seconds at or above target voltage
        self.last_override_time_update = 0         # Timestamp for delta calculation
        self.override_start_time = None            # When battery first reached target voltage

        # Tail current detection
        self.tail_current_start_time = None        # When tail current condition started
        self.stop_reason = ""                      # Why override stopped

        # Current override control (PDU register 88 - Ib_ref_slave, Logical 89)
        self.pending_current_override = None       # Register value to write (None = disabled)
        self.last_current_override_write = 0       # Timestamp of last write
        self.current_override_active = False       # Is current override active?

        # Load persistent state (total yield and 30-day history)
        self.state = self._load_state()

        # Ensure lifetime tracking exists in state (for backwards compatibility)
        if 'lifetime' not in self.state:
            self.state['lifetime'] = {
                "max_pv_voltage": 0.0,
                "max_battery_voltage": 0.0,
                "min_battery_voltage": 999.0
            }

        # Ensure today tracking exists in state (for backwards compatibility)
        if 'today' not in self.state:
            self.state['today'] = {
                "max_battery_current": 0.0,
                "max_power": 0.0,
                "max_pv_voltage": 0.0,
                "max_battery_voltage": 0.0,
                "min_battery_voltage": 999.0,
                "time_bulk": 0
            }

        # Daily value trackers (reset at midnight) - load from state to preserve across restarts
        self.daily_max_battery_current = self.state['today'].get('max_battery_current', 0.0)
        self.daily_max_power = self.state['today'].get('max_power', 0.0)
        self.daily_max_battery_voltage = self.state['today'].get('max_battery_voltage', 0.0)
        self.daily_min_battery_voltage = self.state['today'].get('min_battery_voltage', 999.0)
        self.daily_max_pv_voltage = self.state['today'].get('max_pv_voltage', 0.0)

        # Load time_bulk from state (tracked by driver, not Modbus)
        time_bulk_minutes = self.state['today'].get('time_bulk', 0)
        self.t_bulk_ms = time_bulk_minutes * 60 * 1000  # Convert minutes to milliseconds

        # Nightly reset tracking
        self.last_reset_date = self.state.get('current_date')

        # Daily register reset detection (for post-midnight, pre-sunrise handling)
        # Load from state (persists across restarts to know if Modbus is valid)
        self.daily_register_has_reset = self.state.get('daily_register_has_reset', True)
        self.last_daily_register_value = 0
        self.first_update_done = False  # Flag to detect very first update after restart

        # Daily Wh offset (for handling controller resets before midnight)
        # When controller resets, REG_WHC_DAILY goes to 0, but we're still in valid period
        # Offset = Wh before reset, so actual = offset + register
        self.daily_wh_offset = self.state.get('daily_wh_offset', 0.0)

        # Daily time offsets (same principle as daily_wh_offset, but for charge stage timers)
        self.time_abs_offset = self.state.get('time_abs_offset', 0)
        self.time_float_offset = self.state.get('time_float_offset', 0)
        self.time_eq_offset = self.state.get('time_eq_offset', 0)

        # Load voltage override state (for backwards compatibility)
        if 'voltage_override' not in self.state:
            self.state['voltage_override'] = {
                "time_used_today": 0,
                "current_date": self.state.get('current_date'),
                "stop_reason": ""
            }

        # Load voltage override time tracking from state
        self.time_at_override_today = self.state['voltage_override'].get('time_used_today', 0)
        self.stop_reason = self.state['voltage_override'].get('stop_reason', "")

        # Track which history days have D-Bus paths created (for dynamic path creation)
        self.history_days_created = set()  # Set of day indices (1-29) that have paths

        # Charge profile management (EEPROM-based permanent settings)
        self.charge_profiles = self._load_charge_profiles()
        self.profile_apply_status = "idle"
        self.profile_apply_error = ""
        self.profile_apply_progress = 0
        self.profile_apply_in_progress = False  # Lock flag for Modbus exclusivity
        self.main_loop_paused_reason = ""

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
            "daily_register_has_reset": True,  # Assume Modbus valid initially
            "daily_wh_offset": 0.0,  # Offset for controller resets before midnight
            "time_abs_offset": 0,    # Absorption time before last controller reset
            "time_float_offset": 0,  # Float time before last controller reset
            "time_eq_offset": 0,     # Equalize time before last controller reset
            "today": {
                "yield": 0.0,
                "max_battery_current": 0.0,
                "max_power": 0.0,
                "max_pv_voltage": 0.0,
                "max_battery_voltage": 0.0,
                "min_battery_voltage": 999.0,
                "time_bulk": 0,
                "time_absorption": 0,
                "time_float": 0,
                "time_equalize": 0
            },
            "history": [],  # Will grow to 30 days (Day 1-30)
            "lifetime": {
                "max_pv_voltage": 0.0,
                "max_battery_voltage": 0.0,
                "min_battery_voltage": 999.0  # High initial value so first real value will be lower
            },
            "voltage_override": {
                "time_used_today": 0,         # Seconds at override voltage today
                "current_date": self._get_local_date(),  # Date for midnight reset
                "stop_reason": ""             # Last stop reason
            }
        }

    def _save_state(self):
        """Save state to JSON file atomically"""
        try:
            # Create directory if needed
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

            # Update timestamp
            self.state['last_update'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

            # Write atomically (temp file + rename)
            temp_file = STATE_FILE.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(self.state, f, indent=2)
            temp_file.replace(STATE_FILE)

            logging.debug("State saved successfully")

        except Exception as e:
            logging.error(f"Error saving state: {e}")

    def _get_local_date(self):
        """Get current date in local timezone from D-Bus timezone setting"""
        try:
            # Read timezone from Venus OS D-Bus settings (e.g., 'Europe/Paris')
            bus = dbus.SystemBus()
            settings = bus.get_object('com.victronenergy.settings', '/Settings/System/TimeZone')
            tz_string = settings.GetValue()

            # Temporarily set TZ environment variable to get correct local time
            old_tz = os.environ.get('TZ', '')
            os.environ['TZ'] = tz_string
            time_module.tzset()

            # Get local date in the configured timezone
            local_date = time_module.strftime('%Y-%m-%d', time_module.localtime())

            # Restore original TZ setting
            if old_tz:
                os.environ['TZ'] = old_tz
            else:
                if 'TZ' in os.environ:
                    del os.environ['TZ']
            time_module.tzset()

            return local_date

        except Exception as e:
            logging.error(f"Error getting local date from timezone: {e}")
            # Fallback to UTC date
            return datetime.now().date().isoformat()

    def _update_historical_days(self):
        """Update D-Bus paths for days 1-29 from state file (create paths dynamically)"""
        try:
            history = self.state.get('history', [])

            # Update DaysAvailable: number of historical days + today (day 0)
            days_available = min(len(history) + 1, 31)  # Max 31 days (Day 0 + Days 1-30)
            self.dbus['/History/Overall/DaysAvailable'] = days_available

            # Only create paths for days that have actual data (days 1-30)
            # Venus OS shows 31 days total: Day 0 (today) + Days 1-30 (historical)
            for history_index in range(len(history)):
                day_index = history_index + 1  # history[0] = day 1 (yesterday)

                if day_index > 30:
                    break  # Only support up to 30 historical days

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

                # Snapshot yesterday's final values from state (not memory)
                # This ensures correct values even if driver restarted between midnight and sunrise
                # Values are saved every 5 minutes, so state has the latest values
                yesterday_snapshot = {
                    "date": self.last_reset_date,
                    "yield": current_daily_kwh,  # Use REG_WHC_DAILY before it resets
                    "max_power": self.state['today']['max_power'],
                    "max_pv_voltage": self.state['today']['max_pv_voltage'],
                    "max_battery_voltage": self.state['today']['max_battery_voltage'],
                    "min_battery_voltage": self.state['today']['min_battery_voltage'] if self.state['today']['min_battery_voltage'] < 999 else 0.0,
                    "max_battery_current": self.state['today']['max_battery_current'],
                    "time_bulk": int(self.t_bulk_ms / (1000 * 60)),
                    "time_absorption": self.state['today']['time_absorption'],
                    "time_float": self.state['today']['time_float'],
                    "time_equalize": self.state['today']['time_equalize']
                }

                # Add yesterday's production to total
                self.state['total_yield_kwh'] += current_daily_kwh
                logging.info(f"Added {current_daily_kwh:.3f} kWh to total. New total: {self.state['total_yield_kwh']:.2f} kWh")

                # Insert yesterday at position 0, shifting everything
                self.state['history'].insert(0, yesterday_snapshot)

                # Keep only 30 days of history (day 0 = today, days 1-30 = history)
                if len(self.state['history']) > 30:
                    self.state['history'] = self.state['history'][:30]
                    logging.info(f"Trimmed history to 30 days (oldest day removed)")

                # Update current date
                self.last_reset_date = current_date
                self.state['current_date'] = current_date

                # Reset daily trackers for new day (both memory and state)
                self.daily_max_battery_current = 0.0
                self.daily_max_power = 0.0
                self.daily_max_battery_voltage = 0.0
                self.daily_min_battery_voltage = 999.0
                self.daily_max_pv_voltage = 0.0
                self.t_bulk_ms = 0

                # Reset today's values in state as well
                self.state['today'] = {
                    "yield": 0.0,
                    "max_battery_current": 0.0,
                    "max_power": 0.0,
                    "max_pv_voltage": 0.0,
                    "max_battery_voltage": 0.0,
                    "min_battery_voltage": 999.0,
                    "time_bulk": 0,
                    "time_absorption": 0,
                    "time_float": 0,
                    "time_equalize": 0
                }

                # Reset register flag (expect register to reset when sun comes up)
                self.daily_register_has_reset = False
                self.state['daily_register_has_reset'] = False

                # Reset voltage override time tracking for new day
                self.time_at_override_today = 0
                self.state['voltage_override']['time_used_today'] = 0
                self.state['voltage_override']['current_date'] = current_date
                logging.info("Voltage override time counter reset for new day")

                # Reset daily Wh offset for new day
                self.daily_wh_offset = 0.0
                self.state['daily_wh_offset'] = 0.0
                logging.info("Daily Wh offset reset for new day")

                # Reset daily time offsets for new day
                self.time_abs_offset = 0
                self.time_float_offset = 0
                self.time_eq_offset = 0
                self.state['time_abs_offset'] = 0
                self.state['time_float_offset'] = 0
                self.state['time_eq_offset'] = 0

                # Save state to file
                self._save_state()

                # Update D-Bus paths immediately for days 1-29 (show rotated history in UI)
                self._update_historical_days()

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
        s.add_path('/Mode', 1, writeable=True, onchangecallback=self._on_mode_change)  # 1=On, 4=Off
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

        # History - Overall (lifetime) - Values updated from state in update loop
        s.add_path('/History/Overall/MaxPvVoltage', 0.0, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/History/Overall/MaxBatteryVoltage', 0.0, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/History/Overall/MinBatteryVoltage', 0.0, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/History/Overall/LastError1', 0)  # Error history not yet implemented
        s.add_path('/History/Overall/LastError2', 0)
        s.add_path('/History/Overall/LastError3', 0)
        s.add_path('/History/Overall/LastError4', 0)

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
        # This prevents Venus OS from thinking we have 31 days of data when we don't

        # Total yield
        s.add_path('/Yield/User', 0.0, gettextcallback=lambda p, v: f"{v}kWh")
        s.add_path('/Yield/System', 0.0, gettextcallback=lambda p, v: f"{v}kWh")

        # Control (coils) - writable
        s.add_path('/Control/EqualizeTriggered', 0, writeable=True, onchangecallback=self._on_coil_write)
        s.add_path('/Control/ChargerDisconnect', 0, writeable=True, onchangecallback=self._on_coil_write)
        s.add_path('/Control/ResetController', 0, writeable=True, onchangecallback=self._on_coil_write)
        s.add_path('/Control/ResetCommServer', 0, writeable=True, onchangecallback=self._on_coil_write)

        # Voltage override control - writable (non-persistent, starts at 0)
        s.add_path('/Control/VoltageOverride', 0.0, writeable=True, onchangecallback=self._on_voltage_override_write, gettextcallback=lambda p, v: f"{v}V")

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

        # Voltage override monitoring
        s.add_path('/Custom/VoltageOverride/ExcessPower', 0, writeable=False, gettextcallback=lambda p, v: f"{v}W")
        s.add_path('/Custom/VoltageOverride/Active', False, writeable=False)
        s.add_path('/Custom/VoltageOverride/TimeAtTargetVoltage', 0, writeable=False)  # Seconds at target voltage
        s.add_path('/Custom/VoltageOverride/TailCurrentTimer', 0, writeable=False)  # Seconds
        s.add_path('/Custom/VoltageOverride/StopReason', "", writeable=False)  # Text: TimeLimit/BatteryFull/UserDisabled
        s.add_path('/Custom/VoltageOverride/CurrentVoltage', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/Custom/VoltageOverride/RegisterReadback', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")  # Actual value read from PDU register 89 (vb_ref_slave)

        # Current override control and monitoring (PDU register 88 - Ib_ref_slave, Logical 89)
        s.add_path('/Control/CurrentOverride', 0.0, writeable=True, onchangecallback=self._on_current_override_write, gettextcallback=lambda p, v: f"{v}A")
        s.add_path('/Custom/CurrentOverride/Active', False, writeable=False)
        s.add_path('/Custom/CurrentOverride/CurrentValue', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}A")
        s.add_path('/Custom/CurrentOverride/RegisterReadback', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}A")  # Actual value read from PDU register 88 (Ib_ref_slave)

        # Manual control register monitoring (registers that might interfere with slave mode)
        s.add_path('/Custom/ManualControl/VaRefFixed', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")  # Register 91 - Array voltage fixed target
        s.add_path('/Custom/ManualControl/VaRefFixedPct', 0, writeable=False, gettextcallback=lambda p, v: f"{v}%")  # Register 92 - Array voltage % of Voc

        # Battery diagnostics
        s.add_path('/Custom/Battery/TerminalVoltage', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/Custom/Battery/SenseVoltage', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/Custom/Battery/CurrentFast', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}A")
        s.add_path('/Custom/Battery/VoltageSlow', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")

        # EEPROM charge settings (configured absorption/equalize voltages and limits)
        s.add_path('/Custom/EEPROM/AbsorptionVoltage', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/Custom/EEPROM/FloatVoltage', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/Custom/EEPROM/AbsorptionTime', 0, writeable=False, gettextcallback=lambda p, v: f"{v}s")
        s.add_path('/Custom/EEPROM/FloatCancelVoltage', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/Custom/EEPROM/EqualizeVoltage', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/Custom/EEPROM/TempCompensation', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V/C")
        s.add_path('/Custom/EEPROM/MaxRegulationLimit', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}V")

        # Charge profile management (EEPROM profile apply control and status)
        s.add_path('/Control/ApplyChargeProfile', '', writeable=True, onchangecallback=self._on_apply_profile_requested)
        s.add_path('/Custom/ChargeProfile/ApplyStatus', 'idle', writeable=False)
        s.add_path('/Custom/ChargeProfile/LastApplied', '', writeable=False)
        s.add_path('/Custom/ChargeProfile/LastError', '', writeable=False)
        s.add_path('/Custom/ChargeProfile/ProgressPercent', 0, writeable=False)

        # EEPROM lifetime charge counters (TriStar's internal counters)
        s.add_path('/Custom/EEPROM/ChargeKwhResetable', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}kWh")
        s.add_path('/Custom/EEPROM/ChargeKwhTotal', 0.0, writeable=False, gettextcallback=lambda p, v: f"{v}kWh")

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
        s.add_path('/Custom/Daily/ChargeWh', 0, writeable=False, gettextcallback=lambda p, v: f"{v}Wh")  # Raw Modbus REG_WHC_DAILY
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
        elif setting == 'state_save_interval':
            # Update state save interval
            self.state_save_interval = new
            logging.info(f"State save interval updated to {new} seconds")
        elif setting == 'watchdog_timeout':
            # Update watchdog timeout
            self.watchdog_timeout = new
            logging.info(f"Watchdog timeout updated to {new} seconds")
        elif setting == 'nightly_reset_hour':
            # Update nightly reset hour (will take effect at next reset check)
            logging.info(f"Nightly reset hour updated to {new} (effective at next reset check)")

    def _on_mode_change(self, path, value):
        """Called when /Mode is changed via D-Bus (1=On, 4=Off)"""
        logging.info(f"Mode change request: {path} = {value}")

        if value == 1:
            # Mode = On → Clear COIL_DISCONNECT (allow charging)
            logging.info("Setting charger to ON (clearing disconnect coil)")
            success = self.write_coil(COIL_DISCONNECT, False)
            if success:
                self.dbus['/Mode'] = 1
                logging.info("Charger enabled successfully")
            else:
                logging.error("Failed to enable charger")
        elif value == 4:
            # Mode = Off → Set COIL_DISCONNECT (force disconnect)
            logging.info("Setting charger to OFF (setting disconnect coil)")
            success = self.write_coil(COIL_DISCONNECT, True)
            if success:
                self.dbus['/Mode'] = 4
                logging.info("Charger disabled successfully")
            else:
                logging.error("Failed to disable charger")
        else:
            logging.warning(f"Invalid mode value: {value} (expected 1 or 4)")
            return value  # Return current value unchanged

        return value

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

    def _on_voltage_override_write(self, path, value):
        """Called when voltage override is written via D-Bus"""
        logging.info(f"Voltage override request: {path} = {value}")

        try:
            voltage = float(value)

            # Disable override if negative value or zero
            if voltage <= 0:
                self.pending_voltage_override = None
                self.voltage_override_active = False
                self.stop_reason = "UserDisabled"
                self.override_start_time = None
                self.tail_current_start_time = None
                self.time_above_target_accumulated = 0
                logging.info("Voltage override disabled by user")
                # Immediately write -1 to disable slave mode
                self.write_holding_register(89, -1)  # PDU 89 = vb_ref_slave
                # Also clear array voltage registers to ensure MPPT is enabled
                self.write_holding_register(90, -1)  # PDU 90 = va_ref_fixed
                self.write_holding_register(91, -1)  # PDU 91 = va_ref_fixed_pct
                # Update D-Bus paths immediately to show disabled
                self.dbus['/Custom/VoltageOverride/CurrentVoltage'] = 0.0
                self.dbus['/Custom/VoltageOverride/Active'] = False
                self.dbus['/Custom/CurrentOverride/CurrentValue'] = 0.0
                self.dbus['/Custom/CurrentOverride/Active'] = False
                return -1  # Show -1 on D-Bus path to indicate disabled

            # Validate against safety limit (CRITICAL)
            max_voltage = self.settings['max_voltage_override_voltage']
            if voltage > max_voltage:
                logging.error(f"Voltage override REJECTED: {voltage}V > max {max_voltage}V (safety limit)")
                return False  # Reject write

            # Convert voltage to register format
            register_value = self.voltage_to_register(voltage)
            self.pending_voltage_override = register_value
            self.voltage_override_active = True

            # Write voltage override to PDU 89 only (current override not needed for slave mode)
            success = self.write_holding_register(89, register_value)  # PDU 89 = vb_ref_slave
            if success:
                self.last_voltage_override_write = time()  # Reset timer for next periodic write (30s from now)
                # Update D-Bus paths immediately
                actual_voltage = self.register_to_voltage(register_value)
                self.dbus['/Custom/VoltageOverride/CurrentVoltage'] = round(actual_voltage, 2)
                self.dbus['/Custom/VoltageOverride/Active'] = True

                # Read back PDU 89 to verify write
                sleep(0.1)  # Give TriStar time to process
                readback = self.read_holding_registers(89, 1)  # PDU 89 = vb_ref_slave
                if readback is not None:
                    readback_value = self._to_signed(readback[0])
                    readback_voltage = self.register_to_voltage(readback_value)
                    self.dbus['/Custom/VoltageOverride/RegisterReadback'] = round(readback_voltage, 2)
                    if abs(readback_voltage - actual_voltage) > 0.1:
                        logging.warning(f"PDU 89 readback mismatch: wrote {actual_voltage:.2f}V, read {readback_voltage:.2f}V (reg: {readback_value})")
                    else:
                        logging.info(f"PDU 89 verified: {readback_voltage:.2f}V (reg: {readback_value})")
                else:
                    logging.warning("Failed to read back PDU 89")

            # Clear stop reason when user enables
            self.stop_reason = ""

            # Return actual voltage that will be written (may differ slightly due to scaling)
            actual_voltage = self.register_to_voltage(register_value)
            logging.info(f"Voltage override set to {voltage}V (actual: {actual_voltage:.2f}V, register: {register_value})")
            return round(actual_voltage, 2)

        except (ValueError, TypeError) as e:
            logging.error(f"Invalid voltage value: {e}")
            return False

    def _on_current_override_write(self, path, value):
        """Called when current override is written via D-Bus"""
        logging.info(f"Current override request: {path} = {value}")

        try:
            current = float(value)

            # Disable override if negative value or zero
            if current <= 0:
                self.pending_current_override = None
                self.current_override_active = False
                logging.info("Current override disabled by user - also disabling voltage override (TriStar requires both)")
                # Immediately write -1 to BOTH registers to disable slave mode
                # (TriStar requires both registers to be maintained together)
                self.write_holding_register(88, -1)  # PDU 88 = Ib_ref_slave
                self.write_holding_register(89, -1)  # PDU 89 = vb_ref_slave
                # Also clear array voltage registers to ensure MPPT is enabled
                self.write_holding_register(90, -1)  # PDU 90 = va_ref_fixed
                self.write_holding_register(91, -1)  # PDU 91 = va_ref_fixed_pct
                # Also disable voltage override
                self.pending_voltage_override = None
                self.voltage_override_active = False
                # Update D-Bus paths immediately to show disabled
                self.dbus['/Custom/CurrentOverride/CurrentValue'] = 0.0
                self.dbus['/Custom/CurrentOverride/Active'] = False
                self.dbus['/Custom/VoltageOverride/CurrentVoltage'] = 0.0
                self.dbus['/Custom/VoltageOverride/Active'] = False
                return -1  # Show -1 on D-Bus path to indicate disabled

            # Convert current to register format
            register_value = self.current_to_register(current)
            self.pending_current_override = register_value
            self.current_override_active = True

            # CRITICAL: TriStar requires BOTH PDU 88 (current) AND 89 (voltage) to be updated
            # together every <60s to maintain slave mode. Auto-enable voltage override with max safe limit.
            if self.pending_voltage_override is None:
                # Set voltage override to max safe voltage from settings
                voltage_limit = self.settings['max_voltage_override_voltage']
                voltage_register_value = self.voltage_to_register(voltage_limit)
                self.pending_voltage_override = voltage_register_value
                self.voltage_override_active = True
                logging.info(f"Auto-enabling voltage override at {voltage_limit}V to maintain slave mode")
                # Write voltage override immediately
                self.write_holding_register(89, voltage_register_value)  # PDU 89 = vb_ref_slave
                self.last_voltage_override_write = time()
                self.dbus['/Custom/VoltageOverride/CurrentVoltage'] = voltage_limit
                self.dbus['/Custom/VoltageOverride/Active'] = True

            # Immediately write to register (don't wait for periodic update)
            success = self.write_holding_register(88, register_value)  # PDU 88 = Ib_ref_slave
            if success:
                self.last_current_override_write = time()  # Reset timer for next periodic write (30s from now)
                # Update D-Bus paths immediately
                actual_current = self.register_to_current(register_value)
                self.dbus['/Custom/CurrentOverride/CurrentValue'] = round(actual_current, 2)
                self.dbus['/Custom/CurrentOverride/Active'] = True

                # Read back PDU 88 to verify write
                sleep(0.1)  # Give TriStar time to process
                readback = self.read_holding_registers(88, 1)  # PDU 88 = Ib_ref_slave
                if readback is not None:
                    readback_value = self._to_signed(readback[0])
                    readback_current = self.register_to_current(readback_value)
                    self.dbus['/Custom/CurrentOverride/RegisterReadback'] = round(readback_current, 2)
                    if abs(readback_current - actual_current) > 0.5:
                        logging.warning(f"PDU 88 readback mismatch: wrote {actual_current:.2f}A, read {readback_current:.2f}A (reg: {readback_value})")
                    else:
                        logging.info(f"PDU 88 verified: {readback_current:.2f}A (reg: {readback_value})")
                else:
                    logging.warning("Failed to read back PDU 88")

            # Return actual current that will be written (may differ slightly due to scaling)
            actual_current = self.register_to_current(register_value)
            logging.info(f"Current override set to {current}A (actual: {actual_current:.2f}A, register: {register_value})")
            return round(actual_current, 2)

        except (ValueError, TypeError) as e:
            logging.error(f"Invalid current value: {e}")
            return False

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

    def read_holding_registers(self, address, count):
        """
        Read holding registers (writable registers like Vb_ref_slave)
        Uses same pattern as read_input_registers: connect → read → close
        """
        ip = self.settings['ip_address']
        port = self.settings['modbus_port']
        slave_id = self.settings['slave_id']

        for attempt in range(5):
            client = ModbusTcpClient(host=ip, port=port, timeout=1, retries=0)

            try:
                if not client.connect():
                    if attempt < 4:
                        logging.debug(f"Connection failed, retry {attempt + 1}/5")
                        continue
                    else:
                        logging.error(f"Failed to connect for holding register read after 5 retries")
                        return None

                # Read holding registers
                result = client.read_holding_registers(
                    address=address,
                    count=count,
                    unit=slave_id
                )

                if result.isError():
                    if attempt < 4:
                        logging.debug(f"Modbus error reading holding register, retry {attempt + 1}/5")
                        client.close()
                        continue
                    else:
                        logging.error(f"Modbus error reading holding register after 5 retries")
                        client.close()
                        return None

                # Success
                registers = result.registers
                client.close()
                return registers

            except Exception as e:
                if attempt < 4:
                    logging.debug(f"Exception reading holding register, retry {attempt + 1}/5: {e}")
                else:
                    logging.error(f"Exception reading holding register after 5 retries: {e}")

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

    def write_holding_register(self, address, value):
        """
        Write single holding register with retry logic

        Args:
            address: Register address (e.g., 90 for Vb_ref_slave)
            value: 16-bit signed integer value (-32768 to 32767)

        Returns:
            True on success, False on failure
        """
        ip = self.settings['ip_address']
        port = self.settings['modbus_port']
        slave_id = self.settings['slave_id']

        # Convert signed to unsigned for pymodbus (expects 0-65535)
        # -1 becomes 65535 (0xFFFF) via two's complement
        if value < 0:
            unsigned_value = (1 << 16) + value  # 65536 + value
        else:
            unsigned_value = value

        for attempt in range(5):
            client = ModbusTcpClient(host=ip, port=port, timeout=1, retries=0)

            try:
                if not client.connect():
                    if attempt < 4:
                        logging.debug(f"Connection failed, retry {attempt + 1}/5")
                        continue
                    else:
                        logging.error(f"Failed to connect for register {address} write after 5 retries")
                        return False

                result = client.write_register(address=address, value=unsigned_value, unit=slave_id)

                if result.isError():
                    if attempt < 4:
                        client.close()
                        continue
                    else:
                        logging.error(f"Register {address} write error after 5 retries")
                        client.close()
                        return False

                client.close()
                # Log register 90 (Vb_ref_slave) writes at INFO level for visibility
                if address == 90:
                    if value == -1 or unsigned_value >= 65535:
                        logging.info(f"Successfully wrote register {address} = {value} (disable slave mode)")
                    else:
                        logging.info(f"Successfully wrote register {address} = {value} (enable slave mode)")
                else:
                    logging.debug(f"Successfully wrote register {address} = {value}")
                return True

            except Exception as e:
                if attempt < 4:
                    logging.debug(f"Exception on attempt {attempt + 1}: {e}")
                    continue
                else:
                    logging.error(f"Exception writing register {address} after 5 retries: {e}")
                    return False

        return False

    def voltage_to_register(self, voltage_v):
        """
        Convert real voltage (volts) to TriStar register format

        Args:
            voltage_v: Voltage in volts (e.g., 28.5)

        Returns:
            16-bit signed integer for Modbus register
        """
        if voltage_v < 0:  # Negative voltage disables override
            return -1

        # Apply v_pu scaling: register = voltage * 32768 / v_pu
        register_value = int(voltage_v * 32768.0 / self.v_pu)

        # Clamp to 16-bit signed range (-32768 to 32767)
        register_value = max(-32768, min(32767, register_value))

        return register_value

    def register_to_voltage(self, register_value):
        """
        Convert register value back to voltage for verification

        Args:
            register_value: 16-bit signed integer from register

        Returns:
            Voltage in volts
        """
        if register_value < 0:
            return 0
        return register_value * self.v_pu / 32768.0

    def current_to_register(self, current_a):
        """
        Convert real current (amps) to TriStar register format

        Args:
            current_a: Current in amps (e.g., 50.0)

        Returns:
            16-bit signed integer for Modbus register
        """
        if current_a < 0:  # Negative current disables override
            return -1

        # Apply i_pu scaling: register = current * 32768 / i_pu
        register_value = int(current_a * 32768.0 / self.i_pu)

        # Clamp to 16-bit signed range (-32768 to 32767)
        register_value = max(-32768, min(32767, register_value))

        return register_value

    def register_to_current(self, register_value):
        """
        Convert register value back to current for verification

        Args:
            register_value: 16-bit signed integer from register

        Returns:
            Current in amps
        """
        if register_value < 0:
            return 0
        return register_value * self.i_pu / 32768.0

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

        # Detect system voltage (12V/24V/48V) from V_PU for EEPROM scaling
        # V_PU ≈ 78 for 12V, ≈156 for 24V, ≈312 for 48V
        if self.v_pu < 100:
            self.system_voltage_scale = 1  # 12V system
        elif self.v_pu < 200:
            self.system_voltage_scale = 2  # 24V system
        else:
            self.system_voltage_scale = 4  # 48V system
        logging.info(f"Detected {self.system_voltage_scale * 12}V system (EEPROM scale factor: {self.system_voltage_scale})")

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

        # Read EEPROM values at startup (charge settings + lifetime kWh)
        self._read_eeprom_charge_settings()
        self._read_eeprom_lifetime_kwh()

        self.initialized = True
        return True

    def update(self):
        """Periodic update - read values and publish to D-Bus"""
        # Only log if update is delayed (> 10 sec since last update)
        current_time = time_module.time()
        if hasattr(self, 'last_update_time'):
            time_since_last = current_time - self.last_update_time
            if time_since_last > 10:
                logging.warning(f"update() delayed: {time_since_last:.1f}s since last update")
        else:
            logging.info("update() called (first time)")

        self.last_update_time = current_time

        # Check if profile apply is in progress (avoid Modbus collision)
        if self.profile_apply_in_progress:
            # Main loop paused - profile apply thread has exclusive Modbus access
            if self.main_loop_paused_reason:
                logging.debug(f"Main loop paused: {self.main_loop_paused_reason}")
            return True  # Continue timer, but skip Modbus operations

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

            # Calculate bulk time (only increment during BULK, reset happens at midnight)
            if cs_raw == CS_BULK:
                self.t_bulk_ms += dt_ms

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
            elif cs == 3:
                self.dbus['/MppOperationMode'] = 2  # Bulk - MPPT tracking active
            else:
                self.dbus['/MppOperationMode'] = 1  # Absorption/Float/Equalize - V/I limited

            # Custom TriStar-specific values
            self.dbus['/Custom/ChargeState'] = cs_raw
            self.dbus['/Custom/ChargeStateText'] = CHARGE_STATE_TEXT.get(cs_raw, "UNKNOWN")
            self.dbus['/Custom/TargetRegulationVoltage'] = round(v_target, 2)

            # Battery diagnostics
            self.dbus['/Custom/Battery/TerminalVoltage'] = round(reg(REG_V_BAT_TERM) * self.v_pu / 32768.0, 2)
            self.dbus['/Custom/Battery/SenseVoltage'] = round(reg(REG_V_BAT_SENSE) * self.v_pu / 32768.0, 2)
            self.dbus['/Custom/Battery/CurrentFast'] = round(self._to_signed(reg(REG_I_CC_FAST)) * self.i_pu / 32768.0, 2)
            self.dbus['/Custom/Battery/VoltageSlow'] = round(reg(REG_V_BAT_SLOW) * self.v_pu / 32768.0, 2)

            # EEPROM reads REMOVED from main poll loop (per Morningstar recommendation)
            # Now called conditionally at end of update() - see _read_eeprom_charge_settings() and _read_eeprom_lifetime_kwh()

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

            # Update lifetime max/min from current values (saved once per day at midnight)
            self.state['lifetime']['max_pv_voltage'] = max(self.state['lifetime']['max_pv_voltage'], v_pv)
            self.state['lifetime']['max_battery_voltage'] = max(self.state['lifetime']['max_battery_voltage'], v_bat)
            if v_bat > 0:
                self.state['lifetime']['min_battery_voltage'] = min(self.state['lifetime']['min_battery_voltage'], v_bat)

            # Also update lifetime AND today based on TriStar's min/max (when data is valid)
            # TriStar tracks continuously, so it may have seen values we missed
            if self.daily_register_has_reset:
                today_max_pv_raw = reg(REG_V_PV_MAX) * self.v_pu / 32768.0
                today_max_batt_raw = reg(REG_V_BAT_MAX) * self.v_pu / 32768.0
                today_min_batt_raw = reg(REG_V_BAT_MIN) * self.v_pu / 32768.0

                # Update lifetime
                self.state['lifetime']['max_pv_voltage'] = max(self.state['lifetime']['max_pv_voltage'], today_max_pv_raw)
                self.state['lifetime']['max_battery_voltage'] = max(self.state['lifetime']['max_battery_voltage'], today_max_batt_raw)
                if today_min_batt_raw > 0:
                    self.state['lifetime']['min_battery_voltage'] = min(self.state['lifetime']['min_battery_voltage'], today_min_batt_raw)

                # Also update today's values from TriStar (more accurate than our 5-sec sampling)
                self.state['today']['max_pv_voltage'] = max(self.state['today']['max_pv_voltage'], today_max_pv_raw)
                self.state['today']['max_battery_voltage'] = max(self.state['today']['max_battery_voltage'], today_max_batt_raw)
                if today_min_batt_raw > 0 and today_min_batt_raw < 999:
                    self.state['today']['min_battery_voltage'] = min(self.state['today']['min_battery_voltage'], today_min_batt_raw)

            # Calculate daily yield with register reset detection
            # (used for history, yield calculation, and midnight rollover)
            current_daily_wh = reg(REG_WHC_DAILY)

            # Expose raw Modbus value on D-Bus for debugging/logging
            self.dbus['/Custom/Daily/ChargeWh'] = current_daily_wh

            # Detect register reset - THREE cases:
            # 1. Value decreased during valid period (daily_register_has_reset=True) = CONTROLLER RESET
            # 2. Value decreased post-midnight (daily_register_has_reset=False) = SUNRISE RESET
            # 3. Increased from 0 (no charging yesterday: 0 → 10 Wh)
            if current_daily_wh < self.last_daily_register_value:
                if self.daily_register_has_reset:
                    # Case 1: Controller reset during valid period (before midnight)
                    # Register dropped from X → 0, but we're still in same day
                    # Save current total as offset, keep using it
                    decrease = self.last_daily_register_value - current_daily_wh
                    if decrease > 50:  # Significant drop (>50 Wh), likely controller reset
                        current_total_wh = self.daily_wh_offset + self.last_daily_register_value
                        self.daily_wh_offset = current_total_wh
                        self.state['daily_wh_offset'] = self.daily_wh_offset
                        logging.warning(f"⚠️ Controller reset detected! REG_WHC_DAILY: {self.last_daily_register_value} → {current_daily_wh} Wh")
                        logging.warning(f"  Setting offset to {self.daily_wh_offset:.1f} Wh to preserve today's data")
                        logging.warning(f"  Future daily_wh = {self.daily_wh_offset:.1f} + REG_WHC_DAILY")

                        # Save time offsets (Modbus time registers also reset to 0 on controller reset)
                        self.time_abs_offset = self.state['today'].get('time_absorption', 0)
                        self.time_float_offset = self.state['today'].get('time_float', 0)
                        self.time_eq_offset = self.state['today'].get('time_equalize', 0)
                        self.state['time_abs_offset'] = self.time_abs_offset
                        self.state['time_float_offset'] = self.time_float_offset
                        self.state['time_eq_offset'] = self.time_eq_offset
                        logging.warning(f"  Time offsets set: abs={self.time_abs_offset}m, float={self.time_float_offset}m, eq={self.time_eq_offset}m")
                    else:
                        # Small decrease, might be noise - treat as normal sunrise reset
                        self.daily_register_has_reset = True
                        self.state['daily_register_has_reset'] = True
                        logging.info(f"Detected REG_WHC_DAILY reset (decrease): {self.last_daily_register_value} → {current_daily_wh} Wh")
                else:
                    # Case 2: Sunrise reset (post-midnight, pre-sunrise period)
                    self.daily_register_has_reset = True
                    self.state['daily_register_has_reset'] = True
                    logging.info(f"Detected REG_WHC_DAILY reset (sunrise): {self.last_daily_register_value} → {current_daily_wh} Wh")
                    logging.info(f"  Before: total={self.state['total_yield_kwh']:.3f} kWh, daily will become {current_daily_wh/1000.0:.3f} kWh")
            elif self.last_daily_register_value == 0 and current_daily_wh > 0 and not self.daily_register_has_reset:
                # Case 3: Register increased from 0 = charging started after zero-yield day
                # Safe because: if register is updating (0 → X), it's not frozen
                self.daily_register_has_reset = True
                self.state['daily_register_has_reset'] = True
                logging.info(f"Detected REG_WHC_DAILY reset (from zero): 0 → {current_daily_wh} Wh (no yield yesterday)")

            # On first update after restart: Trust state.json flag (persisted from before restart)
            # Don't set flag based on charge state - wait for actual register decrease detection!
            # This prevents spikes if driver restarts right at sunrise when register hasn't reset yet
            if not self.first_update_done:
                self.first_update_done = True
                logging.info(f"First update: cs_raw={cs_raw}, using daily_register_has_reset={self.daily_register_has_reset} from state.json")
                logging.info(f"  Will detect register reset on next cycle when whc_daily decreases")

            # NOTE: We used to set daily_register_has_reset=True when detecting cs_raw >= 5
            # But this caused spikes because whc_daily register doesn't reset immediately
            # when charging starts - there's a delay. So we ONLY trust the register
            # value decrease detection (line 1746 above). Never set flag based on charge state!

            self.last_daily_register_value = current_daily_wh

            # Calculate daily yield with offset (for controller resets before midnight)
            if not self.daily_register_has_reset:
                daily_kwh = 0.0  # Don't use yesterday's stale value
                logging.debug("Post-midnight, pre-sunrise: using 0 for daily yield")
            else:
                # Apply offset (normally 0, but set when controller reset happens)
                modbus_kwh = (self.daily_wh_offset + current_daily_wh) / 1000.0
                # Use max(state.json, Modbus) - protects against driver restart losing daily_wh_offset
                saved_kwh = self.state['today'].get('yield', 0.0)
                daily_kwh = max(saved_kwh, modbus_kwh)
                if self.daily_wh_offset > 0:
                    logging.debug(f"Daily yield with offset: {self.daily_wh_offset:.1f} + {current_daily_wh} Wh = {modbus_kwh:.3f} kWh")
                if daily_kwh > modbus_kwh:
                    logging.debug(f"Daily yield: using saved value {saved_kwh:.3f} kWh (Modbus: {modbus_kwh:.3f} kWh)")

            # Check for midnight (date changed) - do this BEFORE updating history paths
            self._check_midnight_rollover(daily_kwh)

            # CRITICAL: Recalculate daily_kwh AFTER all flag changes
            # Flag can change in 3 places:
            #  1. Line 1718: Register reset detected (False → True)
            #  2. Line 1728: First update, charging detected (False → True)
            #  3. Line 1740: Charging detected mid-day (False → True)
            #  4. Midnight rollover: (True → False)
            # We must recalculate to match current flag state, otherwise spike occurs
            old_daily_kwh = daily_kwh  # Save for logging
            if not self.daily_register_has_reset:
                daily_kwh = 0.0  # Post-midnight pre-sunrise: use 0
            else:
                modbus_kwh = (self.daily_wh_offset + current_daily_wh) / 1000.0
                daily_kwh = max(self.state['today'].get('yield', 0.0), modbus_kwh)

            # Log if recalculation changed the value (indicates flag changed during this cycle)
            if abs(daily_kwh - old_daily_kwh) > 0.001:
                logging.info(f"🔄 Recalculated daily_kwh: {old_daily_kwh:.3f} → {daily_kwh:.3f} kWh (flag={self.daily_register_has_reset})")

            # Update state['today'] with current daily values (AFTER midnight check, so reset works correctly)
            # This will be saved every 5 minutes to preserve values across restarts
            if self.daily_register_has_reset:
                self.state['today']['yield'] = daily_kwh  # Only save when Modbus is valid
            self.state['today']['max_battery_current'] = self.daily_max_battery_current
            self.state['today']['max_power'] = self.daily_max_power
            self.state['today']['max_pv_voltage'] = self.daily_max_pv_voltage
            self.state['today']['max_battery_voltage'] = self.daily_max_battery_voltage
            self.state['today']['min_battery_voltage'] = self.daily_min_battery_voltage
            # Save time values from Modbus when valid (offset + register = total for the day)
            if self.daily_register_has_reset:
                self.state['today']['time_absorption'] = self.time_abs_offset + reg(REG_T_ABS) // 60
                self.state['today']['time_float'] = self.time_float_offset + reg(REG_T_FLOAT) // 60
                self.state['today']['time_equalize'] = self.time_eq_offset + reg(REG_T_EQ_DAILY) // 60
            self.state['today']['time_bulk'] = int(self.t_bulk_ms / (1000 * 60))  # Convert ms to minutes

            # History - Day 0 (today, live values)
            self.dbus['/History/Daily/0/Yield'] = round(daily_kwh, 2)

            if self.daily_register_has_reset:
                # Register has valid data for today - use max(state.json, Modbus)
                # This preserves values across controller resets (which reset Modbus registers)
                modbus_max_power = reg(REG_POUT_MAX_DAILY) * self.i_pu * self.v_pu / 131072.0
                modbus_max_pv_v = reg(REG_V_PV_MAX) * self.v_pu / 32768.0
                modbus_max_batt_v = reg(REG_V_BAT_MAX) * self.v_pu / 32768.0
                modbus_min_batt_v = reg(REG_V_BAT_MIN) * self.v_pu / 32768.0

                self.dbus['/History/Daily/0/MaxPower'] = round(
                    max(self.state['today']['max_power'], modbus_max_power), 0
                )
                self.dbus['/History/Daily/0/MaxPvVoltage'] = round(
                    max(self.state['today']['max_pv_voltage'], modbus_max_pv_v), 2
                )
                self.dbus['/History/Daily/0/MaxBatteryVoltage'] = round(
                    max(self.state['today']['max_battery_voltage'], modbus_max_batt_v), 2
                )
                # Min uses min() instead of max()
                state_min = self.state['today']['min_battery_voltage'] if self.state['today']['min_battery_voltage'] < 999 else 99.0
                self.dbus['/History/Daily/0/MinBatteryVoltage'] = round(
                    min(state_min, modbus_min_batt_v), 2
                )
                # Time values: offset + Modbus (same principle as daily_wh_offset for yield)
                self.dbus['/History/Daily/0/TimeInAbsorption'] = self.time_abs_offset + reg(REG_T_ABS) // 60
                self.dbus['/History/Daily/0/TimeInFloat'] = self.time_float_offset + reg(REG_T_FLOAT) // 60
                self.dbus['/History/Daily/0/TimeInEqualize'] = self.time_eq_offset + reg(REG_T_EQ_DAILY) // 60
            else:
                # Modbus has stale data - use today's values from state.json instead
                # (state is updated every 5 min, so these are recent values)
                self.dbus['/History/Daily/0/MaxPower'] = round(self.state['today']['max_power'], 0)
                self.dbus['/History/Daily/0/MaxPvVoltage'] = round(self.state['today']['max_pv_voltage'], 2)
                self.dbus['/History/Daily/0/MaxBatteryVoltage'] = round(self.state['today']['max_battery_voltage'], 2)
                min_batt = self.state['today']['min_battery_voltage']
                self.dbus['/History/Daily/0/MinBatteryVoltage'] = round(min_batt, 2) if min_batt < 999 else 0.0
                # Time values: Use state.json when Modbus is stale (preserves yesterday's values until sunrise)
                self.dbus['/History/Daily/0/TimeInAbsorption'] = self.state['today']['time_absorption']
                self.dbus['/History/Daily/0/TimeInFloat'] = self.state['today']['time_float']
                self.dbus['/History/Daily/0/TimeInEqualize'] = self.state['today']['time_equalize']

            # These values are tracked by us (reset at midnight), so always use them
            self.dbus['/History/Daily/0/MaxBatteryCurrent'] = round(self.daily_max_battery_current, 2)
            self.dbus['/History/Daily/0/TimeInBulk'] = int(self.t_bulk_ms / (1000 * 60))

            # Update historical days 1-29 from state file
            self._update_historical_days()

            # Update Overall (lifetime) values
            self.dbus['/History/Overall/MaxPvVoltage'] = round(self.state['lifetime']['max_pv_voltage'], 2)
            self.dbus['/History/Overall/MaxBatteryVoltage'] = round(self.state['lifetime']['max_battery_voltage'], 2)
            min_batt = self.state['lifetime']['min_battery_voltage']
            self.dbus['/History/Overall/MinBatteryVoltage'] = round(min_batt, 2) if min_batt < 999 else 0.0

            # Periodic state save (every 5 minutes to preserve today's values across restarts)
            current_time = time()
            if current_time - self.last_state_save_time >= self.state_save_interval:
                logging.info(f"Periodic state save (5 min interval) - preserving today's values")
                # Update voltage override state before saving
                self.state['voltage_override']['stop_reason'] = self.stop_reason
                self._save_state()
                self.last_state_save_time = current_time

            # ========================================================================
            # VOLTAGE OVERRIDE CONTROL LOGIC
            # ========================================================================

            # Calculate excess power (sweep_Pin_max - threshold - P_out)
            sweep_pmax = reg(REG_SWEEP_PMAX) * self.i_pu * self.v_pu / 131072.0  # Watts
            p_out = reg(REG_POUT) * self.i_pu * self.v_pu / 131072.0  # Watts
            excess_power_threshold = self.settings['excess_power_threshold']
            excess_power = sweep_pmax - excess_power_threshold - p_out
            self.dbus['/Custom/VoltageOverride/ExcessPower'] = round(excess_power, 0)

            # Get safety limits from settings
            max_time = self.settings['max_voltage_override_time']
            battery_full_current = self.settings['battery_full_current']
            tail_current_time = self.settings['tail_current_time']

            # Get current battery measurements
            i_charge = self._to_signed(reg(REG_I_CC_1M)) * self.i_pu / 32768.0  # Amps (filtered, 1-min avg)
            v_battery = reg(REG_V_BAT) * self.v_pu / 32768.0  # Volts

            current_time = time()

            # Check if override is active
            if self.pending_voltage_override is not None:
                self.voltage_override_active = True

                # Get target voltage for safety checks
                target_voltage = self.register_to_voltage(self.pending_voltage_override)

                # At target: V >= target (like Home Assistant binary_sensor.over_28_7v)
                # This tolerates brief dips due to clouds/varying solar input
                at_target_voltage = v_battery >= target_voltage

                # Track cumulative time at or above target voltage (tolerates dips)
                if not hasattr(self, 'time_above_target_accumulated'):
                    self.time_above_target_accumulated = 0
                if not hasattr(self, 'last_override_time_update'):
                    self.last_override_time_update = current_time

                # Initialize timer on first time reaching target
                if at_target_voltage and self.override_start_time is None:
                    self.override_start_time = current_time
                    self.time_above_target_accumulated = 0
                    self.last_override_time_update = current_time
                    logging.info(f"Battery reached target voltage {target_voltage:.2f}V (>= {target_voltage:.2f}V) - starting cumulative timer")

                # Accumulate time when at or above target
                if at_target_voltage and self.override_start_time is not None:
                    delta = current_time - self.last_override_time_update
                    if 0 < delta < 10:  # Sanity check (max 10s between updates)
                        self.time_above_target_accumulated += delta
                    self.last_override_time_update = current_time

                time_at_target = self.time_above_target_accumulated

                # Safety check 1: Time at target voltage limit exceeded?
                if at_target_voltage and time_at_target >= max_time:
                    logging.warning(f"Max time at target voltage exceeded ({int(time_at_target)}s >= {max_time}s)")
                    self.stop_reason = "TimeLimit"
                    self.pending_voltage_override = None
                    self.voltage_override_active = False
                    self.override_start_time = None
                    self.tail_current_start_time = None
                    self.time_above_target_accumulated = 0
                    self.write_holding_register(89, -1)  # PDU 89 = vb_ref_slave

                # Safety check 2: Battery full (tail current)?
                # Check voltage at target AND (excess power OR disabled) AND low current
                else:
                    # Excess power check: skip if threshold is -1 (disabled)
                    check_excess_power = (excess_power_threshold == -1) or (excess_power > 0)

                    if at_target_voltage and check_excess_power and i_charge < battery_full_current:
                        # Start tail current timer if not already started
                        if self.tail_current_start_time is None:
                            self.tail_current_start_time = current_time
                            logging.info(f"Tail current detected: V={v_battery:.2f}V (target={target_voltage:.2f}V), I={i_charge:.2f}A < {battery_full_current}A")

                        # Check if tail current condition held long enough
                        tail_duration = current_time - self.tail_current_start_time
                        if tail_duration >= tail_current_time:
                            logging.info(f"Battery full detected: voltage at {v_battery:.2f}V, tail current {i_charge:.2f}A for {int(tail_duration)}s")
                            self.stop_reason = "BatteryFull"
                            self.pending_voltage_override = None
                            self.voltage_override_active = False
                            self.tail_current_start_time = None
                            self.override_start_time = None
                            self.time_above_target_accumulated = 0
                            self.write_holding_register(89, -1)  # PDU 89 = vb_ref_slave
                    else:
                        # Reset tail current timer if conditions not met
                        # (voltage not reached, current too high, or no excess power)
                        if self.tail_current_start_time is not None:
                            logging.debug(f"Tail current timer reset: at_voltage={at_target_voltage}, excess={excess_power:.0f}W, I={i_charge:.2f}A")
                        self.tail_current_start_time = None

                # Update monitoring paths
                self.dbus['/Custom/VoltageOverride/TimeAtTargetVoltage'] = int(time_at_target)
                self.dbus['/Custom/VoltageOverride/TailCurrentTimer'] = int(current_time - self.tail_current_start_time) if self.tail_current_start_time else 0
            else:
                self.voltage_override_active = False
                self.override_start_time = None
                self.tail_current_start_time = None
                self.time_above_target_accumulated = 0

            self.dbus['/Custom/VoltageOverride/Active'] = self.voltage_override_active
            self.dbus['/Custom/VoltageOverride/StopReason'] = self.stop_reason

            # Periodic register write (every 30 seconds to maintain slave mode)
            if self.pending_voltage_override is not None:
                current_time = time()
                if current_time - self.last_voltage_override_write >= self.voltage_override_interval:
                    success = self.write_holding_register(89, self.pending_voltage_override)  # PDU 89 = vb_ref_slave
                    if success:
                        self.last_voltage_override_write = current_time
                        actual_voltage = self.register_to_voltage(self.pending_voltage_override)
                        logging.info(f"Updated Vb_ref_slave: {actual_voltage:.2f}V (reg: {self.pending_voltage_override})")
                        self.dbus['/Custom/VoltageOverride/CurrentVoltage'] = round(actual_voltage, 2)

                        # Read back PDU 89 to verify (periodic check)
                        readback = self.read_holding_registers(89, 1)  # PDU 89 = vb_ref_slave
                        if readback is not None:
                            readback_value = self._to_signed(readback[0])
                            readback_voltage = self.register_to_voltage(readback_value)
                            self.dbus['/Custom/VoltageOverride/RegisterReadback'] = round(readback_voltage, 2)
                            if abs(readback_voltage - actual_voltage) > 0.1:
                                logging.warning(f"PDU 89 readback mismatch: wrote {actual_voltage:.2f}V, read {readback_voltage:.2f}V")
                    else:
                        logging.warning(f"Failed to write Vb_ref_slave register")
            else:
                # Override not active - ensure CurrentVoltage shows 0
                self.dbus['/Custom/VoltageOverride/CurrentVoltage'] = 0.0
                self.dbus['/Custom/VoltageOverride/RegisterReadback'] = 0.0

            # ========================================================================
            # END VOLTAGE OVERRIDE CONTROL LOGIC
            # ========================================================================

            # ========================================================================
            # CURRENT OVERRIDE CONTROL LOGIC (PDU register 88 - Ib_ref_slave, Logical 89)
            # ========================================================================

            # Periodic register write for current override (every 30 seconds to maintain slave mode)
            if self.pending_current_override is not None:
                current_time = time()
                if current_time - self.last_current_override_write >= self.voltage_override_interval:  # Use same 30s interval
                    success = self.write_holding_register(88, self.pending_current_override)  # PDU 88 = Ib_ref_slave
                    if success:
                        self.last_current_override_write = current_time
                        actual_current = self.register_to_current(self.pending_current_override)
                        logging.info(f"Updated Ib_ref_slave: {actual_current:.2f}A (reg: {self.pending_current_override})")
                        self.dbus['/Custom/CurrentOverride/CurrentValue'] = round(actual_current, 2)

                        # Read back PDU 88 to verify (periodic check)
                        readback = self.read_holding_registers(88, 1)  # PDU 88 = Ib_ref_slave
                        if readback is not None:
                            readback_value = self._to_signed(readback[0])
                            readback_current = self.register_to_current(readback_value)
                            self.dbus['/Custom/CurrentOverride/RegisterReadback'] = round(readback_current, 2)
                            if abs(readback_current - actual_current) > 0.5:
                                logging.warning(f"PDU 88 readback mismatch: wrote {actual_current:.2f}A, read {readback_current:.2f}A")
                    else:
                        logging.warning(f"Failed to write Ib_ref_slave register")
            else:
                # Override not active - ensure current shows 0
                self.dbus['/Custom/CurrentOverride/CurrentValue'] = 0.0
                self.dbus['/Custom/CurrentOverride/RegisterReadback'] = 0.0

            self.dbus['/Custom/CurrentOverride/Active'] = self.current_override_active

            # ========================================================================
            # END CURRENT OVERRIDE CONTROL LOGIC
            # ========================================================================

            # Read manual control registers that might interfere with slave mode
            # These should normally be 0 unless explicitly set
            va_ref_fixed_regs = self.read_holding_registers(90, 2)  # Read PDU 90-91 (va_ref_fixed, va_ref_fixed_pct)
            if va_ref_fixed_regs is not None:
                # Register 91 (0x005A): Va_ref_fixed - Array voltage fixed target
                va_ref_fixed_raw = self._to_signed(va_ref_fixed_regs[0])
                if va_ref_fixed_raw > 0:
                    va_ref_fixed = va_ref_fixed_raw * self.v_pu / 32768.0
                    self.dbus['/Custom/ManualControl/VaRefFixed'] = round(va_ref_fixed, 2)
                    if va_ref_fixed > 1.0:  # Only warn if significantly non-zero
                        logging.warning(f"Va_ref_fixed is set to {va_ref_fixed:.2f}V - this disables MPPT sweeping!")
                else:
                    self.dbus['/Custom/ManualControl/VaRefFixed'] = 0.0

                # Register 92 (0x005B): Va_ref_fixed_pct - Array voltage % of Voc
                va_ref_fixed_pct_raw = self._to_signed(va_ref_fixed_regs[1])
                if va_ref_fixed_pct_raw > 0:
                    va_ref_fixed_pct = va_ref_fixed_pct_raw * 100.0 / 32768.0
                    self.dbus['/Custom/ManualControl/VaRefFixedPct'] = round(va_ref_fixed_pct, 1)
                    if va_ref_fixed_pct > 1.0:  # Only warn if significantly non-zero
                        logging.warning(f"Va_ref_fixed_pct is set to {va_ref_fixed_pct:.1f}% - this disables MPPT sweeping!")
                else:
                    self.dbus['/Custom/ManualControl/VaRefFixedPct'] = 0

            # Total yield (use persistent counter to avoid double-counting)
            # Do NOT auto-initialize from TriStar registers (they may be reset or have wrong baseline)
            # User must manually set total_yield_kwh in state.json to desired starting value
            if self.state['total_yield_kwh'] == 0.0:
                logging.warning("total_yield_kwh is 0! Please manually set it in state.json to your desired baseline.")
                logging.warning(f"  REG_KWH_TOTAL_RES (resettable) = {reg(REG_KWH_TOTAL_RES)} kWh")
                logging.warning(f"  REG_KWH_TOTAL (permanent) = {reg(REG_KWH_TOTAL)} kWh")
                logging.warning("  Edit /data/dbus-tristar/state.json and set 'total_yield_kwh' to correct value.")

            # Total yield: persistent total + today's calculated yield (already handled above)
            new_yield_system = round(self.state['total_yield_kwh'] + daily_kwh, 2)

            # Log significant changes (> 0.1 kWh jump in one cycle = potential spike)
            if hasattr(self, 'last_yield_system'):
                delta = abs(new_yield_system - self.last_yield_system)
                if delta > 0.1:
                    logging.warning(f"⚠️  SPIKE DETECTED ⚠️")
                    logging.warning(f"Large /Yield/System change: {self.last_yield_system:.2f} → {new_yield_system:.2f} kWh (Δ={delta:.2f})")
                    logging.warning(f"  total_yield_kwh={self.state['total_yield_kwh']:.3f}, daily_kwh={daily_kwh:.3f}, daily_reg_reset={self.daily_register_has_reset}")
                    logging.warning(f"  current_daily_wh={current_daily_wh} Wh, last_daily_reg={self.last_daily_register_value} Wh")
                    logging.warning(f"  cs_raw={cs_raw}, cs={cs}, first_update_done={self.first_update_done}")

            self.dbus['/Yield/User'] = new_yield_system
            self.dbus['/Yield/System'] = new_yield_system
            self.last_yield_system = new_yield_system

            # Read stateful coils
            coils = self.read_coils(COIL_EQUALIZE, 3)  # Read coils 0, 1, 2
            if coils is not None:
                self.dbus['/Control/EqualizeTriggered'] = int(coils[0])
                self.dbus['/Control/ChargerDisconnect'] = int(coils[2])

                # Update /Mode based on COIL_DISCONNECT state (coil 2)
                # Coil 2 = 0 → Mode = 1 (On), Coil 2 = 1 → Mode = 4 (Off)
                if coils[2]:
                    self.dbus['/Mode'] = 4  # Charger disconnected (Off)
                else:
                    self.dbus['/Mode'] = 1  # Charger connected (On)
            else:
                logging.warning("Failed to read coils - control status may be stale")

            # Nightly reset at 03:00
            self._check_nightly_reset()

        except Exception as e:
            logging.error(f"Update error: {e}", exc_info=True)

        # Conditional EEPROM reads (outside try/except to not block on EEPROM errors)
        # Per Morningstar: "not reading the EEPROM registers helps prevent [comm server] issues"

        # Read lifetime kWh every 30 minutes (not critical for real-time monitoring)
        self.eeprom_kwh_counter += 1
        if self.eeprom_kwh_counter >= self.eeprom_kwh_interval:
            self._read_eeprom_lifetime_kwh()
            self.eeprom_kwh_counter = 0

        # Read charge settings on-demand (after EEPROM write or at startup)
        if self.eeprom_refresh_needed:
            self._read_eeprom_charge_settings()
            self.eeprom_refresh_needed = False

        return True  # Continue timer

    def _check_nightly_reset(self):
        """Check if we should perform nightly TriStar comm server reset (local time)"""
        # Get current local date and time (same method as midnight detection)
        current_date = self._get_local_date()

        # Get current local hour/minute
        try:
            bus = dbus.SystemBus()
            settings = bus.get_object('com.victronenergy.settings', '/Settings/System/TimeZone')
            tz_string = settings.GetValue()

            old_tz = os.environ.get('TZ', '')
            os.environ['TZ'] = tz_string
            time_module.tzset()

            current_hour = int(time_module.strftime('%H', time_module.localtime()))
            current_minute = int(time_module.strftime('%M', time_module.localtime()))

            # Restore TZ
            if old_tz:
                os.environ['TZ'] = old_tz
            else:
                if 'TZ' in os.environ:
                    del os.environ['TZ']
            time_module.tzset()

        except Exception as e:
            logging.error(f"Error getting local time for nightly reset: {e}")
            return

        reset_hour = self.settings['nightly_reset_hour']

        # Check if it's reset time (5-minute window to catch it)
        if current_hour == reset_hour and current_minute < 5:
            # Only attempt reset once per day
            if self.last_reset_date != current_date:
                # Mark as attempted BEFORE trying (prevent retry spam if write fails)
                self.last_reset_date = current_date

                logging.info(f"Performing nightly reset at {reset_hour:02d}:00 local time")

                # 1. Disable voltage override (prevent stuck topcharging)
                if self.pending_voltage_override is not None:
                    logging.info("Nightly reset: Disabling voltage override")
                    self.pending_voltage_override = None
                    self.voltage_override_active = False
                    self.stop_reason = "NightlyReset"
                    self.write_holding_register(89, -1)  # PDU 89 = vb_ref_slave

                # 2. Reset cumulative time counter (fresh start for new day)
                if self.time_above_target_accumulated > 0:
                    logging.info(f"Nightly reset: Clearing cumulative time counter ({int(self.time_above_target_accumulated)}s)")
                self.time_above_target_accumulated = 0
                self.override_start_time = None
                self.tail_current_start_time = None

                # 3. Reset TriStar comm server
                success = self.write_coil(COIL_RESET_COMM, True)
                if success:
                    logging.info("Nightly reset completed successfully")
                else:
                    logging.error("Nightly comm server reset failed - will retry tomorrow")

    # ========================================================================
    # Charge Profile Management (EEPROM)
    # ========================================================================

    def _load_charge_profiles(self):
        """Load charge profiles from JSON file"""
        profile_file = Path("/data/dbus-tristar/charge_profiles.json")

        default_profiles = {
            "version": 1,
            "last_applied_profile": "",
            "last_applied_timestamp": "",
            "profiles": {
                "summer": {
                    "EV_absorp": 28.4,
                    "EV_float": 27.2,
                    "Et_absorp": 7200,
                    "EV_float_cancel": 26.0
                },
                "winter": {
                    "EV_absorp": 28.8,
                    "EV_float": 27.6,
                    "Et_absorp": 9000,
                    "EV_float_cancel": 26.4
                },
                "custom": {
                    "EV_absorp": 28.6,
                    "EV_float": 27.4,
                    "Et_absorp": 8400,
                    "EV_float_cancel": 26.2
                }
            }
        }

        try:
            if profile_file.exists():
                with open(profile_file, 'r') as f:
                    profiles = json.load(f)
                    # Merge with defaults for any missing profiles
                    for profile_name in default_profiles["profiles"]:
                        if profile_name not in profiles.get("profiles", {}):
                            profiles["profiles"][profile_name] = default_profiles["profiles"][profile_name]
                    return profiles
        except Exception as e:
            logging.error(f"Failed to load charge profiles: {e}")

        # Create default file if it doesn't exist
        try:
            profile_file.parent.mkdir(parents=True, exist_ok=True)
            with open(profile_file, 'w') as f:
                json.dump(default_profiles, f, indent=2)
            logging.info(f"Created default charge profiles: {profile_file}")
        except Exception as e:
            logging.error(f"Failed to create default charge profiles file: {e}")

        return default_profiles

    def _save_charge_profiles(self):
        """Save charge profiles to JSON file (atomic write)"""
        profile_file = Path("/data/dbus-tristar/charge_profiles.json")
        temp_file = profile_file.with_suffix('.tmp')

        try:
            with open(temp_file, 'w') as f:
                json.dump(self.charge_profiles, f, indent=2)
            temp_file.replace(profile_file)
        except Exception as e:
            logging.error(f"Failed to save charge profiles: {e}")
            if temp_file.exists():
                temp_file.unlink()

    def _on_apply_profile_requested(self, path, value):
        """Callback when user writes to /Control/ApplyChargeProfile"""
        logging.debug(f"Apply profile callback: path={path}, value={value}, type={type(value)}, status={self.profile_apply_status}")
        profile_name = str(value).lower().strip()
        logging.debug(f"Parsed profile_name: '{profile_name}'")

        if not profile_name:
            logging.error(f"Empty profile name after parsing")
            return False

        if profile_name not in ['summer', 'winter', 'custom']:
            error_msg = f"Invalid profile: {profile_name}. Must be 'summer', 'winter', or 'custom'"
            self.dbus['/Custom/ChargeProfile/LastError'] = error_msg
            logging.error(error_msg)
            return False

        # Block if operation is in progress, but allow retry after success/failure
        if self.profile_apply_status not in ['idle', 'success', 'failed']:
            error_msg = f"Profile apply already in progress (status: {self.profile_apply_status})"
            self.dbus['/Custom/ChargeProfile/LastError'] = error_msg
            logging.warning(error_msg)
            return False

        # Start async profile apply operation
        logging.info(f"Starting charge profile apply: {profile_name}")
        threading.Thread(target=self._apply_charge_profile_async,
                        args=(profile_name,),
                        daemon=True).start()

        return True

    def _wait_for_charge_state(self, expected_state, timeout_sec=5, step_name=""):
        """
        Poll for specific charge state with intelligent retry
        Returns True if state reached, False if timeout
        """
        attempts = int(timeout_sec / 0.5)
        for attempt in range(attempts):
            sleep(0.5)
            try:
                cs = self.client.read_holding_registers(REG_CHARGE_STATE, 1, unit=self.settings['slave_id']).registers[0]
                if cs == expected_state:
                    elapsed = (attempt + 1) * 0.5
                    state_name = CHARGE_STATE_TEXT.get(cs, f"Unknown({cs})")
                    logging.info(f"{step_name}Charge state {state_name} reached after {elapsed:.1f}s")
                    return True
            except Exception as e:
                if attempt % 4 == 0:  # Log every 2 seconds
                    logging.debug(f"Polling charge state: {e}")
                continue

        # Timeout
        logging.warning(f"{step_name}Charge state {expected_state} not reached after {timeout_sec}s")
        return False

    def _wait_for_charge_state_not(self, unwanted_state, timeout_sec=5, step_name=""):
        """
        Poll until charge state changes from unwanted_state
        Returns True if state changed, False if timeout
        """
        attempts = int(timeout_sec / 0.5)
        for attempt in range(attempts):
            sleep(0.5)
            try:
                cs = self.client.read_holding_registers(REG_CHARGE_STATE, 1, unit=self.settings['slave_id']).registers[0]
                if cs != unwanted_state:
                    elapsed = (attempt + 1) * 0.5
                    state_name = CHARGE_STATE_TEXT.get(cs, f"Unknown({cs})")
                    logging.info(f"{step_name}Charge state changed to {state_name} after {elapsed:.1f}s")
                    return True
            except Exception as e:
                if attempt % 4 == 0:
                    logging.debug(f"Polling charge state: {e}")
                continue

        logging.warning(f"{step_name}Charge state still {unwanted_state} after {timeout_sec}s")
        return False

    def _smart_reconnect(self, timeout_sec=20):
        """
        Poll for Modbus reconnect after controller reset with intelligent retry
        Returns True if reconnected, raises Exception if timeout
        """
        attempts = int(timeout_sec / 0.5)

        for attempt in range(attempts):
            sleep(0.5)
            try:
                self.client.close()
                self.client.connect()
                # Test that connection actually works
                self.client.read_holding_registers(REG_V_PU, 1, unit=self.settings['slave_id'])
                elapsed = (attempt + 1) * 0.5
                logging.info(f"✓ Modbus reconnected after {elapsed:.1f}s")
                return True
            except Exception as e:
                if attempt % 4 == 0:  # Log every 2 seconds
                    logging.debug(f"Reconnect attempt {attempt//2 + 1}: {e}")
                continue

        raise Exception(f"Failed to reconnect to controller after {timeout_sec}s")

    def _apply_charge_profile_async(self, profile_name):
        """
        Async operation to apply charge profile to EEPROM
        Follows Morningstar recommended procedure with intelligent retry
        """
        try:
            # ==== LOCK MODBUS (prevent collision with main update loop) ====
            self.profile_apply_in_progress = True
            self.main_loop_paused_reason = f"Applying charge profile '{profile_name}'"
            logging.info(f"Main update loop paused for profile apply")

            # Create dedicated Modbus client for this operation
            ip = self.settings['ip_address']
            port = self.settings['modbus_port']
            slave_id = self.settings['slave_id']
            self.client = ModbusTcpClient(host=ip, port=port, timeout=2, retries=0)
            if not self.client.connect():
                raise Exception("Failed to connect to controller")
            logging.debug("Modbus client connected for profile apply")

            self._update_profile_status("validating", 0, "")

            # Step 1: Get profile from Settings
            profile = self._get_profile_from_settings(profile_name)
            logging.info(f"Profile '{profile_name}': {profile}")

            # Step 2: Validate relationships
            self._validate_profile(profile)

            # Step 3: Read current EEPROM values
            self._update_profile_status("validating", 10, "Reading current EEPROM...")
            current_eeprom = self._read_eeprom_values()
            logging.info(f"Current EEPROM: {current_eeprom}")

            # Step 4: Compare and filter (only write changed values)
            changes = self._compare_profiles(profile, current_eeprom)

            if not changes:
                logging.info(f"Profile '{profile_name}' already matches EEPROM, no changes needed")
                self._update_profile_status("success", 100, "")
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.dbus['/Custom/ChargeProfile/LastApplied'] = f"{profile_name} (no changes) at {timestamp}"
                self._save_charge_profiles()
                return

            logging.info(f"Will write {len(changes)} EEPROM parameter(s): {list(changes.keys())}")

            # Step 5: Backup current EEPROM
            self._update_profile_status("validating", 20, "Backing up current values...")
            backup = self._backup_eeprom(current_eeprom, f"before_profile_{profile_name}")

            # Step 6: Disable charging (DISCONNECT) with intelligent wait
            self._update_profile_status("disconnecting", 30, "Disconnecting charger...")
            if not self.write_coil(COIL_DISCONNECT, True):
                raise Exception("Failed to set DISCONNECT coil")

            # Poll for DISCONNECT state (max 5 seconds)
            if not self._wait_for_charge_state(2, timeout_sec=5, step_name="DISCONNECT: "):
                logging.warning("DISCONNECT state not confirmed, but continuing anyway...")

            # Step 7: Write EEPROM parameters (in safe order: lowest voltage first)
            self._update_profile_status("writing", 40, "Writing EEPROM parameters...")
            write_order = ['EV_float_cancel', 'EV_float', 'EV_absorp', 'Et_absorp']

            written_count = 0
            for param in write_order:
                if param in changes:
                    self._write_eeprom_parameter(param, changes[param])
                    written_count += 1
                    progress = 40 + int((written_count / len(changes)) * 20)
                    self._update_profile_status("writing", progress, f"Wrote {written_count}/{len(changes)} parameters...")
                    sleep(0.2)

            sleep(1)  # EEPROM write cycle completion

            # Step 8: Verify writes
            self._update_profile_status("writing", 60, "Verifying writes...")
            self._verify_eeprom_writes(changes)

            # Step 8.5: Save state before controller reset (preserve daily statistics)
            self._save_state()
            logging.info("✓ State saved before controller reset")

            # Step 9: Reset controller (Morningstar recommended)
            self._update_profile_status("resetting", 70, "Resetting controller...")
            reset_result = self.write_coil(COIL_RESET_CTRL, True)
            if reset_result:
                logging.info("✓ Controller reset command sent successfully")
            else:
                # Reset coil write often fails because controller resets immediately
                # This is expected behavior, not an error
                logging.info("Controller reset triggered (connection closed - expected behavior)")

            # Step 10: Smart reconnect with polling (replaces fixed sleep + manual reconnect)
            self._update_profile_status("resetting", 75, "Waiting for controller reboot...")
            self._smart_reconnect(timeout_sec=20)

            # Step 11: Verify controller resumed normal operation
            # (DISCONNECT coil should be cleared by reset, no manual re-enable needed)
            self._update_profile_status("resetting", 90, "Verifying normal operation...")
            try:
                cs = self.client.read_holding_registers(REG_CHARGE_STATE, 1, unit=self.settings['slave_id']).registers[0]
                state_name = CHARGE_STATE_TEXT.get(cs, f"Unknown({cs})")
                if cs == 2:  # Still DISCONNECT?!
                    logging.warning(f"⚠️ Controller still in DISCONNECT state after reset - unexpected!")
                    logging.warning("Attempting to clear DISCONNECT as fallback...")
                    self.write_coil(COIL_DISCONNECT, False)
                    sleep(1)
                    # Re-check
                    cs = self.client.read_holding_registers(REG_CHARGE_STATE, 1, unit=self.settings['slave_id']).registers[0]
                    state_name = CHARGE_STATE_TEXT.get(cs, f"Unknown({cs})")
                    logging.info(f"State after manual clear: {state_name}")
                else:
                    logging.info(f"✓ Controller resumed normal operation (state: {state_name})")
            except Exception as e:
                logging.warning(f"Could not verify charge state after reset: {e}")

            # Step 12: Read back and update active EEPROM display
            self._update_profile_status("resetting", 95, "Verifying final values...")
            final_eeprom = self._read_eeprom_values()
            self._update_active_eeprom_display(final_eeprom)

            # Step 13: Success!
            self._update_profile_status("success", 100, "")
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.dbus['/Custom/ChargeProfile/LastApplied'] = f"{profile_name} at {timestamp}"

            # Update profiles JSON
            self.charge_profiles['last_applied_profile'] = profile_name
            self.charge_profiles['last_applied_timestamp'] = timestamp
            self._save_charge_profiles()

            # Flag main loop to refresh EEPROM charge settings on next update
            self.eeprom_refresh_needed = True

            logging.info(f"✅ Charge profile '{profile_name}' applied successfully ({len(changes)} changes)")

        except Exception as e:
            error_msg = str(e)
            logging.error(f"❌ Failed to apply charge profile '{profile_name}': {error_msg}")
            self._update_profile_status("failed", self.profile_apply_progress, error_msg)

            # Attempt to re-enable charging if we failed before reset
            # (After reset, DISCONNECT should be auto-cleared by controller)
            try:
                cs = self.client.read_holding_registers(REG_CHARGE_STATE, 1, unit=self.settings['slave_id']).registers[0]
                if cs == 2:  # Still DISCONNECT
                    logging.info("Attempting to re-enable charging after failure...")
                    self.write_coil(COIL_DISCONNECT, False)
            except Exception as recovery_error:
                # Connection errors are expected if controller reset - not a problem
                if "Connection" in str(recovery_error) or "closed" in str(recovery_error):
                    logging.debug(f"Cannot re-enable charging (controller likely reset): {recovery_error}")
                else:
                    logging.error(f"Failed to re-enable charging: {recovery_error}")

        finally:
            # Close Modbus client
            if hasattr(self, 'client') and self.client:
                try:
                    self.client.close()
                    logging.debug("Modbus client closed")
                except Exception:
                    pass
                self.client = None

            # Reset control path so next apply will trigger (D-Bus onchangecallback only fires on value change)
            self.dbus['/Control/ApplyChargeProfile'] = ''

            # ==== UNLOCK MODBUS (always, even on failure) ====
            self.profile_apply_in_progress = False
            self.main_loop_paused_reason = ""
            logging.info("Main update loop resumed")

    def _update_profile_status(self, status, progress, error):
        """Update D-Bus status paths for profile apply operation"""
        self.profile_apply_status = status
        self.profile_apply_progress = progress
        self.profile_apply_error = error

        self.dbus['/Custom/ChargeProfile/ApplyStatus'] = status
        self.dbus['/Custom/ChargeProfile/ProgressPercent'] = progress
        if error:
            self.dbus['/Custom/ChargeProfile/LastError'] = error

    def _get_profile_from_settings(self, profile_name):
        """Read profile values from D-Bus Settings"""
        profile_cap = profile_name.capitalize()

        # Read from SettingsDevice (values are already loaded in self.settings)
        key_map = {
            'EV_absorp': f'profile_{profile_name}_absorption_v',
            'EV_float': f'profile_{profile_name}_float_v',
            'Et_absorp': f'profile_{profile_name}_absorption_time',
            'EV_float_cancel': f'profile_{profile_name}_float_cancel_v',
        }

        profile = {}
        for param, setting_key in key_map.items():
            try:
                value = self.settings[setting_key]
            except KeyError:
                raise Exception(f"Setting '{setting_key}' not found")
            profile[param] = int(value) if param == 'Et_absorp' else float(value)

        return profile

    def _validate_profile(self, profile):
        """Validate profile parameter relationships"""
        ev_float = profile['EV_float']
        ev_absorp = profile['EV_absorp']
        ev_float_cancel = profile['EV_float_cancel']
        et_absorp = profile['Et_absorp']

        if ev_float >= ev_absorp:
            raise Exception(f"Float voltage ({ev_float}V) must be < Absorption voltage ({ev_absorp}V)")

        # Allow 0 for float_cancel (disables the function)
        if ev_float_cancel > 0 and ev_float_cancel >= ev_float:
            raise Exception(f"Float cancel voltage ({ev_float_cancel}V) must be < Float voltage ({ev_float}V)")

        if not (26.0 <= ev_absorp <= 32.0):
            raise Exception(f"Absorption voltage {ev_absorp}V out of safe range (26-32V)")

        # Allow any absorption time from 0 (disabled) to 24 hours
        if not (0 <= et_absorp <= 86400):
            raise Exception(f"Absorption time {et_absorp}s out of range (0-86400s / 0-24 hours)")

    def _read_eeprom_values(self):
        """
        Read current EEPROM charge parameter values from TriStar
        Returns actual voltages (converted from 12V-equivalent stored in EEPROM)
        """
        reg_map = {
            'EV_absorp': REG_EEPROM_EV_ABSORP,
            'EV_float': REG_EEPROM_EV_FLOAT,
            'Et_absorp': REG_EEPROM_ET_ABSORP,
            'EV_float_cancel': REG_EEPROM_EV_FLOAT_CANCEL,
        }

        values = {}
        for param, addr in reg_map.items():
            raw = self.client.read_holding_registers(addr, 1, unit=self.settings['slave_id']).registers[0]
            if param == 'Et_absorp':
                values[param] = raw  # Seconds, no scaling
            else:
                # EEPROM stores 12V-equivalent, convert to actual voltage
                voltage_12v = raw * self.v_pu * (2**-15)
                values[param] = round(voltage_12v * self.system_voltage_scale, 2)

        return values

    def _compare_profiles(self, new_profile, current_eeprom):
        """Return only parameters that differ from current EEPROM"""
        changes = {}
        tolerance = 0.01  # ±0.01V tolerance for voltage comparisons

        for param, new_value in new_profile.items():
            current_value = current_eeprom.get(param)

            if param == 'Et_absorp':
                if current_value != new_value:
                    changes[param] = new_value
            else:
                if abs(current_value - new_value) > tolerance:
                    changes[param] = new_value

        return changes

    def _write_eeprom_parameter(self, param, value):
        """
        Write single EEPROM parameter
        Converts actual voltage to 12V-equivalent before writing to EEPROM
        """
        reg_map = {
            'EV_absorp': REG_EEPROM_EV_ABSORP,
            'EV_float': REG_EEPROM_EV_FLOAT,
            'Et_absorp': REG_EEPROM_ET_ABSORP,
            'EV_float_cancel': REG_EEPROM_EV_FLOAT_CANCEL,
        }

        addr = reg_map[param]

        if param == 'Et_absorp':
            raw_value = int(value)
        else:
            # Convert actual voltage to 12V-equivalent for EEPROM storage
            voltage_12v = value / self.system_voltage_scale
            # Scale to raw register value (use round() not int() for proper rounding)
            raw_value = round(voltage_12v / (self.v_pu * (2**-15)))

        logging.info(f"Writing {param} = {value} (12V-eq: {value / self.system_voltage_scale if param != 'Et_absorp' else 'N/A'}, raw: {raw_value}) to EEPROM register 0x{addr:04X}")
        self.client.write_register(addr, raw_value, unit=self.settings['slave_id'])

    def _verify_eeprom_writes(self, changes):
        """
        Verify written values match expected
        Converts from 12V-equivalent stored in EEPROM to actual voltage for comparison
        """
        for param, expected_value in changes.items():
            reg_map = {
                'EV_absorp': REG_EEPROM_EV_ABSORP,
                'EV_float': REG_EEPROM_EV_FLOAT,
                'Et_absorp': REG_EEPROM_ET_ABSORP,
                'EV_float_cancel': REG_EEPROM_EV_FLOAT_CANCEL,
            }

            addr = reg_map[param]
            raw = self.client.read_holding_registers(addr, 1, unit=self.settings['slave_id']).registers[0]

            if param == 'Et_absorp':
                actual_value = raw
                if actual_value != expected_value:
                    raise Exception(f"Verification failed for {param}: expected {expected_value}, got {actual_value}")
            else:
                # Convert from 12V-equivalent to actual voltage
                voltage_12v = raw * self.v_pu * (2**-15)
                actual_value = round(voltage_12v * self.system_voltage_scale, 2)
                if abs(actual_value - expected_value) > 0.05:
                    raise Exception(f"Verification failed for {param}: expected {expected_value:.2f}V, got {actual_value:.2f}V")

            logging.info(f"✓ Verified {param} = {actual_value}")

    def _backup_eeprom(self, eeprom_values, reason):
        """Create timestamped EEPROM backup"""
        backup_dir = Path("/data/dbus-tristar/eeprom_backups")
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"backup_{timestamp}.json"

        backup_data = {
            "timestamp": datetime.now().isoformat(),
            "reason": reason,
            "values": eeprom_values
        }

        with open(backup_file, 'w') as f:
            json.dump(backup_data, f, indent=2)

        # Keep only last 10 backups
        backups = sorted(backup_dir.glob("backup_*.json"))
        if len(backups) > 10:
            for old_backup in backups[:-10]:
                old_backup.unlink()

        logging.info(f"EEPROM backup saved: {backup_file}")
        return backup_data

    def _read_eeprom_charge_settings(self):
        """
        Read EEPROM charge settings and update D-Bus paths
        Called: at startup, after EEPROM write, or on-demand
        NOT called in main poll loop (per Morningstar recommendation)
        """
        eeprom_regs = self.read_input_registers(0xE000, 18)  # Read EV_absorp through Evb_ref_lim
        if eeprom_regs and len(eeprom_regs) >= 18:
            # Read 12V-equivalent values from EEPROM
            ev_absorp_12v = eeprom_regs[0] * self.v_pu / 32768.0  # 0xE000
            ev_float_12v = eeprom_regs[1] * self.v_pu / 32768.0   # 0xE001
            et_absorp = eeprom_regs[2]                            # 0xE002 (seconds, no scaling)
            ev_float_cancel_12v = eeprom_regs[5] * self.v_pu / 32768.0  # 0xE005
            ev_eq_12v = eeprom_regs[7] * self.v_pu / 32768.0      # 0xE007
            ev_tempcomp = eeprom_regs[13] * self.v_pu / 32768.0  # 0xE00D (V/C, no system scale)
            evb_ref_lim_12v = eeprom_regs[16] * self.v_pu / 32768.0  # 0xE010

            # Convert to actual voltages for display (multiply by system voltage scale)
            ev_absorp = ev_absorp_12v * self.system_voltage_scale
            ev_float = ev_float_12v * self.system_voltage_scale
            ev_float_cancel = ev_float_cancel_12v * self.system_voltage_scale
            ev_eq = ev_eq_12v * self.system_voltage_scale
            evb_ref_lim = evb_ref_lim_12v * self.system_voltage_scale

            self.dbus['/Custom/EEPROM/AbsorptionVoltage'] = round(ev_absorp, 2)
            self.dbus['/Custom/EEPROM/FloatVoltage'] = round(ev_float, 2)
            self.dbus['/Custom/EEPROM/AbsorptionTime'] = et_absorp
            self.dbus['/Custom/EEPROM/FloatCancelVoltage'] = round(ev_float_cancel, 2)
            self.dbus['/Custom/EEPROM/EqualizeVoltage'] = round(ev_eq, 2)
            self.dbus['/Custom/EEPROM/TempCompensation'] = round(ev_tempcomp, 4)
            self.dbus['/Custom/EEPROM/MaxRegulationLimit'] = round(evb_ref_lim, 2)

            logging.debug("EEPROM charge settings refreshed")
        else:
            logging.warning("Failed to read EEPROM charge settings")

    def _read_eeprom_lifetime_kwh(self):
        """
        Read EEPROM lifetime kWh counters and update D-Bus paths
        Called: at startup, every 30 minutes
        NOT called in main poll loop (per Morningstar recommendation)
        """
        kwh_regs = self.read_input_registers(0xE086, 2)
        if kwh_regs and len(kwh_regs) >= 2:
            # Spec page 15: kWhc registers already in kWh units (no scaling needed)
            ekwhc_r = kwh_regs[0]  # 0xE086 - Resetable kWh
            ekwhc_t = kwh_regs[1]  # 0xE087 - Total kWh (lifetime)

            self.dbus['/Custom/EEPROM/ChargeKwhResetable'] = round(ekwhc_r, 1)
            self.dbus['/Custom/EEPROM/ChargeKwhTotal'] = round(ekwhc_t, 1)

            logging.debug(f"EEPROM lifetime kWh refreshed: {ekwhc_t} kWh total")
        else:
            logging.warning("Failed to read EEPROM lifetime kWh")

    def _update_active_eeprom_display(self, eeprom_values):
        """Update D-Bus paths showing active EEPROM values"""
        self.dbus['/Custom/EEPROM/AbsorptionVoltage'] = eeprom_values.get('EV_absorp', 0.0)
        self.dbus['/Custom/EEPROM/FloatVoltage'] = eeprom_values.get('EV_float', 0.0)
        self.dbus['/Custom/EEPROM/AbsorptionTime'] = eeprom_values.get('Et_absorp', 0)
        self.dbus['/Custom/EEPROM/FloatCancelVoltage'] = eeprom_values.get('EV_float_cancel', 0.0)

    def _reconnect_modbus(self):
        """Re-establish Modbus connection after reset"""
        max_retries = 5
        for attempt in range(max_retries):
            try:
                self.client.close()
                sleep(2)
                self.client.connect()
                # Test connection
                self.client.read_holding_registers(REG_V_PU, 1, unit=self.settings['slave_id'])
                logging.info("Modbus reconnected successfully")
                return
            except Exception as e:
                if attempt < max_retries - 1:
                    logging.warning(f"Reconnect attempt {attempt+1} failed: {e}")
                    sleep(3)
                else:
                    raise Exception(f"Failed to reconnect after {max_retries} attempts: {e}")

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
    driver = None

    def cleanup_and_exit(signum=None, frame=None):
        """Handle shutdown signals gracefully"""
        sig_name = signal.Signals(signum).name if signum else "unknown"
        logging.info(f"Received signal {sig_name} - shutting down gracefully...")

        # Save state before shutdown
        if driver:
            try:
                driver._save_state()
                logging.info("✓ State saved before shutdown")
            except Exception as e:
                logging.error(f"Failed to save state on shutdown: {e}")

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
