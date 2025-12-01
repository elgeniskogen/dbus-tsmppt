# dbus-tsmppt - Python Version

Modern Python driver for Morningstar TriStar MPPT charge controllers on Venus OS.

## Features

- **Pure Python** - No Qt or C++ dependencies
- **Modern Venus OS** - Compatible with Venus OS v2.80+ and v3.x
- **Modbus TCP** - Connects to TriStar MPPT via Ethernet
- **Auto-discovery** - Shows up automatically in Venus OS GUI
- **Full VRM support** - All data visible in VRM Portal
- **Easy installation** - Simple install script
- **Robust** - Automatic reconnection on connection loss
- **Configurable** - Settings via D-Bus/GUI

## What's Different from the Qt/C++ Version?

| Feature | Old (Qt/C++) | New (Python) |
|---------|--------------|--------------|
| Language | C++/Qt4 | Python 3 |
| Dependencies | Qt4, libmodbus, SDK | pymodbus only |
| Venus OS | v2.30 (2019) | v2.80+ and v3.x |
| GUI Integration | Manual QML editing | Automatic |
| Installation | Complex build | Simple script |
| Settings | Manual XML | GUI + D-Bus |
| Maintenance | Difficult | Easy |

## Requirements

- Venus OS device (Cerbo GX, Venus GX, etc.) running v2.80 or later
- Morningstar TriStar MPPT 30/45/60 charge controller
- Network connection between Venus OS and TriStar MPPT
- TriStar MPPT with Ethernet adapter or serial-to-ethernet converter

## Installation

### Step 1: Enable SSH on Venus OS

1. Go to Settings → General → Access level → Set to "Superuser"
2. Enable SSH in Settings → General → Remote support

### Step 2: Copy Files to Venus OS

```bash
# On your computer, copy files to Venus OS
scp -r * root@<venus-ip>:/tmp/dbus-tsmppt/
```

Replace `<venus-ip>` with your Venus OS IP address (e.g., `192.168.1.100`)

### Step 3: Run Installation Script

```bash
# SSH into Venus OS
ssh root@<venus-ip>

# Go to installation directory
cd /tmp/dbus-tsmppt

# Run installation script
chmod +x install.sh
./install.sh
```

### Step 4: Configure TriStar IP Address

```bash
# Set your TriStar MPPT IP address
dbus -y com.victronenergy.settings /Settings/TristarMPPT/IPAddress SetValue "192.168.1.200"

# Restart service to apply settings
svc -t /service/dbus-tsmppt
```

### Step 5: Verify Installation

```bash
# Check service status
svstat /service/dbus-tsmppt

# Check logs
tail -f /var/log/dbus-tsmppt/current

# Check D-Bus registration
dbus-spy | grep solarcharger
```

You should see output like:
```
com.victronenergy.solarcharger.tsmppt
```

## Configuration

### Via D-Bus Command Line

```bash
# Set IP address
dbus -y com.victronenergy.settings /Settings/TristarMPPT/IPAddress SetValue "192.168.1.200"

# Set Modbus port (default: 502)
dbus -y com.victronenergy.settings /Settings/TristarMPPT/PortNumber SetValue 502

# Set update interval in milliseconds (default: 5000 = 5 seconds)
dbus -y com.victronenergy.settings /Settings/TristarMPPT/Interval SetValue 5000

# Restart service after changes
svc -t /service/dbus-tsmppt
```

### Via GUI (Future Enhancement)

A settings page similar to the Qt version can be added to the Venus OS GUI. For now, use D-Bus commands or edit `/data/conf/settings.xml`.

## Monitored Values

The driver publishes the following data to D-Bus:

### Real-time Values
- Battery voltage (V)
- Battery current (A)
- Battery temperature (°C)
- PV array voltage (V)
- PV array current (A)
- Output power (W)
- Charge state (Off/Bulk/Absorption/Float/Equalize)

### Daily History
- Daily yield (kWh)
- Max battery voltage
- Min battery voltage
- Max PV voltage
- Max power
- Time in bulk (minutes)
- Time in absorption (minutes)
- Time in float (minutes)

### Total Yield
- Total yield (user resettable)
- Total yield (system)

### Device Info
- Product name (TriStar MPPT 30/45/60)
- Serial number
- Firmware version
- Hardware version

## Troubleshooting

### Service won't start

```bash
# Check service status
svstat /service/dbus-tsmppt

# Check logs for errors
tail -f /var/log/dbus-tsmppt/current

# Manually run to see errors
python3 /data/dbus-tsmppt/dbus-tsmppt.py
```

### No data shown in GUI

1. Verify IP address is set:
   ```bash
   dbus -y com.victronenergy.settings /Settings/TristarMPPT/IPAddress GetValue
   ```

2. Check connection to TriStar:
   ```bash
   ping <tristar-ip>
   ```

3. Test Modbus connection:
   ```bash
   python3 -m pymodbus.console tcp --host <tristar-ip> --port 502
   ```

4. Check D-Bus registration:
   ```bash
   dbus -y com.victronenergy.solarcharger.tsmppt /ProductName GetValue
   ```

### Connection timeouts

- Verify TriStar MPPT Modbus TCP is enabled
- Check network connectivity
- Verify correct IP address and port
- Check firewall rules if applicable
- Increase timeout in code if on slow network

### pymodbus not found

```bash
opkg update
opkg install python3-pymodbus
```

## Uninstallation

```bash
cd /data/dbus-tsmppt
chmod +x uninstall.sh
./uninstall.sh
```

## Development

### Testing on Linux

You can test the driver on a Linux machine with D-Bus session bus:

```bash
# Install dependencies
pip3 install pymodbus dbus-python pygobject

# Run with session bus
DBUS_SESSION_BUS_ADDRESS=unix:path=/tmp/dbus-session python3 dbus-tsmppt.py
```

### Debug Mode

Enable debug logging by modifying [dbus-tsmppt.py](dbus-tsmppt.py):

```python
logging.basicConfig(
    level=logging.DEBUG,  # Change from INFO to DEBUG
    format='%(asctime)s %(levelname)-8s %(message)s'
)
```

### Modbus Register Map

See [tsmppt.cpp](software/src/tsmppt.cpp) for complete register definitions.

Key registers:
- 0-5: Scaling factors and firmware version
- 24-79: Dynamic values (voltage, current, power, etc.)
- 57536-57549: Device info (serial, model, hardware version)

## License

MIT License - see [LICENSE](LICENSE)

## Credits

- Original Qt/C++ driver by Ole André Sæther
- Python rewrite modernized for Venus OS v3.x
- Based on Victron Energy Venus OS dbus-mqtt patterns

## Support

For issues and questions:
- Check logs first: `tail -f /var/log/dbus-tsmppt/current`
- Verify network connectivity to TriStar MPPT
- Check Venus OS version (needs v2.80+)
- Review Modbus settings on TriStar MPPT

## Version History

### v2.0 (2024) - Python Rewrite
- Complete rewrite in Python 3
- Modern Venus OS compatibility (v2.80+, v3.x)
- Automatic GUI integration
- Simplified installation
- Improved error handling and logging

### v1.17 (2019) - Last Qt/C++ Version
- Qt4-based C++ driver
- Venus OS v2.30 compatibility
- Manual GUI integration required
