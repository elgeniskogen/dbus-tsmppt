#!/usr/bin/env python3

"""
Morningstar TriStar MPPT driver for Venus OS
Reads charge controller data via Modbus TCP and publishes to D-Bus
"""

import logging
import sys
import os
from time import time
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException, ConnectionException

# Victron packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python'))
from vedbus import VeDbusService
from settingsdevice import SettingsDevice
from ve_utils import exit_on_error
import dbus

VERSION = "2.0"

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

PRODUCT_ID = 0xABCD  # Dummy product ID


class TristarDevice:
    """Morningstar TriStar MPPT charge controller interface"""

    def __init__(self, host, port=502, slave_id=1, update_interval=5):
        self.host = host
        self.port = port
        self.slave_id = slave_id
        self.update_interval = update_interval

        self.client = None
        self.connected = False
        self.initialized = False

        # Scaling factors (read from device)
        self.v_pu = 0.0
        self.i_pu = 0.0

        # Static device info
        self.firmware_version = 0
        self.hardware_version = ""
        self.serial_number = ""
        self.product_name = ""

        # Dynamic values
        self.values = {}

        # Bulk charge timing
        self.t_bulk_ms = 0
        self.last_update = time()
        self.last_charge_state = 0

        logging.info(f"TristarDevice created: {host}:{port} slave={slave_id}")

    def connect(self):
        """Connect to Modbus device"""
        try:
            if self.client:
                self.client.close()

            self.client = ModbusTcpClient(
                host=self.host,
                port=self.port,
                timeout=10,
                retries=3,
                retry_on_empty=True
            )

            connected = self.client.connect()
            if not connected:
                logging.error(f"Failed to connect to {self.host}:{self.port}")
                return False

            logging.info(f"Connected to {self.host}:{self.port}")
            self.connected = True
            return True

        except Exception as e:
            logging.error(f"Connection error: {e}")
            self.connected = False
            return False

    def read_input_registers(self, address, count):
        """Read input registers with retry logic"""
        if not self.client:
            return None

        for attempt in range(5):
            try:
                result = self.client.read_input_registers(
                    address=address,
                    count=count,
                    slave=self.slave_id
                )

                if result.isError():
                    if attempt < 4:
                        logging.warning(f"Modbus error, retry {attempt + 1}/5")
                        continue
                    else:
                        logging.error(f"Modbus error after 5 retries")
                        self.connected = False
                        return None

                return result.registers

            except (ModbusException, ConnectionException) as e:
                if attempt < 4:
                    logging.warning(f"Modbus exception, retry {attempt + 1}/5: {e}")
                    continue
                else:
                    logging.error(f"Modbus exception after 5 retries: {e}")
                    self.connected = False
                    return None
            except Exception as e:
                logging.error(f"Unexpected error reading registers: {e}")
                self.connected = False
                return None

        return None

    def initialize(self):
        """Read static device information"""
        if self.initialized:
            return True

        logging.info("Initializing TriStar MPPT...")

        # Read scaling factors and firmware version
        regs = self.read_input_registers(REG_V_PU, 6)
        if regs is None:
            return False

        # Voltage scaling (32-bit float from 2 registers)
        self.v_pu = float(regs[0]) + (float(regs[1]) / 65536.0)

        # Current scaling (32-bit float from 2 registers)
        self.i_pu = float(regs[2]) + (float(regs[3]) / 65536.0)

        logging.info(f"Scaling factors: V_PU={self.v_pu:.6f}, I_PU={self.i_pu:.6f}")

        # Firmware version (BCD format)
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

        # Serial number (8 ASCII digits in 4 registers)
        regs = self.read_input_registers(REG_ESERIAL, 4)
        if regs is None:
            return False

        serial = 0
        for i, reg in enumerate(regs):
            # Each register contains 2 ASCII digits (BCD)
            low = (reg & 0xff) - 0x30
            high = (reg >> 8) - 0x30
            serial = serial * 100 + high * 10 + low

        self.serial_number = str(serial)

        logging.info(f"{self.product_name} initialized")
        logging.info(f"  Serial: {self.serial_number}")
        logging.info(f"  Hardware: v{self.hardware_version}")
        logging.info(f"  Firmware: {self.firmware_version}")

        self.initialized = True
        return True

    def update(self):
        """Read current values from device"""
        if not self.connected:
            if not self.connect():
                return False

        if not self.initialized:
            if not self.initialize():
                return False

        # Read all dynamic registers in one go (24-79)
        regs = self.read_input_registers(REG_V_BAT, REG_T_FLOAT - REG_V_BAT + 1)
        if regs is None:
            return False

        # Helper to get register value by offset from REG_V_BAT
        def reg(addr):
            return regs[addr - REG_V_BAT]

        # Calculate time delta for bulk charge tracking
        now = time()
        dt_ms = (now - self.last_update) * 1000
        self.last_update = now

        # Parse values
        self.values = {
            # Battery voltage
            'battery_voltage': reg(REG_V_BAT) * self.v_pu / 32768.0,
            'battery_voltage_max': reg(REG_V_BAT_MAX) * self.v_pu / 32768.0,
            'battery_voltage_min': reg(REG_V_BAT_MIN) * self.v_pu / 32768.0,

            # Battery temperature (signed)
            'battery_temperature': self._to_signed(reg(REG_T_BAT)),

            # Charge current (1 min average, signed, clamp to >= 0)
            'charge_current': max(0.0, self._to_signed(reg(REG_I_CC_1M)) * self.i_pu / 32768.0),

            # Output power
            'output_power': reg(REG_POUT) * self.i_pu * self.v_pu / 131072.0,

            # PV array
            'pv_voltage': reg(REG_V_PV) * self.v_pu / 32768.0,
            'pv_voltage_max': reg(REG_V_PV_MAX) * self.v_pu / 32768.0,
            'pv_current': reg(REG_I_PV) * self.i_pu / 32768.0,

            # Energy (daily in Wh, convert to kWh for Venus)
            'yield_daily': reg(REG_WHC_DAILY) / 1000.0,

            # Energy (total in kWh)
            'yield_total_resettable': float(reg(REG_KWH_TOTAL_RES)),
            'yield_total': float(reg(REG_KWH_TOTAL)),

            # Max power daily
            'power_max_daily': reg(REG_POUT_MAX_DAILY) * self.i_pu * self.v_pu / 131072.0,

            # Charge state
            'charge_state_raw': reg(REG_CHARGE_STATE),

            # Time in charge stages (convert seconds to minutes)
            'time_absorption': reg(REG_T_ABS) // 60,
            'time_float': reg(REG_T_FLOAT) // 60,
        }

        # Calculate bulk charge time (Venus doesn't provide this register)
        cs = self.values['charge_state_raw']
        if cs == CS_BULK:
            self.t_bulk_ms += dt_ms
        elif cs == CS_NIGHT:
            self.t_bulk_ms = 0

        self.values['time_bulk'] = int(self.t_bulk_ms / (1000 * 60))

        # Map charge state to Victron format
        self.values['charge_state'] = CHARGE_STATE_MAP.get(cs, 0)

        # Add yield with daily included (for User and System)
        daily_kwh = self.values['yield_daily']
        self.values['yield_user'] = self.values['yield_total_resettable'] + daily_kwh
        self.values['yield_system'] = self.values['yield_total'] + daily_kwh

        self.last_charge_state = cs

        return True

    @staticmethod
    def _to_signed(value):
        """Convert 16-bit unsigned to signed"""
        if value >= 32768:
            return value - 65536
        return value

    def close(self):
        """Close Modbus connection"""
        if self.client:
            self.client.close()
            self.connected = False
            logging.info("Connection closed")


class DBusTristarService:
    """D-Bus service for TriStar MPPT"""

    def __init__(self, device, servicename='com.victronenergy.solarcharger'):
        self.device = device
        self.servicename = servicename

        # Create D-Bus service
        self.dbusservice = VeDbusService(f"{servicename}.tsmppt")

        # Setup paths
        self._setup_paths()

        logging.info(f"D-Bus service registered: {servicename}.tsmppt")

    def _setup_paths(self):
        """Setup all D-Bus paths"""
        s = self.dbusservice

        # Management
        s.add_path('/Mgmt/ProcessName', __file__)
        s.add_path('/Mgmt/ProcessVersion', VERSION)
        s.add_path('/Mgmt/Connection', 'Modbus TCP')

        # Device info
        s.add_path('/ProductId', PRODUCT_ID)
        s.add_path('/ProductName', self.device.product_name)
        s.add_path('/FirmwareVersion', self.device.firmware_version)
        s.add_path('/HardwareVersion', self.device.hardware_version)
        s.add_path('/Serial', self.device.serial_number)
        s.add_path('/DeviceInstance', 0)
        s.add_path('/Connected', 0)
        s.add_path('/Mode', 1)
        s.add_path('/ErrorCode', 0)

        # PV array
        s.add_path('/Pv/V', None, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/Pv/I', None, gettextcallback=lambda p, v: f"{v}A")

        # Battery
        s.add_path('/Dc/0/Voltage', None, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/Dc/0/Current', None, gettextcallback=lambda p, v: f"{v}A")
        s.add_path('/Dc/0/Temperature', None)

        # Power and state
        s.add_path('/Yield/Power', None, gettextcallback=lambda p, v: f"{v}W")
        s.add_path('/State', None)

        # History
        s.add_path('/History/Overall/DaysAvailable', 1)
        s.add_path('/History/Daily/0/Yield', None, gettextcallback=lambda p, v: f"{v}kWh")
        s.add_path('/History/Daily/0/MaxPower', None, gettextcallback=lambda p, v: f"{v}W")
        s.add_path('/History/Daily/0/MaxPvVoltage', None, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/History/Daily/0/MaxBatteryVoltage', None, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/History/Daily/0/MinBatteryVoltage', None, gettextcallback=lambda p, v: f"{v}V")
        s.add_path('/History/Daily/0/TimeInBulk', None)
        s.add_path('/History/Daily/0/TimeInAbsorption', None)
        s.add_path('/History/Daily/0/TimeInFloat', None)

        # Total yield
        s.add_path('/Yield/User', None, gettextcallback=lambda p, v: f"{v}kWh")
        s.add_path('/Yield/System', None, gettextcallback=lambda p, v: f"{v}kWh")

    def update(self):
        """Update D-Bus values from device"""
        if not self.device.update():
            # Connection lost
            self.dbusservice['/Connected'] = 0
            return False

        # Connection OK
        self.dbusservice['/Connected'] = 1

        v = self.device.values

        # PV array
        self.dbusservice['/Pv/V'] = round(v['pv_voltage'], 2)
        self.dbusservice['/Pv/I'] = round(v['pv_current'], 2)

        # Battery
        self.dbusservice['/Dc/0/Voltage'] = round(v['battery_voltage'], 2)
        self.dbusservice['/Dc/0/Current'] = round(v['charge_current'], 2)
        self.dbusservice['/Dc/0/Temperature'] = round(v['battery_temperature'], 1)

        # Power and state
        self.dbusservice['/Yield/Power'] = round(v['output_power'], 0)
        self.dbusservice['/State'] = v['charge_state']

        # History daily
        self.dbusservice['/History/Daily/0/Yield'] = round(v['yield_daily'], 2)
        self.dbusservice['/History/Daily/0/MaxPower'] = round(v['power_max_daily'], 0)
        self.dbusservice['/History/Daily/0/MaxPvVoltage'] = round(v['pv_voltage_max'], 2)
        self.dbusservice['/History/Daily/0/MaxBatteryVoltage'] = round(v['battery_voltage_max'], 2)
        self.dbusservice['/History/Daily/0/MinBatteryVoltage'] = round(v['battery_voltage_min'], 2)
        self.dbusservice['/History/Daily/0/TimeInBulk'] = v['time_bulk']
        self.dbusservice['/History/Daily/0/TimeInAbsorption'] = v['time_absorption']
        self.dbusservice['/History/Daily/0/TimeInFloat'] = v['time_float']

        # Total yield
        self.dbusservice['/Yield/User'] = round(v['yield_user'], 0)
        self.dbusservice['/Yield/System'] = round(v['yield_system'], 0)

        return True


def main():
    """Main application entry point"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)-8s %(message)s'
    )

    logging.info(f"dbus-tsmppt v{VERSION} starting")

    # Get settings from D-Bus
    settings = SettingsDevice(
        bus=dbus.SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else dbus.SystemBus(),
        supportedSettings={
            'ip': ['/Settings/TristarMPPT/IPAddress', '', 0, 0],
            'port': ['/Settings/TristarMPPT/PortNumber', 502, 0, 65535],
            'interval': ['/Settings/TristarMPPT/Interval', 5000, 1000, 60000],
        },
        eventCallback=None
    )

    # Wait for settings to be available
    ip = settings['ip']
    port = settings['port']
    interval = settings['interval'] / 1000.0  # Convert ms to seconds

    if not ip:
        logging.error("No IP address configured in /Settings/TristarMPPT/IPAddress")
        sys.exit(1)

    logging.info(f"Configuration: {ip}:{port}, interval={interval}s")

    # Create device and service
    device = TristarDevice(ip, port, update_interval=interval)
    service = DBusTristarService(device)

    # Main loop
    from gi.repository import GLib

    def update_callback():
        """Periodic update callback"""
        try:
            service.update()
        except Exception as e:
            logging.error(f"Update error: {e}", exc_info=True)
        return True

    # Schedule periodic updates
    GLib.timeout_add(int(interval * 1000), update_callback)

    logging.info("Entering main loop")
    mainloop = GLib.MainLoop()
    mainloop.run()


if __name__ == '__main__':
    main()
