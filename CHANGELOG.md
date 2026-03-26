# Changelog

All notable changes to the TriStar MPPT driver for Venus OS.

## [2.26] - 2026-03-26

### Added - Charge Profile Management & EEPROM Programming

**Charge Profile System:**
- ✅ **Three configurable profiles** - Summer, Winter, and Custom via D-Bus Settings
- ✅ **Safe EEPROM programming** - Following Morningstar recommended procedure:
  - DISCONNECT before writes
  - Atomic parameter writes with verification
  - Automatic backup creation
  - Controller reset after changes
  - Thread-safe operation (main loop paused)
- ✅ **Automatic voltage scaling** - Auto-detect 12V/24V/48V systems from V_PU
- ✅ **Precision improvements** - Use round() instead of int() for register conversion
  - Achieves exact values matching MS View (e.g., 26.2V → 26.2V, not 26.19V)
- ✅ **Intelligent polling** - Replace fixed sleeps with smart polling (10-15s typical operation)

**New D-Bus Paths:**
- `/Control/ApplyChargeProfile` - Write "summer"/"winter"/"custom" to trigger profile apply
- `/Custom/ChargeProfile/ApplyStatus` - Operation status (idle/validating/writing/resetting/success/failed)
- `/Custom/ChargeProfile/ProgressPercent` - Apply operation progress (0-100%)
- `/Custom/ChargeProfile/LastError` - Last error message if failed
- `/Custom/ChargeProfile/LastApplied` - "profile_name at YYYY-MM-DD HH:MM:SS"
- `/Custom/EEPROM/FloatVoltage` - Active float voltage (read-only)
- `/Custom/EEPROM/AbsorptionTime` - Active absorption time (read-only)
- `/Custom/EEPROM/FloatCancelVoltage` - Active float cancel voltage (read-only)

**New Settings Paths:**
- `/Settings/TristarMPPT/ChargeProfiles/Summer/*` - Summer profile (28.4V abs, 27.2V float, 7200s)
- `/Settings/TristarMPPT/ChargeProfiles/Winter/*` - Winter profile (28.8V abs, 27.6V float, 9000s)
- `/Settings/TristarMPPT/ChargeProfiles/Custom/*` - User-configurable profile (28.6V abs, 27.4V float, 8400s)
  - Each profile: AbsorptionVoltage, FloatVoltage, AbsorptionTime, FloatCancelVoltage

**Safety Features:**
- Read-before-write comparison (only write changed parameters)
- Parameter validation (float < absorption, safe voltage ranges)
- Timestamped backups in `/data/dbus-tristar/eeprom_backups/`
- Verification after every write (±0.1V tolerance)
- Dedicated Modbus client per operation (thread isolation)
- Control path reset after operation (enables immediate retry)
- Status tracking prevents concurrent operations

**EEPROM Write Procedure:**
1. Validate parameters and read current EEPROM
2. Create timestamped backup
3. Set DISCONNECT coil (stop charging)
4. Write parameters in safe order (lowest voltage first)
5. Verify all writes with tolerance checking
6. Reset controller (Morningstar recommended)
7. Smart reconnect (polls for controller reboot)
8. Verify normal operation resumed

**Use Case:**
Switch between seasonal battery optimization profiles (summer: lower voltage for warm weather, winter: higher voltage for cold weather, custom: user-defined for specific battery type/location). Integrate with Home Assistant for automated seasonal switching via MQTT.

### Changed

**Reset Handling:**
- Controller reset connection close now treated as expected behavior (not error)
- Recovery logic improved to handle expected connection errors during reset

**Retry Logic:**
- Profile apply now allows retry after success/failed (not just idle)
- Control path automatically resets to empty string after operation

**Documentation:**
- Added comprehensive charge profile management section
- Updated README with charge profile quick examples
- Added voltage scaling explanation (12V-equivalent EEPROM storage)

### Fixed

- **Voltage precision:** Register conversion now uses round() instead of int()
  - Fixes 0.01-0.05V rounding errors (matches MS View precision)
- **SettingsDevice access:** Fixed .get() usage (changed to [] indexing with try/except)
- **Modbus client initialization:** Fixed missing self.client in async operations
- **Callback triggering:** Control path reset enables same-profile reapplication

### Technical Details

**Voltage Scaling Algorithm:**
```
System detection: V_PU < 100 = 12V, V_PU < 200 = 24V, V_PU ≥ 200 = 48V
Write: voltage_12v = actual_voltage / scale; raw = round(voltage_12v / (v_pu * 2^-15))
Read: voltage_12v = raw * v_pu * 2^-15; actual_voltage = voltage_12v * scale
```

**Operation Timing:**
- No changes: < 1s (validation only)
- With writes: 10-15s (disconnect 1s, write 2s, verify 1s, reset+reconnect 5-8s)

**Thread Safety:**
- Main update loop paused via flag check
- Dedicated client created/destroyed per operation
- Finally block ensures loop always resumes

---

## [2.2] - 2024-01-24

### Added - WAN Optimizations & Production Hardening

**Reliability Features:**
- ✅ **Connection watchdog** - Detects and marks disconnected after 3 minutes without successful reads
- ✅ **Exponential backoff** - Automatically reduces poll frequency during outages (1x → 2x → 4x)
- ✅ **Graceful shutdown** - Proper SIGTERM/SIGINT signal handlers for clean service stops
- ✅ **Data validation** - Sanity checks reject unrealistic voltage/current/power values
- ✅ **Critical coil verification** - Read-after-write for EQUALIZE and DISCONNECT operations

**Diagnostics & Monitoring:**
- ✅ **Statistics paths** - 5 new D-Bus paths for remote health monitoring:
  - `/Custom/Stats/SuccessfulReads` - Total successful Modbus operations
  - `/Custom/Stats/FailedReads` - Total failed Modbus operations
  - `/Custom/Stats/ConsecutiveFailures` - Current consecutive failure count
  - `/Custom/Stats/LastSuccessTime` - Unix timestamp of last success
  - `/Custom/Stats/BackoffFactor` - Current poll interval multiplier (1/2/4)

**Configuration:**
- ✅ **Configurable device instance** - Support multiple TriStar MPPTs on same Venus OS
  - Setting: `/Settings/TristarMPPT/DeviceInstance` (0-255)
  - Service name becomes: `com.victronenergy.solarcharger.tristar_{instance}`

**Performance:**
- ✅ **Smart retry logging** - Transient failures logged at DEBUG, only persistent at ERROR
- ✅ **Dynamic timer restart** - Poll interval changes take effect immediately without service restart
- ✅ **Optimized logging** - Reduced log noise by 95% during network instability

### Changed

**Nightly reset improvements:**
- Now resets both comm server AND daily counters (bulk time) at 03:00
- Prevents retry spam if reset fails (marks as attempted before trying)

**Timer management:**
- Poll interval changes now restart timer immediately (no service restart needed)
- Backoff automatically adjusts timer when network degraded

**Logging levels:**
- Connection/Modbus retry attempts: WARNING → DEBUG (first 4 attempts)
- Only final (5th) retry failure logged at ERROR level
- Reduces log spam from ~48 lines to 1 line per failed read during network issues

### Fixed

- **Timer restart bug** - Changing poll interval via settings now properly restarts timer
- **Bulk time reset** - Daily bulk time counter now resets at nightly reset (not just at NIGHT state)
- **Coil read errors** - Now logged with warning instead of silent failure

### Technical Details

**Data validation ranges:**
- Battery voltage: 18.0 - 35.0V (LiFePO4 7S nominal 21-29.4V with margin)
- PV voltage: 0 - 160V (TriStar max 150V + margin)
- Charge current: 0 - 70A (TriStar max 60A + margin)
- Output power: 0 - 2500W (60A × 35V theoretical max + margin)

**Backoff behavior:**
- Triggers after 10 consecutive failures (~50 seconds at 5s interval)
- Progression: 5s → 10s → 20s (maximum)
- Immediately returns to 5s on recovery
- Over 60-minute outage: reduces attempts from 720 to ~100 (85% reduction)

**Coil verification:**
- Applied to COIL_EQUALIZE (0) and COIL_DISCONNECT (2) only
- 100ms delay before readback to allow TriStar processing time
- Momentary coils (RESET_CTRL, RESET_COMM) not verified (fire-and-forget)

---

## [2.1] - 2024-01-20

### Added

**Control features:**
- Modbus coil control via D-Bus (4 coils exposed)
- Automatic nightly reset at 03:00 (comm server)
- Target regulation voltage sensor (`/Settings/ChargeTargetVoltage`)

**D-Bus paths:**
- `/Control/EqualizeTriggered` - Read/write equalize coil
- `/Control/ChargerDisconnect` - Read/write disconnect coil
- `/Control/ResetController` - Momentary reset button
- `/Control/ResetCommServer` - Momentary comm reset button

### Changed

- Modbus timeout reduced from 20s to 1s for WAN optimization
- Connect-read-close pattern enforced (matches TriStar hardware behavior)

---

## [2.0] - 2024-01-15

### Added

- Initial Python rewrite of C++ driver
- Venus OS v3.4+ compatibility
- SettingsDevice integration (no QML required)
- All 27 standard D-Bus paths from original driver
- Full Modbus register support (56 registers)
- Automatic reconnection on network loss
- pymodbus v2.x/v3.x compatibility

### Removed

- Qt/C++ compilation requirement
- QML file dependencies
- Manual XML editing for settings

---

## Version Naming

- **2.x** - Python driver (Venus OS v3.4+)
- **1.x** - Legacy C++ driver (Venus OS v2.x)

---

## Upgrade Path

### From v2.1 to v2.2

No breaking changes. Simply replace `dbus_tristar.py` and restart service:

```bash
svc -t /service/dbus-tristar
```

Settings, statistics, and all D-Bus paths remain compatible.

### From v2.0 to v2.1+

No breaking changes. Coil control paths are additive (existing paths unchanged).

### From C++ (v1.x) to Python (v2.x)

**Compatible:** All D-Bus paths produce identical data.

**Migration:**
1. Stop old C++ service
2. Install new Python driver
3. Configure IP via D-Bus settings
4. Verify in Venus OS GUI

**Note:** Service name unchanged (`com.victronenergy.solarcharger.tristar_0`), so VRM Portal history preserved.

---

**For installation and usage, see [README.md](README.md)**

**For technical details, see [docs/TECHNICAL-DETAILS.md](docs/TECHNICAL-DETAILS.md)**
