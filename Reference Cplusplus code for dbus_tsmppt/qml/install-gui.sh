#!/bin/bash
set -e

# GUI installation script for Venus OS v3.x
# This adds the TriStar MPPT settings page to the Settings menu

GUI_DIR="/opt/victronenergy/gui/qml"
SETTINGS_FILE="$GUI_DIR/PageSettings.qml"
QML_SOURCE="PageSettingsTristar.qml"

echo "Installing TriStar MPPT GUI integration..."

# Check if GUI directory exists
if [ ! -d "$GUI_DIR" ]; then
    echo "Error: GUI directory not found at $GUI_DIR"
    echo "This script is for Venus OS with GUI (e.g., Cerbo GX, Ekrano GX)"
    exit 1
fi

# Backup original PageSettings.qml if not already backed up
if [ ! -f "$SETTINGS_FILE.backup" ]; then
    echo "Creating backup of PageSettings.qml..."
    cp "$SETTINGS_FILE" "$SETTINGS_FILE.backup"
fi

# Copy our QML file
echo "Copying QML file..."
cp "$QML_SOURCE" "$GUI_DIR/"

# Check if already installed
if grep -q "PageSettingsTristar" "$SETTINGS_FILE"; then
    echo "TriStar MPPT menu entry already exists in PageSettings.qml"
else
    echo "Adding menu entry to PageSettings.qml..."

    # Find the line with PageSettingsModbus or similar and add our entry after
    # This is a bit fragile, but works for Venus OS v3.x structure

    # Create a temp file with our menu entry
    cat > /tmp/tristar_menu_entry.qml << 'EOF'

		ListButton {
			text: qsTr("TriStar MPPT Solar Charger")
			button.text: qsTr("Setup")
			onClicked: {
				pageManager.pushPage("/opt/victronenergy/gui/qml/PageSettingsTristar.qml")
			}
		}
EOF

    # Insert after the "Settings" model section
    # Look for a good insertion point (after Modbus or ESS settings)
    # This is a simple approach - insert before the last closing brace

    # Count lines
    TOTAL_LINES=$(wc -l < "$SETTINGS_FILE")
    INSERT_LINE=$((TOTAL_LINES - 10))  # Insert near end, before closing braces

    # Insert our menu entry
    {
        head -n $INSERT_LINE "$SETTINGS_FILE"
        cat /tmp/tristar_menu_entry.qml
        tail -n +$((INSERT_LINE + 1)) "$SETTINGS_FILE"
    } > /tmp/PageSettings.qml.new

    # Replace original
    mv /tmp/PageSettings.qml.new "$SETTINGS_FILE"
    rm /tmp/tristar_menu_entry.qml

    echo "Menu entry added successfully"
fi

# Restart GUI to apply changes
echo "Restarting GUI..."
svc -t /service/gui

echo ""
echo "✓ GUI installation complete!"
echo ""
echo "The TriStar MPPT settings page should now appear in:"
echo "Settings → TriStar MPPT Solar Charger"
echo ""
echo "If you don't see it, try:"
echo "  1. Restart the GUI: svc -t /service/gui"
echo "  2. Reboot the device: reboot"
echo ""
