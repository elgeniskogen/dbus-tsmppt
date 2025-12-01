#!/usr/bin/env python3

"""
Quick test script to verify Modbus TCP connection to TriStar MPPT
Run this before installing the driver to verify connectivity
"""

import sys
from pymodbus.client import ModbusTcpClient

def test_connection(host, port=502, slave_id=1):
    """Test Modbus connection to TriStar MPPT"""

    print(f"Testing connection to {host}:{port} (slave {slave_id})...")

    try:
        # Create client
        client = ModbusTcpClient(host=host, port=port, timeout=10)

        # Connect
        if not client.connect():
            print("❌ Failed to connect")
            return False

        print("✓ Connected successfully")

        # Try to read scaling factors (registers 0-5)
        result = client.read_input_registers(address=0, count=6, unit=slave_id)

        if result.isError():
            print(f"❌ Modbus error: {result}")
            client.close()
            return False

        print("✓ Read registers successfully")

        # Parse voltage scaling
        v_pu = float(result.registers[0]) + (float(result.registers[1]) / 65536.0)
        i_pu = float(result.registers[2]) + (float(result.registers[3]) / 65536.0)

        print(f"✓ Voltage scaling: {v_pu:.6f}")
        print(f"✓ Current scaling: {i_pu:.6f}")

        # Read firmware version
        ver = result.registers[4]
        firmware = (
            ((ver >> 12) & 0x0f) * 1000 +
            ((ver >> 8) & 0x0f) * 100 +
            ((ver >> 4) & 0x0f) * 10 +
            (ver & 0x0f)
        )
        print(f"✓ Firmware version: {firmware}")

        # Read model
        result = client.read_input_registers(address=57548, count=1, unit=slave_id)
        if not result.isError():
            model_map = {
                0: "TriStar MPPT 45",
                1: "TriStar MPPT 60",
                2: "TriStar MPPT 30"
            }
            model = model_map.get(result.registers[0], f"Unknown ({result.registers[0]})")
            print(f"✓ Model: {model}")

        # Read serial number
        result = client.read_input_registers(address=57536, count=4, unit=slave_id)
        if not result.isError():
            serial = 0
            for reg in result.registers:
                low = (reg & 0xff) - 0x30
                high = (reg >> 8) - 0x30
                serial = serial * 100 + high * 10 + low
            print(f"✓ Serial number: {serial}")

        # Read current battery voltage
        result = client.read_input_registers(address=24, count=1, unit=slave_id)
        if not result.isError():
            v_bat = result.registers[0] * v_pu / 32768.0
            print(f"✓ Battery voltage: {v_bat:.2f}V")

        # Read charge state
        result = client.read_input_registers(address=50, count=1, unit=slave_id)
        if not result.isError():
            states = {
                0: "START",
                1: "NIGHT_CHECK",
                2: "DISCONNECT",
                3: "NIGHT",
                4: "FAULT",
                5: "MPPT (Bulk)",
                6: "ABSORPTION",
                7: "FLOAT",
                8: "EQUALIZE",
                9: "SLAVE"
            }
            state = states.get(result.registers[0], f"Unknown ({result.registers[0]})")
            print(f"✓ Charge state: {state}")

        client.close()

        print("\n✅ All tests passed! Your TriStar MPPT is ready for dbus-tsmppt.")
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 test_connection.py <ip-address> [port] [slave-id]")
        print("Example: python3 test_connection.py 192.168.1.200")
        print("Example: python3 test_connection.py 192.168.1.200 502 1")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 502
    slave_id = int(sys.argv[3]) if len(sys.argv) > 3 else 1

    success = test_connection(host, port, slave_id)
    sys.exit(0 if success else 1)
