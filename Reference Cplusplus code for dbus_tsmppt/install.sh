#!/bin/bash
set -e

# Installation script for dbus-tsmppt on Venus OS
# Run this script on your Venus OS device (GX device)

INSTALL_DIR=/data/dbus-tsmppt
SERVICE_NAME=dbus-tsmppt

echo "Installing dbus-tsmppt..."

# Create installation directory
mkdir -p $INSTALL_DIR
mkdir -p $INSTALL_DIR/service
mkdir -p $INSTALL_DIR/service/log

# Copy files
echo "Copying files..."
cp dbus-tsmppt.py $INSTALL_DIR/
chmod +x $INSTALL_DIR/dbus-tsmppt.py

cp service/run $INSTALL_DIR/service/
chmod +x $INSTALL_DIR/service/run

cp service/log/run $INSTALL_DIR/service/log/
chmod +x $INSTALL_DIR/service/log/run

# Copy test script
if [ -f test_connection.py ]; then
    cp test_connection.py $INSTALL_DIR/
    chmod +x $INSTALL_DIR/test_connection.py
fi

# Install Python dependencies
echo "Installing Python dependencies..."
opkg update
opkg install python3-pymodbus

# Add settings to localsettings if not present
echo "Configuring settings..."
dbus -y com.victronenergy.settings /Settings AddSetting TristarMPPT IPAddress "" s "" ""
dbus -y com.victronenergy.settings /Settings AddSetting TristarMPPT PortNumber 502 i 0 65535
dbus -y com.victronenergy.settings /Settings AddSetting TristarMPPT Interval 5000 i 1000 60000

# Create service link
echo "Creating service..."
ln -sf $INSTALL_DIR/service /service/$SERVICE_NAME

# Start service
echo "Starting service..."
svc -u /service/$SERVICE_NAME

# Wait for service to start
sleep 2
svstat /service/$SERVICE_NAME

# Copy QML files for GUI (optional)
if [ -d qml ]; then
    echo "Copying GUI files..."
    mkdir -p $INSTALL_DIR/qml
    cp -r qml/* $INSTALL_DIR/qml/
    chmod +x $INSTALL_DIR/qml/*.sh
fi

echo ""
echo "✓ Installation complete!"
echo ""
echo "Next steps:"
echo ""
echo "OPTION 1 - Configure via GUI (recommended for devices with screen):"
echo "  Run: cd $INSTALL_DIR/qml && ./install-gui.sh"
echo "  Then go to: Settings → TriStar MPPT Solar Charger"
echo ""
echo "OPTION 2 - Configure via command line:"
echo "  1. Set IP address:"
echo "     dbus -y com.victronenergy.settings /Settings/TristarMPPT/IPAddress SetValue \"192.168.1.100\""
echo ""
echo "  2. Optionally change port (default 502):"
echo "     dbus -y com.victronenergy.settings /Settings/TristarMPPT/PortNumber SetValue 502"
echo ""
echo "  3. Optionally change update interval in ms (default 5000):"
echo "     dbus -y com.victronenergy.settings /Settings/TristarMPPT/Interval SetValue 5000"
echo ""
echo "  4. Restart service:"
echo "     svc -t /service/$SERVICE_NAME"
echo ""
echo "Check logs:"
echo "  tail -f /var/log/dbus-tsmppt/current"
echo ""
echo "Test connection before configuring (optional):"
echo "  cd $INSTALL_DIR && python3 test_connection.py 192.168.1.100"
echo ""
