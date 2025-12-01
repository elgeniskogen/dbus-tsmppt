#!/usr/bin/env python3

"""
Morningstar TriStar MPPT driver for Venus OS
Reads charge controller data via Modbus TCP and publishes to D-Bus

Uses SettingsDevice for configuration via D-Bus
Configure via: dbus -y com.victronenergy.settings /Settings/TristarMPPT/...
"""

import logging
import sys
import dbus
import dbus.mainloop.glib
from gi.repository import GLib
from time import time

# pymodbus v2.x (Venus OS) vs v3.x compatibility
try:
    from pymodbus.client import ModbusTcpClient
except ImportError:
    from pymodbus.client.sync import ModbusTcpClient

# Import Victron packages
sys.path.insert(1, '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python')
from vedbus import VeDbusService
from settingsdevice import SettingsDevice

VERSION = "2.0"
PRODUCT_ID = 0xABCD  # Placeholder - can be registered with Victron

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
                'ip_address': ['/Settings/TristarMPPT/IPAddress', '192.168.1.100', 0, 0],
                'modbus_port': ['/Settings/TristarMPPT/PortNumber', 502, 1, 65535],
                'poll_interval': ['/Settings/TristarMPPT/Interval', 5000, 1000, 60000],
                'slave_id': ['/Settings/TristarMPPT/SlaveID', 1, 1, 247],
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

        # D-Bus service
        self.dbus = VeDbusService('com.victronenergy.solarcharger.tristar_0', register=False)
        self._setup_dbus_paths()
        self.dbus.register()

        # Start periodic updates
        # Convert milliseconds to seconds
        poll_interval_ms = int(self.settings['poll_interval'])
        poll_interval_sec = poll_interval_ms // 1000
        logging.info(f"Starting timer with interval: {poll_interval_sec} seconds ({poll_interval_ms}ms)")
        timer_id = GLib.timeout_add_seconds(poll_interval_sec, self.update)
        logging.info(f"Timer registered with ID: {timer_id}")

        logging.info("TriStar MPPT driver initialized")
        logging.info(f"Settings: {self.settings['ip_address']}:{self.settings['modbus_port']}")

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
        s.add_path('/State', 0)

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

    def _setting_changed(self, setting, old, new):
        """Called when a setting changes in the GUI"""
        logging.info(f"Setting '{setting}' changed from '{old}' to '{new}'")

        if setting == 'poll_interval':
            # Restart timer with new interval
            logging.info("Poll interval changed - will take effect on next update")
        elif setting in ['ip_address', 'modbus_port', 'slave_id']:
            # Force re-initialization with new settings
            logging.info("Connection settings changed - will re-initialize on next update")
            self.initialized = False

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
                        logging.warning(f"Connection failed, retry {attempt + 1}/5")
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
                        logging.warning(f"Modbus error, retry {attempt + 1}/5")
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
                    logging.warning(f"Exception, retry {attempt + 1}/5: {e}")
                else:
                    logging.error(f"Exception after 5 retries: {e}")

                try:
                    client.close()
                except:
                    pass

                if attempt == 4:
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

            # Read all dynamic registers
            regs = self.read_input_registers(REG_V_BAT, REG_T_FLOAT - REG_V_BAT + 1)
            if regs is None:
                self.dbus['/Connected'] = 0
                self.initialized = False
                return True

            # Mark as connected
            self.dbus['/Connected'] = 1

            # Helper to get register by address
            def reg(addr):
                return regs[addr - REG_V_BAT]

            # Calculate time delta for bulk charge tracking
            now = time()
            dt_ms = (now - self.last_update) * 1000
            self.last_update = now

            # Parse and convert values
            v_bat = reg(REG_V_BAT) * self.v_pu / 32768.0
            i_cc = max(0.0, self._to_signed(reg(REG_I_CC_1M)) * self.i_pu / 32768.0)
            v_pv = reg(REG_V_PV) * self.v_pu / 32768.0
            i_pv = reg(REG_I_PV) * self.i_pu / 32768.0
            p_out = reg(REG_POUT) * self.i_pu * self.v_pu / 131072.0

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
            self.dbus['/Pv/I'] = round(i_pv, 2)
            self.dbus['/Dc/0/Voltage'] = round(v_bat, 2)
            self.dbus['/Dc/0/Current'] = round(i_cc, 2)
            self.dbus['/Dc/0/Temperature'] = round(self._to_signed(reg(REG_T_BAT)), 1)
            self.dbus['/Yield/Power'] = round(p_out, 0)
            self.dbus['/State'] = cs

            # History
            self.dbus['/History/Daily/0/Yield'] = round(reg(REG_WHC_DAILY) / 1000.0, 2)
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
            self.dbus['/History/Daily/0/TimeInBulk'] = int(self.t_bulk_ms / (1000 * 60))
            self.dbus['/History/Daily/0/TimeInAbsorption'] = reg(REG_T_ABS) // 60
            self.dbus['/History/Daily/0/TimeInFloat'] = reg(REG_T_FLOAT) // 60

            # Total yield
            daily_kwh = reg(REG_WHC_DAILY) / 1000.0
            self.dbus['/Yield/User'] = round(reg(REG_KWH_TOTAL_RES) + daily_kwh, 0)
            self.dbus['/Yield/System'] = round(reg(REG_KWH_TOTAL) + daily_kwh, 0)

        except Exception as e:
            logging.error(f"Update error: {e}", exc_info=True)

        return True  # Continue timer

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

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    driver = TriStarDriver()

    logging.info("✓ Driver initialized")
    logging.info("Configure via: dbus -y com.victronenergy.settings /Settings/TristarMPPT/...")
    logging.info("Entering main loop...")

    GLib.MainLoop().run()


if __name__ == '__main__':
    main()
