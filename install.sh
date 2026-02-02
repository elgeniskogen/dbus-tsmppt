#!/bin/bash
set -e

# Installation script for TriStar MPPT driver
# For Venus OS v3.4+ (including v3.67)
# NO QML REQUIRED - NO compilation needed!

# Installation directory (persistent across firmware updates)
INSTALL_DIR=/data/dbus-tristar
SCRIPT_NAME=dbus_tristar.py

echo "================================================================"
echo "TriStar MPPT Driver Installation (Venus OS v3.4+)"
echo "================================================================"
echo ""
echo "Modern Python driver - zero compilation, easy configuration."
echo "NO QML files needed - configure via D-Bus command line."
echo ""

# Create installation directory
echo "Creating installation directory: $INSTALL_DIR"
mkdir -p $INSTALL_DIR

# Copy driver
echo "Installing driver..."
cp $SCRIPT_NAME $INSTALL_DIR/
chmod +x $INSTALL_DIR/$SCRIPT_NAME

# Create service structure (if using daemontools/runit)
if [ -d /service ]; then
    echo "Setting up service..."

    # Create service directory
    mkdir -p $INSTALL_DIR/service
    mkdir -p $INSTALL_DIR/service/log

    # Create run script
    cat > $INSTALL_DIR/service/run << 'EOF'
#!/bin/sh
exec 2>&1
exec python3 /data/dbus-tristar/dbus_tristar.py
EOF
    chmod +x $INSTALL_DIR/service/run

    # Create log run script
    cat > $INSTALL_DIR/service/log/run << 'EOF'
#!/bin/sh
exec multilog t s25000 n4 /var/log/dbus-tristar
EOF
    chmod +x $INSTALL_DIR/service/log/run

    # Remove old symlink if it exists
    if [ -L /service/dbus-tristar ]; then
        rm /service/dbus-tristar
    fi

    # Create symlink to /service
    ln -sf $INSTALL_DIR/service /service/dbus-tristar

    echo "✓ Service created"

    # Start service
    echo "Starting service..."
    svc -u /service/dbus-tristar
    sleep 2
    svstat /service/dbus-tristar
else
    echo "Note: /service directory not found - manual start required"
fi

# Install Python dependencies if not present
if ! python3 -c "import pymodbus" 2>/dev/null; then
    echo "Installing pymodbus..."
    opkg update
    opkg install python3-pymodbus
else
    echo "✓ pymodbus already installed"
fi

echo ""
echo "================================================================"
echo "✓ Installation complete!"
echo "================================================================"
echo ""
echo "Installation location: $INSTALL_DIR"
echo "Service directory: /service/dbus-tristar"
echo "Log directory: /var/log/dbus-tristar"
echo ""
echo "📋 NEXT STEP: Configure via D-Bus command line"
echo ""
echo "Set TriStar IP address (REQUIRED):"
echo "  dbus -y com.victronenergy.settings /Settings/TristarMPPT/IPAddress SetValue \"YOUR_IP_HERE\""
echo ""
echo "Optional settings (with defaults):"
echo "  dbus -y com.victronenergy.settings /Settings/TristarMPPT/PortNumber SetValue 502"
echo "  dbus -y com.victronenergy.settings /Settings/TristarMPPT/Interval SetValue 5000"
echo "  dbus -y com.victronenergy.settings /Settings/TristarMPPT/SlaveID SetValue 1"
echo "  dbus -y com.victronenergy.settings /Settings/TristarMPPT/DeviceInstance SetValue 0"
echo ""
echo "After configuring, restart the driver:"
echo "  svc -t /service/dbus-tristar"
echo ""
echo "📊 Verification:"
echo ""
echo "Check service status:"
echo "  svstat /service/dbus-tristar"
echo ""
echo "Check logs:"
echo "  tail -f /var/log/dbus-tristar/current"
echo ""
echo "Check D-Bus registration:"
echo "  dbus -y com.victronenergy.solarcharger.tristar_0 /ProductName GetValue"
echo ""
echo "Check current values:"
echo "  dbus -y com.victronenergy.solarcharger.tristar_0 /Dc/0/Voltage GetValue"
echo "  dbus -y com.victronenergy.solarcharger.tristar_0 /Yield/Power GetValue"
echo ""
echo "Once configured, your TriStar MPPT will appear as a Solar Charger"
echo "in the Venus OS main screen and VRM Portal!"
echo ""
