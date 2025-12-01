# GUI Integration for Venus OS v3.x

This directory contains QML files for integrating TriStar MPPT settings into the Venus OS GUI.

## What This Does

Adds a **"TriStar MPPT Solar Charger"** settings page to the Venus OS Settings menu where you can:

- Configure IP address/hostname
- Set Modbus TCP port
- Adjust update interval
- View connection status
- See device information (model, serial, firmware)

## Requirements

- Venus OS v3.x with GUI (Cerbo GX, Ekrano GX, etc.)
- **Not needed for** headless installations (Venus GX without screen)

## Installation

### After installing the main driver:

```bash
cd /data/dbus-tsmppt/qml
./install-gui.sh
```

This will:
1. Copy `PageSettingsTristar.qml` to `/opt/victronenergy/gui/qml/`
2. Add menu entry to `PageSettings.qml`
3. Create backup of original `PageSettings.qml`
4. Restart GUI

## Usage

After installation, go to:

**Settings → TriStar MPPT Solar Charger**

You'll see:
- **IP Address / Hostname** - Enter your TriStar MPPT IP
- **Modbus TCP Port** - Usually 502
- **Update Interval** - How often to poll (1000-60000 ms)
- **Connection Status** - Shows if connected
- **Device Info** - Model, serial, firmware (when connected)

Changes are saved immediately to D-Bus settings.

## Uninstallation

```bash
cd /data/dbus-tsmppt/qml
./uninstall-gui.sh
```

This restores the original `PageSettings.qml` from backup.

## Manual Installation (Alternative)

If the automatic script doesn't work, you can manually add the menu entry:

1. Copy QML file:
   ```bash
   cp PageSettingsTristar.qml /opt/victronenergy/gui/qml/
   ```

2. Edit `/opt/victronenergy/gui/qml/PageSettings.qml` and add:
   ```qml
   ListButton {
       text: qsTr("TriStar MPPT Solar Charger")
       button.text: qsTr("Setup")
       onClicked: {
           pageManager.pushPage("/opt/victronenergy/gui/qml/PageSettingsTristar.qml")
       }
   }
   ```

3. Restart GUI:
   ```bash
   svc -t /service/gui
   ```

## Troubleshooting

### Menu entry doesn't appear

1. Check file exists:
   ```bash
   ls -l /opt/victronenergy/gui/qml/PageSettingsTristar.qml
   ```

2. Restart GUI:
   ```bash
   svc -t /service/gui
   ```

3. Reboot device:
   ```bash
   reboot
   ```

### Settings don't save

Check D-Bus settings exist:
```bash
dbus -y com.victronenergy.settings /Settings/TristarMPPT/IPAddress GetValue
```

If missing, run main install script again:
```bash
/data/dbus-tsmppt/install.sh
```

### QML errors in logs

Check GUI logs:
```bash
tail -f /var/log/gui/current
```

## Venus OS v2.x (Old GUI)

If you're on Venus OS v2.x with QtQuick 1.1, use the old QML files in `software/qml/` instead.

## File Structure

```
qml/
├── PageSettingsTristar.qml  - Settings page (QtQuick 2.0)
├── install-gui.sh           - Automatic installer
├── uninstall-gui.sh         - Automatic uninstaller
└── README.md                - This file
```

## Notes

- The GUI is **optional** - the driver works without it
- You can configure everything via D-Bus commands (see main README)
- The install script backs up `PageSettings.qml` before modifying it
- Safe to run install script multiple times (won't duplicate entries)

## Compatibility

Tested on:
- Venus OS v3.00+
- QtQuick 2.0+
- Victron.VenusOS 1.0 QML module

For older versions, see `software/qml/` directory.
