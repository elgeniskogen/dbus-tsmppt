# ⚠️ VIKTIG - Les Denne Først!

## PDF-en du viste meg endret ALT! 🎯

Venus OS v3.4+ (inkludert v3.65) bruker en **helt ny metode** for settings:

### ❌ Det gamle (QML) - IKKE bruk lenger!
- `qml/PageSettingsTristar.qml`
- `qml/install-gui.sh`
- Manuell GUI-integrasjon

### ✅ Det nye (SettingsDevice) - BRUK DETTE!
- `dbus_tristar.py`
- `install-v3.sh`
- **GUI genereres AUTOMATISK!**

## Hvilket Venus OS har du?

```bash
ssh root@<venus-ip>
cat /opt/victronenergy/version
```

| Versjon | Bruk | Se README |
|---------|------|-----------|
| **v3.4 - v3.65+** | ✅ `dbus_tristar.py` | [README-V3.md](README-V3.md) |
| v3.0 - v3.3 | ⚠️ Prøv `dbus_tristar.py` | [README-V3.md](README-V3.md) |
| v2.80 - v2.99 | `dbus-tsmppt.py` + QML | [README-PYTHON.md](README-PYTHON.md) |

## Moderne Installasjon (v3.4+)

```bash
# 1. Kopier til Venus
scp dbus_tristar.py install-v3.sh root@<venus-ip>:/tmp/

# 2. Installer
ssh root@<venus-ip>
cd /tmp
./install-v3.sh

# 3. Konfigurer
# Gå til: Settings → Services → TriStar MPPT
# Skriv inn IP-adresse: 192.168.1.100
```

**FERDIG!** Ingen QML! Ingen manuell GUI-kode!

## Nøkkelforskjeller

| Feature | Gammelt (QML) | Nytt (SettingsDevice) |
|---------|---------------|----------------------|
| **QML-filer** | Ja, manuelt | ❌ INGEN! |
| **Settings** | Array-format | Dictionary-format |
| **GUI** | Manuell integrasjon | Auto-generert |
| **Meny** | Settings → TriStar MPPT | Settings → Services → TriStar MPPT |
| **Lokasjon** | `/data/dbus-tsmppt/` | `/data/venus-data/dbus-plugins/tristar/` |

## Kode-eksempel

### Gammelt (Array-format)
```python
settings = SettingsDevice(
    supportedSettings={
        'ip': ['/Settings/TristarMPPT/IPAddress', '', 0, 0],  # ❌ Gammel
    }
)
```

### Nytt (Dictionary-format)
```python
settings = SettingsDevice(
    supported_settings={  # ✅ Nytt navn!
        'ip_address': {  # ✅ Dictionary!
            'default': '192.168.1.100',
            'description': 'TriStar IP address',
            'type': 's',
        },
    },
    deviceInstance=0
)
```

## Hvilke Filer skal du bruke?

### For Venus OS v3.4+ (MODERNE)
- ✅ `dbus_tristar.py`
- ✅ `install-v3.sh`
- ✅ `README-V3.md`
- ✅ `QUICKSTART-V3.md`
- ❌ **IKKE** bruk `qml/` mappen!

### For Venus OS v2.80 - v3.3 (LEGACY)
- ✅ `dbus-tsmppt.py`
- ✅ `install.sh`
- ✅ `qml/install-gui.sh` (hvis GUI ønsket)
- ✅ `README-PYTHON.md`
- ✅ `QUICKSTART.md`

## Hva skjer med Settings?

### Moderne (v3.4+)
Settings lagres i:
- `/data/conf/settings.db` (SQLite database)
- Vises automatisk i GUI
- Ingen XML-editing

### Legacy (v2.80-v3.3)
Settings lagres i:
- `/data/conf/settings.xml`
- Krever manuell QML for GUI

## Test at det fungerer

```bash
# Check logs
tail -f /var/log/dbus-tristar/current

# Check D-Bus
dbus -y com.victronenergy.solarcharger.tristar_0 /ProductName GetValue

# Se i GUI
# Settings → Services → TriStar MPPT ← Skal dukke opp automatisk!
```

## Takk til PDF-en! 🙏

PDF-en du viste meg (`Definere menyene i Venus OS.pdf`) forklarte:
- Den nye `SettingsDevice` API-en
- At QML IKKE lenger brukes for settings
- At GUI genereres automatisk fra `supported_settings`
- At drivers skal ligge i `/data/venus-data/dbus-plugins/`

**Uten den PDF-en hadde jeg laget en UTDATERT driver!**

---

## Oppsummering

✅ **Hvis du har Venus OS v3.4+**
- Bruk `dbus_tristar.py`
- Ingen QML
- Settings dukker opp automatisk
- Se [README-V3.md](README-V3.md)

✅ **Hvis du har Venus OS v2.80 - v3.3**
- Bruk `dbus-tsmppt.py`
- QML-filer for GUI (optional)
- Se [README-PYTHON.md](README-PYTHON.md)

❌ **Ikke bland metodene!**
- Moderne driver bruker IKKE QML
- Legacy driver TRENGER QML for GUI
- De er IKKE kompatible

---

**Start her: [README.md](README.md) → Finn din Venus-versjon → Følg riktig guide!**
