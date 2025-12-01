# Reference: Legacy C++ and Python Code

This folder contains the original C++ driver and legacy Python implementations for historical reference and comparison purposes.

**⚠️ For new installations, use the modern Python driver in the parent directory: `dbus_tristar.py`**

---

## Contents

### Original C++ Driver (Venus OS v2.30 and older)

**Directory:** `software/`

The original Qt4/C++ implementation from 2018-2019:
- Required Venus OS SDK for compilation
- Manual QML file editing for GUI
- Complex build process
- Last updated: 2019
- **Status:** Deprecated - do not use

### Legacy Python Driver (Venus OS v2.80-v3.3)

**File:** `dbus-tsmppt.py`

First Python rewrite:
- No compilation needed (improvement over C++)
- Required manual QML files for GUI
- SettingsDevice with array format
- **Status:** Superseded by modern driver

### QML Files (Venus OS v2.80-v3.3)

**Directory:** `qml/`

Manual GUI integration files:
- `PageSettingsTristar.qml` - Settings page
- `install-gui.sh` - GUI installation script

**Status:** Not needed for Venus OS v3.4+ (SettingsDevice auto-generates GUI)

### Service Files

**Directory:** `service/`

Old daemontools/runit service configuration.

**Status:** Modern installer creates service structure automatically.

### Legacy Documentation

- `INSTALL.md` - Old installation instructions
- `QUICKSTART.md` - Legacy quick start
- `README-ORIGINAL.md` - Original README from C++ driver
- `README-PYTHON.md` - Legacy Python driver README

---

## Why Keep This?

1. **Historical reference** - Shows evolution from C++ to Python
2. **Comparison baseline** - Verify new driver matches C++ behavior
3. **Learning resource** - Study Modbus implementation, D-Bus integration
4. **Compatibility verification** - Ensure register mapping unchanged

---

## Comparison with Modern Driver

| Aspect | C++ Driver (2019) | Legacy Python | Modern Python (2024) |
|--------|-------------------|---------------|----------------------|
| **Language** | C++/Qt4 | Python | Python |
| **Compilation** | Required | None | None |
| **GUI Method** | Manual QML | Manual QML | D-Bus config (v3.67) |
| **Connection** | Connect-read-close | Connect-read-close | Connect-read-close |
| **Registers** | 56 (24-79) | 56 (24-79) | 56 (24-79) |
| **D-Bus Paths** | 27 paths | 27 paths | 27 paths ✅ Identical |
| **Scaling** | Manual | Manual | Manual ✅ Identical |
| **Timeout** | 20 seconds | 5 seconds | 1 second (WAN-optimized) |
| **Retries** | 5 | 5 | 5 |
| **Settings API** | XML editing | SettingsDevice array | SettingsDevice array |
| **pymodbus** | N/A | v2.x (`slave=`) | v3.x (`unit=`) |
| **Auto-reconnect** | Yes | Yes | Yes + settings callback |
| **Status** | Deprecated | Superseded | ✅ **Production-ready** |

---

## Key Technical Findings

From comparing C++ source with modern Python driver:

### Modbus Connection Pattern
**All three implementations use identical pattern:**
```
1. Create new Modbus client
2. Connect
3. Read registers
4. Close connection
5. Process data
```

This is **not** a persistent connection - each poll cycle creates a new connection.

### Register Reading
**Identical in all versions:**
- Read registers 24-79 (56 registers total)
- Single bulk read per update
- Scaling factors (v_pu, i_pu) read once during initialization
- All calculations use identical formulas

### D-Bus Integration
**All 27 D-Bus paths identical:**
```
/Pv/V, /Pv/I                    - PV array
/Dc/0/Voltage, /Dc/0/Current    - Battery
/Yield/Power, /Yield/User       - Power/yield
/State, /Mode, /Connected       - Status
/History/Daily/0/*              - Daily history (7 paths)
/ProductName, /Serial           - Device info
... and more
```

### Charge State Mapping
**All versions map 10 TriStar states → Victron states identically:**
```
START/NIGHT_CHECK/DISCONNECT/NIGHT → 0 (OFF)
FAULT                              → 2 (FAULT)
MPPT/BULK                          → 3 (BULK)
ABSORPTION                         → 4 (ABSORPTION)
FLOAT                              → 5 (FLOAT)
EQUALIZE                           → 7 (EQUALIZE)
SLAVE                              → 11 (OTHER)
```

**Result:** Modern Python driver produces **exactly the same data** as C++ driver.

---

## Files Preserved

```
Reference Cplusplus code for dbus_tsmppt/
├── README.md (this file)
├── software/                          # C++ driver source
│   ├── src/
│   │   ├── dbus_tsmppt_bridge.cpp    # D-Bus integration
│   │   ├── tsmppt.cpp                # Modbus communication
│   │   ├── tsmppt.h
│   │   └── main.cpp
│   ├── ext/                          # External dependencies
│   └── dbus-tsmppt.pro               # Qt project file
├── qml/                               # GUI files (v2.80-v3.3)
│   ├── PageSettingsTristar.qml
│   └── install-gui.sh
├── service/                           # Service configuration
│   ├── run
│   └── log/run
├── dbus-tsmppt.py                     # Legacy Python driver
├── dbus_tristar FUNKER.py             # Working backup copy
├── install.sh                         # Legacy installer
├── uninstall.sh                       # Legacy uninstaller
├── INSTALL.md                         # Old install guide
├── QUICKSTART.md                      # Legacy quick start
├── README-ORIGINAL.md                 # Original C++ README
└── README-PYTHON.md                   # Legacy Python README
```

---

## Study Guide

If you want to understand how the driver works:

1. **Start here:** `../dbus_tristar.py` (modern, well-commented)
2. **Compare with:** `software/src/tsmppt.cpp` (C++ Modbus implementation)
3. **D-Bus paths:** `software/src/dbus_tsmppt_bridge.cpp` (shows all paths)
4. **Legacy Python:** `dbus-tsmppt.py` (intermediate version)

---

## License

All code: MIT License

Original C++ driver: Ole André Sæther (2018-2019)

---

**Go back to parent directory for the production-ready driver!**

[← Back to main README](../README.md)
