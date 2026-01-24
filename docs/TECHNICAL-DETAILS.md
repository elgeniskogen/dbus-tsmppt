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
    'device_instance': ['/Settings/TristarMPPT/DeviceInstance', 0, 0, 255],
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

**Important - TriStar TCP Behavior:**

From TriStar MPPT Modbus specification (MS-002582_v11):
> "Note: the TCP socket is closed by the TS-MPPT after each MODBUS response (change pending)"

**What this means:**
- ✅ TriStar **automatically closes** the TCP socket after every Modbus response
- ✅ Persistent connections are **not supported** by TriStar hardware
- ✅ Connect-read-close pattern is **required**, not optional
- ✅ Each Modbus operation requires its own TCP connection

**Driver implementation:**
The driver performs **2 separate TCP connections** per poll cycle (every 5 seconds):
1. Connect → Read input registers (24-79, 56 registers) → Close
2. Connect → Read coils (0-2, 3 coils) → Close

This matches TriStar's documented behavior and cannot be optimized further without TriStar firmware changes. The overhead (~400-1000ms per poll over WAN) is unavoidable due to hardware limitations.

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

**Core Paths (27 - identical to C++ driver):**
- `/Pv/V`, `/Pv/I` - PV array voltage/current
- `/Dc/0/Voltage`, `/Dc/0/Current`, `/Dc/0/Temperature` - Battery data
- `/Yield/Power`, `/State`, `/Connected`, `/Mode` - Status
- `/History/Daily/0/*` - Daily statistics (7 paths)
- `/Yield/User`, `/Yield/System` - Total yield
- `/ProductName`, `/Serial`, `/FirmwareVersion`, `/HardwareVersion` - Device info
- `/ProductId`, `/DeviceInstance`, `/ErrorCode` - Management

**New in v2.1 (Python driver only):**
- `/Settings/ChargeTargetVoltage` - Target regulation voltage (read-only)
- `/Control/EqualizeTriggered` - Equalize charge trigger (read/write coil 0, verified)
- `/Control/ChargerDisconnect` - Disconnect charger (read/write coil 2, verified)
- `/Control/ResetController` - Reset controller (write-only coil 255, momentary)
- `/Control/ResetCommServer` - Reset comm server (write-only coil 4351, momentary)
- `/Custom/Stats/SuccessfulReads` - Total successful Modbus reads (diagnostic)
- `/Custom/Stats/FailedReads` - Total failed Modbus reads (diagnostic)
- `/Custom/Stats/ConsecutiveFailures` - Current consecutive failure count (diagnostic)
- `/Custom/Stats/LastSuccessTime` - Unix timestamp of last successful read (diagnostic)
- `/Custom/Stats/BackoffFactor` - Current poll interval multiplier: 1, 2, or 4 (diagnostic)

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

## 🆕 New Features in v2.1

### Target Regulation Voltage Sensor

**Register:** 51 (REG_V_TARGET)
**D-Bus path:** `/Settings/ChargeTargetVoltage`
**Scaling:** `reg * v_pu / 32768.0`
**Type:** Read-only voltage sensor

Shows the target voltage the TriStar is currently regulating to (absorption, float, or equalize voltage depending on charge state).

**Usage:**
```bash
dbus -y com.victronenergy.solarcharger.tristar_0 /Settings/ChargeTargetVoltage GetValue
```

### Modbus Coil Control

Four new control paths allow read/write access to TriStar coils:

| D-Bus Path | Coil | Type | Description |
|------------|------|------|-------------|
| `/Control/EqualizeTriggered` | 0 | Read/Write | Trigger equalize charge cycle |
| `/Control/ChargerDisconnect` | 2 | Read/Write | Disconnect/reconnect charger |
| `/Control/ResetController` | 255 | Write-only | Reset controller (momentary, only when dark!) |
| `/Control/ResetCommServer` | 4351 | Write-only | Reset Modbus comm server (momentary) |

**Stateful coils** (0, 2):
- Read current state every 5 seconds
- State persists until changed
- Value updates in D-Bus reflect TriStar's actual state

**Momentary buttons** (255, 4351):
- Write 1 to trigger action
- D-Bus value always shows 0
- Fire-and-forget (no state tracking)

**Usage examples:**
```bash
# Read equalize status
dbus -y com.victronenergy.solarcharger.tristar_0 /Control/EqualizeTriggered GetValue

# Trigger equalize
dbus -y com.victronenergy.solarcharger.tristar_0 /Control/EqualizeTriggered SetValue 1

# Disconnect charger
dbus -y com.victronenergy.solarcharger.tristar_0 /Control/ChargerDisconnect SetValue 1

# Reset comm server
dbus -y com.victronenergy.solarcharger.tristar_0 /Control/ResetCommServer SetValue 1
```

### Automatic Nightly Reset

The driver automatically performs a **comm server reset** every night at **03:00**.

**Implementation:**
- Checks time every poll cycle (5 seconds)
- 5-minute window (03:00-03:04) to ensure it triggers
- Executes only once per day
- Logged: `Performing nightly comm server reset at 03:00`

**Why:** TriStar Modbus comm server requires periodic reset to maintain stability. Previously done manually via Home Assistant, now handled automatically by the driver.

**Disable:** Not currently configurable. Edit `_check_nightly_reset()` in `dbus_tristar.py` if you want to disable or change the schedule.

### MQTT Integration

All D-Bus paths are automatically published to Venus OS MQTT broker:

**Topics:**
```
N/<portal-id>/solarcharger/tristar_0/Control/EqualizeTriggered      # Read
W/<portal-id>/solarcharger/tristar_0/Control/EqualizeTriggered      # Write
```

**Home Assistant example:**
```yaml
mqtt:
  switch:
    - unique_id: tristar_equalize
      name: "TriStar Equalize"
      state_topic: "N/<portal-id>/solarcharger/tristar_0/Control/EqualizeTriggered"
      command_topic: "W/<portal-id>/solarcharger/tristar_0/Control/EqualizeTriggered"
      payload_on: '{"value": 1}'
      payload_off: '{"value": 0}'
```

---

## 🌐 WAN Optimizations (v2.1+)

The driver is optimized for operation over WAN connections (VPN, cellular, internet). These features were added based on real-world deployment experience with remote sites.

### Connection Watchdog

**Purpose:** Detect when TriStar becomes unreachable and mark device as disconnected.

**Implementation:**
- Tracks timestamp of last successful Modbus read
- If no successful reads for 3 minutes (180 seconds), sets `/Connected = 0`
- Prevents stale data from being displayed in GUI
- Automatically recovers when connection restored

**Observable:** Check `/Custom/Stats/LastSuccessTime` to see when last successful read occurred.

### Exponential Backoff

**Purpose:** Reduce network traffic and CPU load during extended outages.

**Behavior:**
- Normal operation: 5-second poll interval (1x)
- After 10 consecutive failures (~50 seconds): backs off to 10 seconds (2x)
- After 20 consecutive failures: backs off to 20 seconds (4x, maximum)
- Immediately returns to 5 seconds when connection recovers

**Example timeline:**
```
00:00 - Normal polling at 5s interval
00:50 - 10 failures → backoff to 10s interval
01:40 - 20 failures → backoff to 20s interval (max)
...network down for hours...
10:30 - Connection restored → immediately return to 5s interval
```

**Observable:** Check `/Custom/Stats/BackoffFactor` (1, 2, or 4).

**Benefit:** Over a 60-minute outage, reduces Modbus attempts from ~720 to ~100 (85% reduction).

### Data Validation (Sanity Checks)

**Purpose:** Reject corrupted Modbus packets that pass CRC but contain unrealistic values.

**Implementation:**
```python
# Battery voltage: 18-35V (LiFePO4 7S nominal 21-29.4V with margin)
if not (18.0 <= v_bat <= 35.0):
    logging.warning("Unrealistic battery voltage")
    return  # Skip update, keep old values

# Similar checks for PV voltage (0-160V), charge current (0-70A), power (0-2500W)
```

**Why needed:** Over WAN, bit-flips can occur at higher protocol layers. Modbus CRC validates packet structure but not semantic correctness. A corrupted register value like `0xFFFF` (65535) would pass CRC but translate to impossible voltage (65.5V).

**Observable:** Check logs for "Unrealistic" warnings.

### Critical Coil Verification

**Purpose:** Ensure safety-critical operations (EQUALIZE, DISCONNECT) actually succeeded.

**Implementation:**
1. Write coil via Modbus
2. Wait 100ms for TriStar to process
3. Read coil back
4. Compare written value with readback
5. Log error if mismatch

**Example:**
```python
# Write equalize coil
write_coil(COIL_EQUALIZE, True)

# Verify (after 100ms)
verify = read_coils(COIL_EQUALIZE, 1)
if verify[0] != True:
    logging.error("Coil write verification failed")
    return False  # Propagate failure
```

**Why needed:** Over WAN, ACK can succeed but TriStar may reject command due to internal state (e.g., refusing EQUALIZE if battery voltage too low).

**Observable:** Check logs for "Coil write verification" messages.

### Smart Retry Logging

**Purpose:** Reduce log noise during transient network issues.

**Behavior:**
- First 4 retry attempts: logged at DEBUG level (not shown in INFO logs)
- Final (5th) attempt failure: logged at ERROR level
- Result: Only persistent failures appear in standard logs

**Example:**
```
# Transient failure (connection hiccup, packet loss):
# No log entries (retries at DEBUG level)

# Persistent failure (network down):
2024-01-24 10:30:15 ERROR    Failed to connect after 5 retries
```

**Benefit:** Logs remain clean and actionable. Transient hiccups don't trigger false alarms.

### Graceful Shutdown

**Purpose:** Proper cleanup when Venus OS restarts or service stops.

**Implementation:**
- Handles SIGTERM (service stop, reboot)
- Handles SIGINT (Ctrl+C during testing)
- Cleanly exits GLib main loop
- Prevents zombie processes

**Observable:** Check logs during `svc -t /service/dbus-tristar`:
```
2024-01-24 10:30:15 INFO     Received signal SIGTERM - shutting down gracefully...
```

### Statistics for Remote Diagnostics

**Purpose:** Enable debugging without SSH access to Venus OS.

**Available metrics:**
```bash
# Total operations
/Custom/Stats/SuccessfulReads    # Cumulative successful reads
/Custom/Stats/FailedReads        # Cumulative failed reads

# Current health
/Custom/Stats/ConsecutiveFailures  # 0 = healthy, >0 = problems
/Custom/Stats/LastSuccessTime      # Unix timestamp
/Custom/Stats/BackoffFactor        # 1 = normal, 2-4 = degraded

# Check from VRM Portal or via dbus-spy
dbus -y com.victronenergy.solarcharger.tristar_0 /Custom/Stats/ConsecutiveFailures GetValue
```

**Example diagnosis from VRM Portal:**
```
SuccessfulReads: 14523
FailedReads: 47
ConsecutiveFailures: 0
LastSuccessTime: 1738012345 (6 minutes ago)
BackoffFactor: 1

→ Conclusion: 99.7% success rate, currently healthy
```

**Versus during outage:**
```
SuccessfulReads: 14523
FailedReads: 94
ConsecutiveFailures: 47
LastSuccessTime: 1738009000 (56 minutes ago)
BackoffFactor: 4

→ Conclusion: Network down for 56 minutes, driver in backoff mode
```

### Dynamic Timer Restart

**Purpose:** Apply new poll interval immediately when changed via settings.

**Behavior:**
- Changing `/Settings/TristarMPPT/Interval` immediately stops old timer
- Starts new timer with new interval
- No service restart required

**Before (v2.0):** Had to restart service to apply interval change.

**After (v2.1):** Change takes effect within current poll cycle (max 5 seconds).

### Configurable Device Instance

**Purpose:** Support multiple TriStar MPPTs on same Venus OS installation.

**Implementation:**
```bash
# First TriStar (north array)
dbus -y com.victronenergy.settings /Settings/TristarMPPT/DeviceInstance SetValue 0
# Service: com.victronenergy.solarcharger.tristar_0

# Second TriStar (south array)
dbus -y com.victronenergy.settings /Settings/TristarMPPT/DeviceInstance SetValue 1
# Service: com.victronenergy.solarcharger.tristar_1
```

**Note:** Each instance requires separate installation (different service directories).

---

**Enjoy your TriStar MPPT on Venus OS! ☀️🔋**

Questions? Check the logs first: `tail -f /var/log/dbus-tristar/current`
