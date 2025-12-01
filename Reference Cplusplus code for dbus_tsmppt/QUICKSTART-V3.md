# Quick Start - Venus OS v3.4+ (Modern Method)

**3 minutes to get your TriStar MPPT working!**

## ⚡ Super Quick Install

```bash
# 1. Copy to Venus OS
scp dbus_tristar.py install-v3.sh root@<venus-ip>:/tmp/

# 2. SSH and install
ssh root@<venus-ip>
cd /tmp
./install-v3.sh
```

## ⚙️ Configure (Choose ONE method)

### GUI Method (Easiest!)
1. Go to: **Settings → Services → TriStar MPPT**
2. Enter IP address: `192.168.1.100`
3. Done!

### Command Line Method
```bash
dbus -y com.victronenergy.settings /Settings/Services/TriStar/ip_address SetValue "192.168.1.100"
```

## ✅ Verify It's Working

```bash
tail -f /var/log/dbus-tristar/current
```

You should see:
```
TriStar MPPT 60 initialized
Serial: 12345678
```

## 🎉 That's It!

Your TriStar MPPT now appears in:
- Venus OS GUI → Solar Charger tile
- VRM Portal → Device list
- Remote Console

---

**IMPORTANT:** This is for Venus OS **v3.4+**

For older versions, see [README-PYTHON.md](README-PYTHON.md) (legacy QML method)
