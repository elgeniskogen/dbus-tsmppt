#!/bin/bash
set -e

# Installation script for TriStar MPPT driver
# For Venus OS v3.4+ (including v3.67)
# Uses CORRECT daemontools structure with persistent storage

SERVICE_NAME=dbus-tristar
SCRIPT_NAME=dbus_tristar.py

# Persistent directories (survive firmware updates)
INSTALL_DIR=/data/$SERVICE_NAME
SERVICE_DIR=/data/etc/sv/$SERVICE_NAME
LOG_DIR=/data/log/$SERVICE_NAME

echo "================================================================"
echo "TriStar MPPT Driver Installation (Venus OS v3.4+)"
echo "================================================================"
echo ""
echo "Modern Python driver - zero compilation, easy configuration."
echo "NO QML files needed - configure via D-Bus command line."
echo ""

# Create installation directory for scripts
echo "Creating installation directory: $INSTALL_DIR"
mkdir -p $INSTALL_DIR

# Copy driver
echo "Installing driver..."
cp $SCRIPT_NAME $INSTALL_DIR/
chmod +x $INSTALL_DIR/$SCRIPT_NAME

# Create service directory structure (daemontools persistent)
echo "Setting up persistent service structure..."
mkdir -p $SERVICE_DIR/log
mkdir -p $LOG_DIR

# Create run script (main service)
cat > $SERVICE_DIR/run << 'EOF'
#!/bin/sh
echo "*** starting dbus-tristar ***"
exec 2>&1
exec python3 -u /data/dbus-tristar/dbus_tristar.py
EOF
chmod +x $SERVICE_DIR/run

# Create log run script
cat > $SERVICE_DIR/log/run << 'EOF'
#!/bin/sh
exec svlogd -tt /data/log/dbus-tristar
EOF
chmod +x $SERVICE_DIR/log/run

echo "✓ Service structure created"

# Setup rc.local for automatic symlink restoration on boot
RC_LOCAL=/data/rc.local

if [ ! -f $RC_LOCAL ]; then
    echo "Creating /data/rc.local..."
    cat > $RC_LOCAL << 'EOF'
#!/bin/sh

# Re-create service symlinks at boot (persistent across reboots)
ln -sf /data/etc/sv/dbus-tristar /service/dbus-tristar

exit 0
EOF
    chmod +x $RC_LOCAL
    echo "✓ Created /data/rc.local"
else
    # Check if our service is already in rc.local
    if ! grep -q "dbus-tristar" $RC_LOCAL; then
        echo "Adding dbus-tristar to existing /data/rc.local..."
        # Insert before 'exit 0'
        sed -i '/^exit 0/i ln -sf /data/etc/sv/dbus-tristar /service/dbus-tristar' $RC_LOCAL
        echo "✓ Added to /data/rc.local"
    else
        echo "✓ Already in /data/rc.local"
    fi
fi

# Create symlink (starts service immediately)
echo "Creating service symlink..."
if [ -L /service/$SERVICE_NAME ]; then
    rm /service/$SERVICE_NAME
fi
ln -sf $SERVICE_DIR /service/$SERVICE_NAME

echo "✓ Service symlink created"

# Install Python dependencies if not present
if ! python3 -c "import pymodbus" 2>/dev/null; then
    echo "Installing pymodbus..."
    opkg update
    opkg install python3-pymodbus
else
    echo "✓ pymodbus already installed"
fi

# Wait for service to start
echo ""
echo "Waiting for service to start..."
sleep 5

# Check service status
echo ""
echo "Service status:"
svstat /service/$SERVICE_NAME

echo ""
echo "================================================================"
echo "✓ Installation complete!"
echo "================================================================"
echo ""
echo "STRUCTURE:"
echo "  Driver:      $INSTALL_DIR/$SCRIPT_NAME"
echo "  Service:     $SERVICE_DIR/ (persistent)"
echo "  Logs:        $LOG_DIR/current"
echo "  Autostart:   /data/rc.local"
echo "  Symlink:     /service/$SERVICE_NAME → $SERVICE_DIR"
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
echo "  svc -t /service/$SERVICE_NAME"
echo ""
echo "📊 Verification:"
echo ""
echo "Check service status:"
echo "  svstat /service/$SERVICE_NAME"
echo ""
echo "Check logs:"
echo "  tail -f $LOG_DIR/current"
echo ""
echo "Check logs with timestamps:"
echo "  tail -f $LOG_DIR/current | tai64nlocal"
echo ""
echo "Check D-Bus registration:"
echo "  dbus -y com.victronenergy.solarcharger.tristar_0 /ProductName GetValue"
echo ""
echo "Check current values:"
echo "  dbus -y com.victronenergy.solarcharger.tristar_0 /Dc/0/Voltage GetValue"
echo "  dbus -y com.victronenergy.solarcharger.tristar_0 /Yield/Power GetValue"
echo ""
echo "✅ Service will AUTO-START after reboot (configured in /data/rc.local)"
echo ""
