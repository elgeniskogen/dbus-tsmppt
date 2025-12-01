# Documentation

Technical documentation and PDFs for the TriStar MPPT driver project.

---

## Venus OS Documentation (Norwegian)

### Data rapportert til Venus OS.pdf
Victron Energy documentation about D-Bus data paths and structure:
- Solar charger D-Bus paths (`/Pv/V`, `/Dc/0/Voltage`, etc.)
- Data types and units
- VRM Portal integration
- Official Victron standards

**Used for:** Ensuring our driver follows Victron's official D-Bus path structure.

### Definere menyene i Venus OS.pdf
Documentation about Venus OS GUI menu system:
- SettingsDevice API documentation
- QML integration (for older Venus versions)
- GUI menu structure
- Settings management

**Note:** This PDF suggested dictionary format for SettingsDevice, but Venus OS v3.67 actually uses array format. See `VIKTIGHETNOTE.md` for details.

---

## Project Notes

### TECHNICAL-DETAILS.md
Complete technical documentation for the modern Python driver:
- Full installation and configuration guide
- SettingsDevice API implementation (array format for v3.67)
- Complete C++ compatibility analysis
- All 27 D-Bus paths documented
- Modbus register mapping and scaling formulas
- Charge state mapping table
- Troubleshooting guide

**This is the most detailed technical reference for the driver.**

### VIKTIGHETNOTE.md
**"Viktig note" = "Important note" (Norwegian)**

Documents the critical discovery that the PDF documentation was incorrect about Venus OS v3.4+ API:
- PDFs claimed dictionary format: `{'default': value, 'type': 's'}`
- v3.67 actually requires array format: `[path, default, min, max]`
- Testing on real Venus OS v3.67 proved array format is correct

This note explains the API confusion we encountered during development.

### SUMMARY.md
Detailed technical summary of the entire development process:
- Evolution from C++ to Python driver
- API discovery and troubleshooting
- All errors encountered and fixes applied
- Technical decisions and their rationale
- Complete conversation history

**Use this to understand:** How we arrived at the final working driver implementation.

---

## Purpose

These documents are preserved for:
1. **Reference** - Future troubleshooting and updates
2. **Learning** - Understanding Venus OS D-Bus architecture
3. **History** - Documenting the development process
4. **Verification** - Ensuring compliance with Victron standards

---

[← Back to main README](../README.md)
