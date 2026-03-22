# TriStar MPPT Driver for Venus OS

**Modern Python driver for Morningstar TriStar MPPT solar charge controllers**

✅ **Production-ready** - Tested on Venus OS v3.67
✅ **Zero compilation** - Pure Python, just copy and run
✅ **No QML required** - Configure via D-Bus command line
✅ **100% compatible** - Same data as original C++ driver
✅ **WAN-ready** - Works over internet with optimized timeouts
✅ **Advanced features** - Voltage override, tail current detection, 30-day history

📚 **[Complete Documentation](DRIVER_DOCUMENTATION.md)** - All D-Bus paths, logic, and advanced features

---

## Recent Updates (v2.24)

✅ **Voltage Override System** - Battery top-charging with automatic tail current detection
✅ **Cumulative Time Tracking** - Tolerates brief voltage dips (Home Assistant pattern)
✅ **Nightly Reset** - Prevents stuck charging sessions (configurable hour)
✅ **30-Day History** - Daily max/min tracking with state persistence
✅ **EEPROM Counters** - Lifetime kWh from TriStar's internal registers

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

## Battery Top-Charging (Quick Example)

The driver supports advanced battery top-charging with automatic tail current detection:

```bash
# Enable voltage override to 28.7V for top-charging
dbus -y com.victronenergy.solarcharger.tristar_0 /Control/VoltageOverride SetValue 28.7

# Monitor progress
dbus -y com.victronenergy.solarcharger.tristar_0 /Custom/VoltageOverride/TimeAtTargetVoltage GetValue
dbus -y com.victronenergy.solarcharger.tristar_0 /Custom/VoltageOverride/TailCurrentTimer GetValue

# Check status
dbus -y com.victronenergy.solarcharger.tristar_0 /Custom/VoltageOverride/Active GetValue
dbus -y com.victronenergy.solarcharger.tristar_0 /Custom/VoltageOverride/StopReason GetValue

# Disable when done (or let automatic tail current detection stop it)
dbus -y com.victronenergy.solarcharger.tristar_0 /Control/VoltageOverride SetValue 0
```

**Automatic stopping conditions:**
- Battery full (tail current < 2.0A for 5 minutes)
- Time limit reached (max 2 hours/day)
- Nightly reset (03:00 local time)

**Configure thresholds:**
```bash
# Set tail current threshold to 1.5A
dbus -y com.victronenergy.settings /Settings/TristarMPPT/BatteryFullCurrent SetValue 1.5

# Set max voltage to 28.95V
dbus -y com.victronenergy.settings /Settings/TristarMPPT/MaxVoltageOverrideVoltage SetValue 28.95
```

📚 **Full documentation:** [DRIVER_DOCUMENTATION.md](DRIVER_DOCUMENTATION.md) - Complete guide with all settings, D-Bus paths, and logic

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
- ✅ **Voltage override** - Top-charge to configurable voltage (e.g., 28.7V)
- ✅ **Automatic battery full detection** - Tail current monitoring with configurable thresholds
- ✅ **Mode control** - Enable/disable charging via D-Bus
- ✅ Equalize trigger (read/write coil with verification)
- ✅ Charger disconnect (read/write coil with verification)
- ✅ Controller reset (momentary button)
- ✅ Comm server reset (momentary button)
- ✅ **Automatic nightly reset** at configurable hour (default: 03:00)

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
├── dbus_tristar.py              # Main driver (v2.24)
├── install.sh                   # Installation script
├── README.md                    # This file (overview)
├── DRIVER_DOCUMENTATION.md      # Complete technical reference (📚 READ THIS!)
├── QUICKSTART.md                # Quick start guide
├── test_connection.py           # Connection testing tool
├── dbus_tristar_mock.py         # Mock driver for testing
├── docs/                        # Technical docs and PDFs
└── Reference Cplusplus code for dbus_tsmppt/   # Legacy C++/QML code
```

---

## Documentation

- **[DRIVER_DOCUMENTATION.md](DRIVER_DOCUMENTATION.md)** - 📚 **COMPLETE REFERENCE** - All D-Bus paths, voltage override system, tail current detection, settings, troubleshooting
- **[QUICKSTART.md](QUICKSTART.md)** - 3-minute installation guide
- **[test_connection.py](test_connection.py)** - Test Modbus connection to your TriStar
- **[docs/TECHNICAL-DETAILS.md](docs/TECHNICAL-DETAILS.md)** - C++ compatibility analysis and technical details

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

**MQTT write not working?**
- **CRITICAL:** Venus OS MQTT requires JSON format: `{"value": 1}` not just `1`
- MQTT topics use device instance (e.g., `solarcharger/0`), not service name (e.g., `tristar_0`)
- Test D-Bus write first to verify driver is working:
  ```bash
  dbus -y com.victronenergy.solarcharger.tristar_0 /Control/EqualizeTriggered SetValue 1
  ```
- Example MQTT write command:
  ```bash
  mosquitto_pub -h <venus-ip> -t "W/<portal-id>/solarcharger/0/Control/EqualizeTriggered" -m '{"value": 1}'
  ```
- Check logs after MQTT write to see if driver received the command:
  ```bash
  tail -f /var/log/dbus-tristar/current | grep "Coil write"
  ```

---

## Technical Details

**Architecture:**
- Pure Python using Venus OS `SettingsDevice` API
- Connect-read-close Modbus pattern (matches TriStar hardware)
- pymodbus v2.x/v3.x compatible with auto-detection
- GLib main loop with exponential backoff on failures
- WAN-optimized: 1-second timeout, data validation, smart retry logging

**D-Bus Service:**
- Service name: `com.victronenergy.solarcharger.tristar_{instance}` (configurable)
- 50+ D-Bus paths: Standard Victron + Custom monitoring/control
- Full settings integration: `/Settings/TristarMPPT/*`
- State persistence: 30-day history in `/data/dbus-tristar/state.json`

**For complete technical details, D-Bus path reference, Modbus registers, and troubleshooting:**
📚 **See [DRIVER_DOCUMENTATION.md](DRIVER_DOCUMENTATION.md)**

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

**IMPORTANT:** Venus OS MQTT write requires JSON format. Use `{"value": 1}` not just `1`.

**Note:**
- Replace `<portal-id>` with your Venus OS VRM Portal ID (found in Settings → VRM Portal)
- Replace `tristar_0` with `0` if using default device instance (MQTT uses device instance, not service name)
- Example: `W/b827ebe38b8c/solarcharger/0/Control/EqualizeTriggered {"value": 1}`

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
- https://github.com/mr-manuel/venus-os_dbus-mqtt-solar-charger

---

**Enjoy your TriStar MPPT on Venus OS! ☀️🔋**

Questions? Check the logs: `tail -f /var/log/dbus-tristar/current`
