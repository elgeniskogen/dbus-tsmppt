#!/bin/bash

# GUI uninstallation script for Venus OS v3.x

GUI_DIR="/opt/victronenergy/gui/qml"
SETTINGS_FILE="$GUI_DIR/PageSettings.qml"

echo "Uninstalling TriStar MPPT GUI integration..."

# Remove QML file
if [ -f "$GUI_DIR/PageSettingsTristar.qml" ]; then
    echo "Removing QML file..."
    rm "$GUI_DIR/PageSettingsTristar.qml"
fi

# Restore original PageSettings.qml from backup
if [ -f "$SETTINGS_FILE.backup" ]; then
    echo "Restoring original PageSettings.qml from backup..."
    cp "$SETTINGS_FILE.backup" "$SETTINGS_FILE"
    echo "Backup restored"
else
    echo "Warning: No backup found. PageSettings.qml not restored."
    echo "You may need to manually remove the TriStar MPPT menu entry."
fi

# Restart GUI
echo "Restarting GUI..."
svc -t /service/gui

echo ""
echo "✓ GUI uninstallation complete!"
echo ""
