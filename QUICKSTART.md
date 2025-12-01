# Quick Start Guide

**3 minutes to get your TriStar MPPT working on Venus OS!**

---

## Step 1: Copy Files to Venus OS

```bash
scp dbus_tristar.py install.sh root@<venus-ip>:/tmp/
```

**Example:**
```bash
scp dbus_tristar.py install.sh root@192.168.1.156:/tmp/
```

---

## Step 2: SSH to Venus OS

```bash
ssh root@<venus-ip>
```

Default password is usually blank (just press Enter) or `root`.

---

## Step 3: Run Installer

```bash
cd /tmp
chmod +x install.sh
./install.sh
```

The installer will:
- ✅ Create `/data/venus-data/dbus-plugins/tristar/`
- ✅ Install driver and create service
- ✅ Start the driver automatically
- ✅ Install pymodbus if needed

---

## Step 4: Configure IP Address (REQUIRED)

**The driver needs your TriStar's IP address:**

```bash
dbus -y com.victronenergy.settings /Settings/TristarMPPT/IPAddress SetValue "192.168.1.100"
```

**Replace `192.168.1.100` with your TriStar's actual IP!**

---

## Step 5: Restart Driver

```bash
svc -t /service/dbus-tristar
```

---

## Step 6: Verify It's Working

```bash
tail -f /var/log/dbus-tristar/current
```

**You should see:**
```
TriStar MPPT 60 initialized
Serial: 12345678
HW: v1.2, FW: 2.15
```

**Press Ctrl+C to exit the log.**

---

## ✅ Check It Appears in Venus OS

Your TriStar MPPT should now be visible:
- **Venus OS GUI** → Main screen → Solar Charger tile
- **VRM Portal** → Device list → Solar Chargers
- **Remote Console** → Same as GUI

---

## Optional: Adjust Settings

```bash
# Change poll interval (default: 5000ms = 5 seconds)
dbus -y com.victronenergy.settings /Settings/TristarMPPT/Interval SetValue 5000

# Change Modbus port (default: 502)
dbus -y com.victronenergy.settings /Settings/TristarMPPT/PortNumber SetValue 502

# Change slave ID (default: 1)
dbus -y com.victronenergy.settings /Settings/TristarMPPT/SlaveID SetValue 1

# Restart after changes
svc -t /service/dbus-tristar
```

---

## Troubleshooting

### Can't Connect to TriStar?

```bash
# Test network connectivity
ping <tristar-ip>

# Test Modbus connection
python3 test_connection.py <tristar-ip> 502 1
```

### No Data Showing?

```bash
# Check current IP setting
dbus -y com.victronenergy.settings /Settings/TristarMPPT/IPAddress GetValue

# Check if driver is running
svstat /service/dbus-tristar

# Check D-Bus registration
dbus -y com.victronenergy.solarcharger.tristar_0 /ProductName GetValue
```

### Check Logs

```bash
tail -f /var/log/dbus-tristar/current
```

Look for:
- ✅ `TriStar MPPT XX initialized` - Success!
- ❌ `Failed to connect` - Check IP address and network
- ❌ `Modbus error` - Check TriStar has Modbus TCP enabled

---

## 🎉 That's It!

Your TriStar MPPT is now fully integrated with Venus OS!

**For detailed documentation, see:** [README.md](README.md)
