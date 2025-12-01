#!/usr/bin/env python3

"""
Mock TriStar MPPT driver for Venus OS - TESTING ONLY
Generates fake data to test GUI without actual TriStar connection
"""

import logging
import sys
import dbus
import dbus.mainloop.glib
from gi.repository import GLib
from time import time
import random
import math

# Import Victron packages
sys.path.insert(1, '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python')
from vedbus import VeDbusService
from settingsdevice import SettingsDevice

VERSION = "2.0-MOCK"
PRODUCT_ID = 0xABCD

# Charge states for rotation
STATES = [
    (3, "BULK"),      # Victron state 3 = BULK
    (4, "ABSORPTION"), # Victron state 4 = ABSORPTION
    (5, "FLOAT"),      # Victron state 5 = FLOAT
]


class MockTriStarDriver:
    """Mock driver that generates fake TriStar data"""

    def __init__(self):
        self.bus = dbus.SystemBus()

        # Settings
        self.settings = SettingsDevice(
            bus=self.bus,
            supportedSettings={
                'poll_interval': ['/Settings/TristarMPPT/Interval', 2000, 1000, 60000],
            },
            eventCallback=None
        )

        # Mock state
        self.start_time = time()
        self.state_index = 0
        self.daily_yield = 0.0
        self.total_yield = 523.4  # Fake total

        # D-Bus service
        self.dbus = VeDbusService('com.victronenergy.solarcharger.tristar_0', register=False)
        self._setup_dbus_paths()
        self.dbus.register()

        # Set static info
        self.dbus['/ProductName'] = "TriStar MPPT 60"
        self.dbus['/FirmwareVersion'] = 1234
        self.dbus['/HardwareVersion'] = "3.1"
        self.dbus['/Serial'] = "12345678"
        self.dbus['/Connected'] = 1

        # Start periodic updates
        poll_interval_ms = int(self.settings['poll_interval'])
        poll_interval_sec = poll_interval_ms // 1000
        logging.info(f"Mock driver: updating every {poll_interval_sec} seconds")
        GLib.timeout_add_seconds(poll_interval_sec, self.update)

        logging.info("Mock TriStar MPPT driver initialized")

    def _setup_dbus_paths(self):
        """Setup all D-Bus paths"""
        s = self.dbus

        # Management
        s.add_path('/Mgmt/ProcessName', __file__)
        s.add_path('/Mgmt/ProcessVersion', VERSION)
        s.add_path('/Mgmt/Connection', 'MOCK - Simulated Data')

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

    def update(self):
        """Generate fake data"""
        elapsed = time() - self.start_time

        # Rotate through charge states every 30 seconds
        self.state_index = int(elapsed / 30) % len(STATES)
        state, state_name = STATES[self.state_index]

        # Generate realistic varying values using sine waves
        base_pv_voltage = 38.0 + 3.0 * math.sin(elapsed / 10)
        base_pv_current = 8.0 + 4.0 * math.sin(elapsed / 15)
        base_battery_voltage = 25.6 + 1.2 * math.sin(elapsed / 20)

        # Add some noise
        pv_voltage = base_pv_voltage + random.uniform(-0.5, 0.5)
        pv_current = max(0, base_pv_current + random.uniform(-1.0, 1.0))
        battery_voltage = base_battery_voltage + random.uniform(-0.1, 0.1)
        battery_current = pv_current * 0.95  # Slightly less due to losses

        # Power
        power = pv_voltage * pv_current

        # Temperature
        temperature = 22 + 3 * math.sin(elapsed / 40)

        # Daily yield increases slowly
        self.daily_yield += (power / 1000.0) * (2.0 / 3600.0)  # kWh (2 sec intervals)

        # Update D-Bus
        self.dbus['/Pv/V'] = round(pv_voltage, 2)
        self.dbus['/Pv/I'] = round(pv_current, 2)
        self.dbus['/Dc/0/Voltage'] = round(battery_voltage, 2)
        self.dbus['/Dc/0/Current'] = round(battery_current, 2)
        self.dbus['/Dc/0/Temperature'] = round(temperature, 1)
        self.dbus['/Yield/Power'] = round(power, 0)
        self.dbus['/State'] = state

        # History
        self.dbus['/History/Daily/0/Yield'] = round(self.daily_yield, 2)
        self.dbus['/History/Daily/0/MaxPower'] = round(power * 1.2, 0)  # Fake max
        self.dbus['/History/Daily/0/MaxPvVoltage'] = round(pv_voltage * 1.1, 2)
        self.dbus['/History/Daily/0/MaxBatteryVoltage'] = round(battery_voltage + 0.5, 2)
        self.dbus['/History/Daily/0/MinBatteryVoltage'] = round(battery_voltage - 1.0, 2)
        self.dbus['/History/Daily/0/TimeInBulk'] = int(elapsed / 60) if state_name == "BULK" else 45
        self.dbus['/History/Daily/0/TimeInAbsorption'] = int(elapsed / 60) if state_name == "ABSORPTION" else 30
        self.dbus['/History/Daily/0/TimeInFloat'] = int(elapsed / 60) if state_name == "FLOAT" else 120

        # Total yield
        self.dbus['/Yield/User'] = round(self.total_yield + self.daily_yield, 0)
        self.dbus['/Yield/System'] = round(self.total_yield + self.daily_yield, 0)

        logging.info(f"Mock update: {state_name}, PV={pv_voltage:.1f}V/{pv_current:.1f}A, "
                    f"Bat={battery_voltage:.1f}V, P={power:.0f}W, Yield={self.daily_yield:.2f}kWh")

        return True  # Continue timer


def main():
    """Main entry point"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)-8s %(message)s'
    )

    logging.info(f"dbus-tristar MOCK v{VERSION} starting")
    logging.info("⚠️  MOCK MODE - Generating fake data for testing!")

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    driver = MockTriStarDriver()

    logging.info("✓ Mock driver initialized")
    logging.info("Watch Venus OS GUI - you should see a Solar Charger with changing data")
    logging.info("Entering main loop...")

    GLib.MainLoop().run()


if __name__ == '__main__':
    main()
