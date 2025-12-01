#!/bin/bash
set -e

# Installation script for TriStar MPPT driver
# For Venus OS v3.4+ (including v3.67)
# NO QML REQUIRED - NO compilation needed!

PLUGIN_DIR=/data/venus-data/dbus-plugins/tristar
SCRIPT_NAME=dbus_tristar.py

echo "================================================================"
echo "TriStar MPPT Driver Installation (Venus OS v3.4+)"
echo "================================================================"
echo ""
echo "Modern Python driver - zero compilation, easy configuration."
echo "NO QML files needed - configure via D-Bus command line."
echo ""

# Create plugin directory
echo "Creating plugin directory..."
mkdir -p $PLUGIN_DIR

# Copy driver
echo "Installing driver..."
cp $SCRIPT_NAME $PLUGIN_DIR/
chmod +x $PLUGIN_DIR/$SCRIPT_NAME

# Create symlink for auto-start (if using daemontools/runit)
if [ -d /service ]; then
    # Create service directory in plugin folder
    mkdir -p $PLUGIN_DIR/service
    mkdir -p $PLUGIN_DIR/service/log

    # Create run script
    cat > $PLUGIN_DIR/service/run << 'EOF'
#!/bin/sh
exec 2>&1
exec python3 /data/venus-data/dbus-plugins/tristar/dbus_tristar.py
EOF
    chmod +x $PLUGIN_DIR/service/run

    # Create log run script
    cat > $PLUGIN_DIR/service/log/run << 'EOF'
#!/bin/sh
exec multilog t s25000 n4 /var/log/dbus-tristar
EOF
    chmod +x $PLUGIN_DIR/service/log/run

    # Link to /service
    ln -sf $PLUGIN_DIR/service /service/dbus-tristar

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
echo "The driver is now running as a service."
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
echo ""
echo "After configuring, restart the driver:"
echo "  svc -t /service/dbus-tristar"
echo ""
echo "📊 Verification:"
echo ""
echo "Check logs:"
echo "  tail -f /var/log/dbus-tristar/current"
echo ""
echo "Check D-Bus registration:"
echo "  dbus -y com.victronenergy.solarcharger.tristar_0 /ProductName GetValue"
echo ""
echo "Check current IP setting:"
echo "  dbus -y com.victronenergy.settings /Settings/TristarMPPT/IPAddress GetValue"
echo ""
echo "Once configured, your TriStar MPPT will appear as a Solar Charger"
echo "in the Venus OS main screen and VRM Portal!"
echo ""
