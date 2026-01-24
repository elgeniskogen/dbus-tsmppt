# TriStar MPPT Driver for Venus OS

**Modern Python driver for Morningstar TriStar MPPT solar charge controllers**

✅ **Production-ready** - Tested on Venus OS v3.67
✅ **Zero compilation** - Pure Python, just copy and run
✅ **No QML required** - Configure via D-Bus command line
✅ **100% compatible** - Same data as original C++ driver
✅ **WAN-ready** - Works over internet with optimized timeouts

TO DO:
* Make a path with the Tristar charger states, both number and text
* Check modbus parameters to be used for I and V. Now it is a mix of fast and slow. 
* Make filters similar to those in the templates in HS
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
dbus -y com.victronenergy.settings /Settings/TristarMPPT/DeviceInstance SetValue 0

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

### Monitoring
- ✅ Full Modbus TCP communication (connect-read-close pattern)
- ✅ All TriStar registers: voltage, current, power, yield, temperature
- ✅ Target regulation voltage (charge setpoint)
- ✅ Daily history: kWh, max values, time in absorption/bulk/float
- ✅ Total yield tracking
- ✅ Full VRM Portal integration

### Control
- ✅ Equalize trigger (read/write coil with verification)
- ✅ Charger disconnect (read/write coil with verification)
- ✅ Controller reset (momentary button)
- ✅ Comm server reset (momentary button)
- ✅ **Automatic nightly reset at 03:00** (comm server + daily counters)

### Diagnostics & Health Monitoring
- ✅ **Connection statistics** (/Custom/Stats/SuccessfulReads)
- ✅ **Failure tracking** (/Custom/Stats/FailedReads)
- ✅ **Consecutive failure counter** (/Custom/Stats/ConsecutiveFailures)
- ✅ **Last success timestamp** (/Custom/Stats/LastSuccessTime)
- ✅ **Backoff factor** (/Custom/Stats/BackoffFactor)
- ✅ **Remote debugging** via VRM Portal or dbus-spy

### Reliability
- ✅ Automatic reconnection on network loss
- ✅ Settings change callback (auto-reconnect when IP/port changes)
- ✅ WAN-optimized: 1-second timeout with 5 retries
- ✅ **Connection watchdog** (3-minute timeout detection)
- ✅ **Exponential backoff** on persistent failures (1x → 2x → 4x interval)
- ✅ **Graceful shutdown** handlers (SIGTERM/SIGINT)
- ✅ **Data validation** (sanity checks on voltage/current/power)
- ✅ **Critical coil verification** (read-after-write for EQUALIZE/DISCONNECT)
- ✅ **Statistics paths** for remote diagnostics (/Custom/Stats/*)
- ✅ MQTT integration via Venus OS broker

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

# Check connection statistics
dbus -y com.victronenergy.solarcharger.tristar_0 /Custom/Stats/ConsecutiveFailures GetValue
dbus -y com.victronenergy.solarcharger.tristar_0 /Custom/Stats/LastSuccessTime GetValue
```

**Connection drops frequently?**
- Check `/Custom/Stats/FailedReads` and `/Custom/Stats/SuccessfulReads`
- High failure rate indicates network instability
- Check if backoff is active: `/Custom/Stats/BackoffFactor` (should be 1 normally)
- Exponential backoff will activate after 10 consecutive failures

**Unrealistic values showing?**
- Driver has built-in sanity checks for voltage/current/power
- Check logs for warnings: "Unrealistic battery voltage" or similar
- Indicates possible Modbus packet corruption over WAN
- Corrupted values are automatically rejected and old values retained

**No data showing?**
- Verify IP address is correct in settings
- Check TriStar has Modbus TCP enabled (usually port 502)
- Check slave ID matches your device (usually 1)
- Review logs for connection errors
- Check `/Connected` path: `dbus -y com.victronenergy.solarcharger.tristar_0 /Connected GetValue`

**Settings menu doesn't appear in GUI?**
- **Expected behavior** in Venus OS v3.67
- Use D-Bus command line instead (see Configuration section)
- Settings are fully functional via D-Bus

---

## Technical Details

**Architecture:**
- Uses Venus OS `SettingsDevice` API (array format for v3.67)
- Connect-read-close Modbus pattern (matches TriStar hardware behavior)
- pymodbus v2.x/v3.x compatible with auto-detection
- GLib main loop with configurable timer and exponential backoff
- Full error handling with 5 retries per operation
- Connection watchdog (3-minute timeout)
- Graceful shutdown (SIGTERM/SIGINT handlers)

**WAN Optimizations:**
- 1-second Modbus timeout (down from 20s in C++ driver)
- Exponential backoff on persistent failures (1x → 2x → 4x interval)
- Data validation with sanity checks (voltage/current/power ranges)
- Critical coil verification (read-after-write for EQUALIZE/DISCONNECT)
- Smart retry logging (DEBUG for transient, ERROR for persistent)

**D-Bus Service:**
- Service name: `com.victronenergy.solarcharger.tristar_{instance}` (configurable)
- 27 standard D-Bus paths identical to original C++ driver
- 5 new statistics paths for diagnostics (/Custom/Stats/*)
- Charge state mapping: TriStar states → Victron states
- Proper signed/unsigned conversion and scaling
- All 4 control coils exposed (equalize, disconnect, reset controller, reset comm)

**See [docs/TECHNICAL-DETAILS.md](docs/TECHNICAL-DETAILS.md) for complete technical details and C++ compatibility analysis.**

---

## Home Assistant Integration

Venus OS has a built-in MQTT broker that automatically publishes all D-Bus paths. This makes integration with Home Assistant simple and native.

### Control via MQTT

**Read coil status:**
```
N/<portal-id>/solarcharger/tristar_0/Control/EqualizeTriggered
N/<portal-id>/solarcharger/tristar_0/Control/ChargerDisconnect
```

**Write to coils:**
```
W/<portal-id>/solarcharger/tristar_0/Control/EqualizeTriggered {"value": 1}
W/<portal-id>/solarcharger/tristar_0/Control/ResetController {"value": 1}
```

### Example HA Configuration

```yaml
mqtt:
  switch:
    - unique_id: tristar_equalize
      name: "TriStar Equalize Charge"
      state_topic: "N/<portal-id>/solarcharger/tristar_0/Control/EqualizeTriggered"
      command_topic: "W/<portal-id>/solarcharger/tristar_0/Control/EqualizeTriggered"
      payload_on: '{"value": 1}'
      payload_off: '{"value": 0}'

    - unique_id: tristar_disconnect
      name: "TriStar Charger Disconnect"
      state_topic: "N/<portal-id>/solarcharger/tristar_0/Control/ChargerDisconnect"
      command_topic: "W/<portal-id>/solarcharger/tristar_0/Control/ChargerDisconnect"
      payload_on: '{"value": 1}'
      payload_off: '{"value": 0}'

  button:
    - unique_id: tristar_reset_controller
      name: "TriStar Reset Controller"
      command_topic: "W/<portal-id>/solarcharger/tristar_0/Control/ResetController"
      payload_press: '{"value": 1}'
```

**Note:** Replace `<portal-id>` with your Venus OS VRM Portal ID (found in Settings → VRM Portal).

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
