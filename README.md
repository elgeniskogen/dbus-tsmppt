# TriStar MPPT Driver for Venus OS

**Modern Python driver for Morningstar TriStar MPPT solar charge controllers**

✅ **Production-ready** - Tested on Venus OS v3.67
✅ **Zero compilation** - Pure Python, just copy and run
✅ **No QML required** - Configure via D-Bus command line
✅ **100% compatible** - Same data as original C++ driver
✅ **WAN-ready** - Works over internet with optimized timeouts

---

## Quick Start

```bash
# 1. Copy files to Venus OS
scp dbus_tristar.py install.sh root@<venus-ip>:/tmp/

# 2. SSH to Venus OS
ssh root@<venus-ip>

# 3. Install (creates service and starts driver)
cd /tmp
chmod +x install.sh
./install.sh
```

**That's it!** The driver is now running as a service.

---

## Configuration

Settings are configured via D-Bus command line (no GUI menu in Venus OS v3.67):

```bash
# Set IP address (REQUIRED)
dbus -y com.victronenergy.settings /Settings/TristarMPPT/IPAddress SetValue "192.168.1.100"

# Optional settings (with defaults shown)
dbus -y com.victronenergy.settings /Settings/TristarMPPT/PortNumber SetValue 502
dbus -y com.victronenergy.settings /Settings/TristarMPPT/Interval SetValue 5000
dbus -y com.victronenergy.settings /Settings/TristarMPPT/SlaveID SetValue 1

# Restart driver to apply changes
svc -t /service/dbus-tristar
```

---

## Verification

```bash
# Check service is running
svstat /service/dbus-tristar

# Check logs
tail -f /var/log/dbus-tristar/current

# Check D-Bus registration
dbus -y com.victronenergy.solarcharger.tristar_0 /ProductName GetValue

# Check current values
dbus -y com.victronenergy.solarcharger.tristar_0 /Dc/0/Voltage GetValue
dbus -y com.victronenergy.solarcharger.tristar_0 /Yield/Power GetValue
```

Your TriStar MPPT will appear as a **Solar Charger** in:
- Venus OS main screen
- VRM Portal dashboard
- Remote Console

---

## Features

- ✅ Full Modbus TCP communication (connect-read-close pattern)
- ✅ All TriStar registers: voltage, current, power, yield, temperature
- ✅ Daily history: kWh, max values, time in absorption/bulk/float
- ✅ Total yield tracking
- ✅ Automatic reconnection on network loss
- ✅ Settings change callback (auto-reconnect when IP/port changes)
- ✅ WAN-optimized: 1-second timeout with 5 retries
- ✅ Full VRM Portal integration

---

## Supported Hardware

- Morningstar TriStar MPPT 30
- Morningstar TriStar MPPT 45
- Morningstar TriStar MPPT 60

**Requirements:**
- TriStar with Modbus TCP enabled
- Network connectivity between Venus OS and TriStar
- Venus OS v3.4+ (tested on v3.67)

---

## Files

```
dbus-tsmppt/
├── dbus_tristar.py              # Main driver
├── install.sh                   # Installation script
├── README.md                    # This file (main documentation)
├── QUICKSTART.md                # Quick start guide
├── test_connection.py           # Connection testing tool
├── dbus_tristar_mock.py         # Mock driver for testing
├── docs/                        # Technical docs and PDFs
└── Reference Cplusplus code for dbus_tsmppt/   # Legacy C++/QML code
```

---

## Documentation

- **[QUICKSTART.md](QUICKSTART.md)** - 3-minute installation guide
- **[test_connection.py](test_connection.py)** - Test Modbus connection to your TriStar
- **[docs/TECHNICAL-DETAILS.md](docs/TECHNICAL-DETAILS.md)** - Complete technical details and C++ compatibility analysis

---

## Troubleshooting

**Can't connect to TriStar?**
```bash
# Test connection
python3 test_connection.py <tristar-ip> 502 1

# Check network
ping <tristar-ip>

# Review logs
tail -f /var/log/dbus-tristar/current
```

**No data showing?**
- Verify IP address is correct in settings
- Check TriStar has Modbus TCP enabled (usually port 502)
- Check slave ID matches your device (usually 1)
- Review logs for connection errors

**Settings menu doesn't appear in GUI?**
- **Expected behavior** in Venus OS v3.67
- Use D-Bus command line instead (see Configuration section)
- Settings are fully functional via D-Bus

---

## Technical Details

**Architecture:**
- Uses Venus OS `SettingsDevice` API (array format for v3.67)
- Connect-read-close Modbus pattern (matches original C++ driver)
- pymodbus v3.x compatible (`unit=` parameter)
- GLib main loop with periodic timer
- Full error handling with automatic retries

**D-Bus Service:**
- Service name: `com.victronenergy.solarcharger.tristar_0`
- All 27 D-Bus paths identical to original C++ driver
- Charge state mapping: TriStar states → Victron states
- Proper signed/unsigned conversion and scaling

**See [docs/TECHNICAL-DETAILS.md](docs/TECHNICAL-DETAILS.md) for complete technical details and C++ compatibility analysis.**

---

## Legacy Code

The original C++ driver and legacy Python versions are preserved in:

**[Reference Cplusplus code for dbus_tsmppt/](Reference%20Cplusplus%20code%20for%20dbus_tsmppt/)**

Contents:
- `software/` - Original Qt/C++ driver (Venus OS v2.30 and older)
- `qml/` - QML files for Venus OS v2.80-v3.3
- `dbus-tsmppt.py` - Legacy Python driver
- Old installation scripts and documentation

These are kept for reference only. **Use `dbus_tristar.py` for all new installations.**

---

## License

MIT License - See [LICENSE](LICENSE)

---

## Credits

- **Original C++ driver:** Ole André Sæther (2018-2019)
- **Python rewrite:** 2024 - Modern Venus OS v3.4+ compatible
- **Architecture:** Based on Victron Energy Venus OS and velib_python

---

**Enjoy your TriStar MPPT on Venus OS! ☀️🔋**

Questions? Check the logs: `tail -f /var/log/dbus-tristar/current`
