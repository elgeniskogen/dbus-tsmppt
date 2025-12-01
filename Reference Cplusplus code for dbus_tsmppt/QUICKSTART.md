# Quick Start Guide

Get your TriStar MPPT running on Venus OS in 5 minutes!

## 1. Copy Files to Venus OS

```bash
scp -r * root@venus-ip:/data/dbus-tsmppt/
```

## 2. Install Driver

```bash
ssh root@venus-ip
cd /data/dbus-tsmppt
./install.sh
```

## 3. Install GUI (Optional - for devices with screen)

```bash
cd /data/dbus-tsmppt/qml
./install-gui.sh
```

Then configure via: **Settings → TriStar MPPT Solar Charger**

## 4. Configure IP Address

### Option A: Via GUI
- Settings → TriStar MPPT Solar Charger
- Enter IP address: `192.168.1.100`

### Option B: Via Command Line
```bash
dbus -y com.victronenergy.settings /Settings/TristarMPPT/IPAddress SetValue "192.168.1.100"
svc -t /service/dbus-tsmppt
```

## 5. Done! 🎉

Check it's working:
```bash
tail -f /var/log/dbus-tsmppt/current
```

You should see:
- "TriStar MPPT XX initialized"
- "Serial: XXXXXXXX"
- No errors

## Troubleshooting

**No connection?**
```bash
python3 /data/dbus-tsmppt/test_connection.py 192.168.1.100
```

**Not showing in GUI?**
- Wait 30 seconds
- Restart GUI: `svc -t /service/gui`
- Reboot if needed

**Need help?**
- See [INSTALL.md](INSTALL.md) for detailed guide
- Check logs: `tail -f /var/log/dbus-tsmppt/current`
