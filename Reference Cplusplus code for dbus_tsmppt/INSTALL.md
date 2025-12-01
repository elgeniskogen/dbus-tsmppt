# Installation Guide - TriStar MPPT Driver for Venus OS

Complete installation guide for the modern Python-based TriStar MPPT driver.

## Quick Start (3 Minutes)

```bash
# 1. Copy files to Venus OS (from your computer)
scp -r * root@venus-ip:/data/dbus-tsmppt/

# 2. SSH into Venus OS
ssh root@venus-ip

# 3. Install
cd /data/dbus-tsmppt
./install.sh

# 4a. GUI method (devices with screen)
cd /data/dbus-tsmppt/qml
./install-gui.sh
# Then configure via: Settings → TriStar MPPT Solar Charger

# 4b. Command line method (all devices)
dbus -y com.victronenergy.settings /Settings/TristarMPPT/IPAddress SetValue "192.168.1.100"
svc -t /service/dbus-tsmppt
```

## Detailed Installation

### Prerequisites

1. **Venus OS Device**
   - Cerbo GX, Venus GX, CCGX, Ekrano GX, or Raspberry Pi with Venus OS
   - Venus OS v2.80 or later (v3.x recommended)
   - Network connection to device

2. **TriStar MPPT**
   - TriStar MPPT 30, 45, or 60
   - Ethernet connection (Modbus TCP enabled)
   - Known IP address

3. **Network**
   - TriStar MPPT and Venus OS on same network (or routable)
   - IP connectivity verified with `ping`

### Step 1: Enable SSH Access

On your Venus OS device:

1. **Settings → General → Access level** → Set to "Superuser"
2. **Settings → General → Remote support** → Enable SSH on LAN
3. Note the IP address from **Settings → General → Network status**

### Step 2: Copy Files to Venus OS

From your computer (Mac/Linux):

```bash
# Clone or download this repository first
git clone https://github.com/yourusername/dbus-tsmppt.git
cd dbus-tsmppt

# Copy to Venus OS
scp -r * root@<venus-ip>:/data/dbus-tsmppt/
```

**Windows users:** Use WinSCP or similar tool to copy files to `/data/dbus-tsmppt/`

### Step 3: Run Installation Script

```bash
# SSH into Venus OS
ssh root@<venus-ip>

# Navigate to installation directory
cd /data/dbus-tsmppt

# Make install script executable (if needed)
chmod +x install.sh

# Run installer
./install.sh
```

The installer will:
- ✓ Create `/data/dbus-tsmppt/` directory structure
- ✓ Copy driver files
- ✓ Install Python dependencies (`python3-pymodbus`)
- ✓ Create D-Bus settings
- ✓ Set up service for auto-start
- ✓ Start the service

### Step 4: Test Connection (Optional but Recommended)

Before configuring, verify your TriStar MPPT is reachable:

```bash
# Test network connectivity
ping 192.168.1.100

# Test Modbus TCP connection
cd /data/dbus-tsmppt
python3 test_connection.py 192.168.1.100
```

You should see:
```
✓ Connected successfully
✓ Read registers successfully
✓ Model: TriStar MPPT 60
✓ Serial number: 12345678
✓ Battery voltage: 13.8V
```

### Step 5: Configure Connection

Choose **either** GUI or command line method:

#### Option A: GUI Configuration (Recommended)

For devices with a screen (Cerbo GX, Ekrano GX):

```bash
cd /data/dbus-tsmppt/qml
./install-gui.sh
```

Then on the device screen:
1. Go to **Settings**
2. Scroll to **TriStar MPPT Solar Charger**
3. Tap **Setup**
4. Enter IP address: `192.168.1.100`
5. Verify Port: `502`
6. Adjust interval if needed: `5000` ms

The GUI page shows:
- IP Address / Hostname input
- Modbus TCP Port setting
- Update Interval setting
- Connection Status (live)
- Device info when connected

#### Option B: Command Line Configuration

For all devices:

```bash
# Set IP address (REQUIRED)
dbus -y com.victronenergy.settings /Settings/TristarMPPT/IPAddress SetValue "192.168.1.100"

# Set port if not 502 (optional)
dbus -y com.victronenergy.settings /Settings/TristarMPPT/PortNumber SetValue 502

# Set update interval in ms (optional, default 5000 = 5 seconds)
dbus -y com.victronenergy.settings /Settings/TristarMPPT/Interval SetValue 5000

# Restart service to apply
svc -t /service/dbus-tsmppt
```

### Step 6: Verify Installation

```bash
# Check service status
svstat /service/dbus-tsmppt
# Should show: up (run: X seconds)

# Check logs
tail -f /var/log/dbus-tsmppt/current

# Look for:
# - "dbus-tsmppt v2.0 starting"
# - "TriStar MPPT XX initialized"
# - "Serial: XXXXXXXX"
# - No connection errors

# Verify D-Bus registration
dbus -y com.victronenergy.solarcharger.tsmppt /ProductName GetValue
# Should return: TriStar MPPT 60 (or 30/45)

# Check live data
dbus -y com.victronenergy.solarcharger.tsmppt /Dc/0/Voltage GetValue
dbus -y com.victronenergy.solarcharger.tsmppt /Yield/Power GetValue
```

### Step 7: View in Venus OS

The TriStar MPPT should now appear:

1. **On device screen:**
   - Main screen → Solar Charger tile
   - Shows battery voltage, current, power

2. **In VRM Portal:**
   - Device list → Solar Chargers → TriStar MPPT
   - Dashboard widgets for solar data
   - Historical data in Advanced

3. **Remote Console:**
   - Same as device screen (accessed via web browser)

## Uninstallation

```bash
cd /data/dbus-tsmppt

# Remove GUI integration (if installed)
cd qml
./uninstall-gui.sh

# Remove driver
cd ..
./uninstall.sh
```

## Troubleshooting

### Service won't start

```bash
# Check Python is installed
which python3

# Check dependencies
opkg list-installed | grep pymodbus

# Run manually to see errors
python3 /data/dbus-tsmppt/dbus-tsmppt.py
```

### No connection to TriStar

```bash
# Verify IP is correct
dbus -y com.victronenergy.settings /Settings/TristarMPPT/IPAddress GetValue

# Test network
ping 192.168.1.100

# Test Modbus
python3 /data/dbus-tsmppt/test_connection.py 192.168.1.100

# Check TriStar MPPT Modbus settings
# - Modbus TCP must be enabled
# - Port should be 502
# - Check firewall if applicable
```

### GUI menu doesn't appear

```bash
# Verify QML file exists
ls -l /opt/victronenergy/gui/qml/PageSettingsTristar.qml

# Restart GUI
svc -t /service/gui

# Check GUI logs
tail -f /var/log/gui/current

# Try reboot
reboot
```

### Data shows in D-Bus but not GUI

The driver registers as a Solar Charger, so it should appear automatically. Check:

```bash
# Verify service is registered
dbus-spy | grep solarcharger.tsmppt

# Check Connected flag
dbus -y com.victronenergy.solarcharger.tsmppt /Connected GetValue
# Should return: 1

# Check ProductId
dbus -y com.victronenergy.solarcharger.tsmppt /ProductId GetValue
```

### Settings don't persist

Settings are stored in `/data/conf/settings.xml` by localsettings.

```bash
# Verify settings service is running
svstat /service/localsettings

# Check settings exist
grep -A5 "TristarMPPT" /data/conf/settings.xml

# Manually add if missing (run install.sh again)
```

## Advanced Configuration

### Change Update Frequency

Default is 5 seconds. You can adjust from 1-60 seconds:

```bash
# Faster updates (2 seconds)
dbus -y com.victronenergy.settings /Settings/TristarMPPT/Interval SetValue 2000

# Slower updates (10 seconds, saves network bandwidth)
dbus -y com.victronenergy.settings /Settings/TristarMPPT/Interval SetValue 10000

# Restart
svc -t /service/dbus-tsmppt
```

### Multiple TriStar MPPTs

To add multiple TriStar MPPTs, you'll need to:
1. Create separate instances with different service names
2. Modify `dbus-tsmppt.py` to use unique D-Bus service name
3. Create separate settings paths

This is advanced - contact for help if needed.

### Persistent Installation

The `/data` directory persists across reboots and firmware updates on Venus OS.

Your installation will survive:
- ✓ Reboots
- ✓ Firmware updates
- ✓ Power loss

### Auto-Start on Boot

The service is already configured to auto-start via the `/service` symlink.

Verify:
```bash
ls -l /service/dbus-tsmppt
# Should point to: /data/dbus-tsmppt/service
```

## Support

### Logs

Always check logs first:
```bash
tail -f /var/log/dbus-tsmppt/current
```

### Enable Debug Logging

Edit `/data/dbus-tsmppt/dbus-tsmppt.py`:

```python
logging.basicConfig(
    level=logging.DEBUG,  # Change from INFO
    format='%(asctime)s %(levelname)-8s %(message)s'
)
```

Restart:
```bash
svc -t /service/dbus-tsmppt
```

### Common Issues

| Problem | Solution |
|---------|----------|
| Service down | Check logs, verify IP set |
| No data | Check Modbus connection |
| Connection lost | Check network, verify IP |
| GUI missing | Run `qml/install-gui.sh` |
| Settings reset | Check `/data/conf/settings.xml` |

### Getting Help

1. Check logs: `tail -f /var/log/dbus-tsmppt/current`
2. Test connection: `python3 test_connection.py <ip>`
3. Verify D-Bus: `dbus-spy | grep tsmppt`
4. Check service: `svstat /service/dbus-tsmppt`

## Next Steps

After successful installation:

1. **Monitor in VRM Portal**
   - View solar production
   - Track historical data
   - Set up alerts

2. **Configure ESS** (if applicable)
   - Solar data feeds into ESS calculations
   - Optimize self-consumption

3. **Set up DVCC** (if multiple solar chargers)
   - Coordinated charging
   - BMS integration

Enjoy your TriStar MPPT integration! ☀️🔋
