## TriStar MPPT Driver for Venus OS v3.4+

**Modern Python driver - NO QML required, NO compilation needed!**

### ✅ What's New Compared to C++ Driver

- ❌ **OLD**: C++/Qt, requires SDK, compilation, manual QML editing
- ✅ **NEW**: Pure Python, copy & run, no compilation needed
- ✅ **100% compatible**: Same Modbus registers, same D-Bus paths, same data

**This driver replaces the old C++ version** - easier to install, easier to modify!

### 📦 What You Get

- **Zero compilation** - just copy Python file and run
- All Modbus registers supported (voltage, current, power, yield, history)
- Live reconnection if network drops
- Full VRM Portal integration
- NO QML files needed (settings via D-Bus command line)
- **100% data compatibility** with original C++ driver

### 🚀 Installation (Super Simple!)

```bash
# 1. Copy files to Venus OS
scp dbus_tristar.py install-v3.sh root@<venus-ip>:/tmp/

# 2. SSH to Venus OS
ssh root@<venus-ip>

# 3. Install
cd /tmp
chmod +x install-v3.sh
./install-v3.sh
```

Done! The driver is now running.

### ⚙️ Configuration

**Note:** On Venus OS v3.67, settings do **not** appear in GUI automatically. Use D-Bus command line instead.

#### Via D-Bus Command Line

```bash
# Set IP address (required!)
dbus -y com.victronenergy.settings /Settings/TristarMPPT/IPAddress SetValue "78.158.239.143"

# Set port (default: 502)
dbus -y com.victronenergy.settings /Settings/TristarMPPT/PortNumber SetValue 502

# Set poll interval in milliseconds (default: 5000 = 5 seconds)
dbus -y com.victronenergy.settings /Settings/TristarMPPT/Interval SetValue 5000

# Set slave ID (default: 1)
dbus -y com.victronenergy.settings /Settings/TristarMPPT/SlaveID SetValue 1

# Restart driver to apply changes
svc -t /service/dbus-tristar
```

After configuration, verify it worked:
```bash
# Check current IP
dbus -y com.victronenergy.settings /Settings/TristarMPPT/IPAddress GetValue

# Check logs
tail -f /var/log/dbus-tristar/current
# Should show: "TriStar MPPT XX initialized" with your device info
```

### 🔍 Verification

```bash
# Check service is running
svstat /service/dbus-tristar
# Should show: up (run: XXX seconds)

# Check logs
tail -f /var/log/dbus-tristar/current
# Look for: "TriStar MPPT XX initialized"

# Check D-Bus
dbus -y com.victronenergy.solarcharger.tristar_0 /ProductName GetValue
# Should return: TriStar MPPT 60 (or 30/45)

# Check current values
dbus -y com.victronenergy.solarcharger.tristar_0 /Dc/0/Voltage GetValue
dbus -y com.victronenergy.solarcharger.tristar_0 /Yield/Power GetValue
```

### 📊 Where Data Appears

1. **Venus OS GUI**
   - Main screen → Solar Charger tile
   - Shows battery voltage, current, power

2. **VRM Portal**
   - Device list → Solar Chargers → TriStar MPPT
   - Dashboard widgets
   - Historical graphs

3. **Remote Console**
   - Same as Venus OS screen (web browser access)

### 🗂️ File Structure

```
/data/venus-data/dbus-plugins/tristar/
├── dbus_tristar.py          # Main driver (this file)
├── service/                 # Auto-start service (created by install)
│   ├── run
│   └── log/run
```

**Important:** Driver location changed!
- ❌ OLD: `/data/dbus-tsmppt/` (custom location)
- ✅ NEW: `/data/venus-data/dbus-plugins/tristar/` (official plugin location)

### 🆚 Venus OS Version Compatibility

| Venus OS Version | Use This Driver | Method |
|------------------|-----------------|---------|
| **v3.4 - v3.65+** (2023+) | ✅ **dbus_tristar.py** | Automatic GUI |
| v3.0 - v3.3 | ⚠️ Might work | Try dbus_tristar.py first |
| v2.80 - v2.99 | ❌ Use legacy | Need dbus-tsmppt.py + QML |
| v2.30 and older | ❌ Use legacy | Need Qt/C++ version |

### 🔧 Troubleshooting

**Settings menu doesn't appear?**
- **Expected behavior** in Venus v3.67 - GUI menu does not auto-generate
- Use D-Bus command line instead (see Configuration section above)
- Settings are fully functional via D-Bus, just no GUI menu

**Can't connect to TriStar?**
- Verify IP is correct in settings
- Test network: `ping <tristar-ip>`
- Check TriStar has Modbus TCP enabled
- Check Modbus port (usually 502)
- Review logs: `tail -f /var/log/dbus-tristar/current`

**No data showing?**
- Check connection status in logs
- Verify TriStar is responding to Modbus
- Check slave ID matches your device (usually 1)

### 📝 Settings Device Structure

**Note:** Venus OS v3.67 uses **array format** for SettingsDevice (not dictionary format):

```python
supportedSettings={
    'ip_address': ['/Settings/TristarMPPT/IPAddress', '192.168.1.100', 0, 0],
    'modbus_port': ['/Settings/TristarMPPT/PortNumber', 502, 1, 65535],
    'poll_interval': ['/Settings/TristarMPPT/Interval', 5000, 1000, 60000],
    'slave_id': ['/Settings/TristarMPPT/SlaveID', 1, 1, 247],
}
# Format: [D-Bus path, default, min, max]
```

Settings are stored in `/data/conf/settings.xml` and can be accessed via:
```bash
dbus -y com.victronenergy.settings /Settings/TristarMPPT/IPAddress GetValue
dbus -y com.victronenergy.settings /Settings/TristarMPPT/IPAddress SetValue "192.168.1.200"
```

**Note:** GUI menu does not auto-generate in Venus v3.67. Settings work via D-Bus command line only (no QML required).

### 🎯 Benefits Over Legacy QML Method

| Feature | Legacy (QML) | Modern (SettingsDevice) |
|---------|--------------|-------------------------|
| **Installation** | Complex (QML editing) | Simple (copy 1 file) |
| **GUI Code** | Manual QML files | Auto-generated |
| **Settings Storage** | Manual XML editing | Automatic database |
| **Validation** | Manual | Built-in (min/max) |
| **Updates** | Edit QML + restart GUI | Edit Python + restart service |
| **Compatibility** | Breaks on updates | Future-proof API |

### 🚫 Why No QML Files?

**The QML files in this repo (`qml/` directory) are for Venus OS v2.x - v3.3 ONLY.**

For Venus OS v3.4+:
- QML is **NOT used** for settings
- Settings appear automatically via `SettingsDevice`
- Don't run `qml/install-gui.sh` - it's for old Venus versions!

### 📚 Further Reading

- [Venus OS D-Bus documentation](https://github.com/victronenergy/venus/wiki/dbus)
- [SettingsDevice source](https://github.com/victronenergy/velib_python/blob/master/settingsdevice.py)
- [Morningstar TriStar MPPT Modbus spec](https://www.morningstarcorp.com/products/tristar-mppt/)

### 🎁 Source Code

See `dbus_tristar.py` for full source - well commented and easy to modify!

Key features:
- Auto-reconnect on network drop
- Settings change callback (reconnects when IP/port changes)
- Full Modbus register map
- Proper scaling and signed/unsigned conversion
- Error handling with retries

### ✅ Compatibility with Original C++ Driver

The Python driver is **100% functionally identical** to the original Qt/C++ driver:

#### Modbus Register Reading
| Aspect | C++ Driver | Python Driver | Status |
|--------|------------|---------------|--------|
| **Register range** | REG_FIRST_DYN (24) → REG_LAST_DYN (79) | REG_V_BAT (24) → REG_T_FLOAT (79) | ✅ Identical |
| **Register count** | 56 registers | 56 registers | ✅ Identical |
| **Connection pattern** | Connect → Read → Close | Connect → Read → Close | ✅ Identical |
| **Timeout** | 20 seconds | 1 second (WAN-optimized) | ⚠️ Improved |
| **Retries** | 5 attempts | 5 attempts | ✅ Identical |

#### Data Conversion & Scaling
All calculations match **exactly**:
- Battery Voltage: `reg * v_pu / 32768.0`
- Charge Current: `signed(reg) * i_pu / 32768.0`
- PV Voltage: `reg * v_pu / 32768.0`
- PV Current: `reg * i_pu / 32768.0`
- Output Power: `reg * i_pu * v_pu / 131072.0`
- Battery Temperature: `signed(reg)` (direct value)
- Daily Yield: `reg / 1000.0` (Wh → kWh)
- Max Power: `reg * i_pu * v_pu / 131072.0`
- Time values: `reg / 60` (seconds → minutes)
- Yield calculations: `daily_kwh + total_kwh` (same algorithm)

#### D-Bus Paths
**All 27 D-Bus paths are identical:**
- `/Pv/V`, `/Pv/I` - PV array voltage/current
- `/Dc/0/Voltage`, `/Dc/0/Current`, `/Dc/0/Temperature` - Battery data
- `/Yield/Power`, `/State`, `/Connected`, `/Mode` - Status
- `/History/Daily/0/*` - Daily statistics (7 paths)
- `/Yield/User`, `/Yield/System` - Total yield
- `/ProductName`, `/Serial`, `/FirmwareVersion`, `/HardwareVersion` - Device info
- `/ProductId`, `/DeviceInstance`, `/ErrorCode` - Management

#### Charge State Mapping
All 10 TriStar states map to Victron states **identically**:
- START/NIGHT_CHECK/DISCONNECT/NIGHT → 0 (OFF)
- FAULT → 2 (FAULT)
- MPPT/BULK → 3 (BULK)
- ABSORPTION → 4 (ABSORPTION)
- FLOAT → 5 (FLOAT)
- EQUALIZE → 7 (EQUALIZE)
- SLAVE → 11 (OTHER)

**Result:** Venus OS GUI, VRM Portal, and all integrations see **exactly the same data** from both drivers.

---

**Enjoy your TriStar MPPT on Venus OS! ☀️🔋**

Questions? Check the logs first: `tail -f /var/log/dbus-tristar/current`
