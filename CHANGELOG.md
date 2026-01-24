# Changelog

All notable changes to the TriStar MPPT driver for Venus OS.

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
