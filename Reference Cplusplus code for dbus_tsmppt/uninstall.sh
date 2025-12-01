#!/bin/bash

# Uninstall script for dbus-tsmppt on Venus OS

SERVICE_NAME=dbus-tsmppt
INSTALL_DIR=/data/dbus-tsmppt

echo "Uninstalling dbus-tsmppt..."

# Stop and remove service
if [ -L /service/$SERVICE_NAME ]; then
    echo "Stopping service..."
    svc -d /service/$SERVICE_NAME
    sleep 2
    rm /service/$SERVICE_NAME
    echo "Service removed"
fi

# Remove installation directory
if [ -d $INSTALL_DIR ]; then
    echo "Removing installation directory..."
    rm -rf $INSTALL_DIR
    echo "Files removed"
fi

# Remove log directory
if [ -d /var/log/$SERVICE_NAME ]; then
    echo "Removing logs..."
    rm -rf /var/log/$SERVICE_NAME
fi

echo ""
echo "Uninstall complete!"
echo ""
echo "Note: Settings in /Settings/TristarMPPT/ were not removed."
echo "To remove settings, use:"
echo "  dbus -y com.victronenergy.settings /Settings/TristarMPPT/IPAddress Delete"
echo "  dbus -y com.victronenergy.settings /Settings/TristarMPPT/PortNumber Delete"
echo "  dbus -y com.victronenergy.settings /Settings/TristarMPPT/Interval Delete"
echo ""
