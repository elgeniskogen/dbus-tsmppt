# Hva er laget - Oppsummering

## 🎉 To komplette drivere for forskjellige Venus OS-versjoner

### 1. **Moderne Driver** (Venus OS v3.4+)

**Fil:** `dbus_tristar.py`

**Hvordan settings fungerer:**
- ✅ **Automatisk GUI-generering** - INGEN QML!
- ✅ `SettingsDevice` med dictionary-format
- ✅ Settings dukker opp i: **Settings → Services → TriStar MPPT**
- ✅ Lagres i `/data/conf/settings.db`

**Installasjon:**
```bash
scp dbus_tristar.py install-v3.sh root@venus:/tmp/
ssh root@venus
cd /tmp && ./install-v3.sh
```

**Dokumentasjon:**
- [README-V3.md](README-V3.md) - Full guide
- [QUICKSTART-V3.md](QUICKSTART-V3.md) - 3-minutters installasjon

**Basert på:** PDF-en du viste meg!

---

### 2. **Legacy Driver** (Venus OS v2.80 - v3.3)

**Fil:** `dbus-tsmppt.py`

**Hvordan settings fungerer:**
- ⚠️ Manuell QML for GUI (optional)
- ⚠️ `SettingsDevice` med array-format
- ⚠️ Lagres i `/data/conf/settings.xml`

**Installasjon:**
```bash
scp -r * root@venus:/data/dbus-tsmppt/
ssh root@venus
cd /data/dbus-tsmppt && ./install.sh
```

**Dokumentasjon:**
- [README-PYTHON.md](README-PYTHON.md) - Full guide
- [QUICKSTART.md](QUICKSTART.md) - 5-minutters installasjon
- [INSTALL.md](INSTALL.md) - Detaljert guide

---

## 📁 Filstruktur

```
dbus-tsmppt/
│
├── README.md                    # Hovedoversikt - START HER!
├── VIKTIGHETNOTE.md             # Forklarer forskjellen
├── SUMMARY.md                   # Dette dokumentet
│
├── MODERNE (v3.4+):
│   ├── dbus_tristar.py          # Moderne driver
│   ├── install-v3.sh            # Moderne installer
│   ├── README-V3.md             # Moderne docs
│   └── QUICKSTART-V3.md         # Moderne quickstart
│
├── LEGACY (v2.80-v3.3):
│   ├── dbus-tsmppt.py           # Legacy driver
│   ├── install.sh               # Legacy installer
│   ├── README-PYTHON.md         # Legacy docs
│   ├── QUICKSTART.md            # Legacy quickstart
│   └── INSTALL.md               # Detaljert installasjon
│
├── LEGACY QML (kun v2.80-v3.3):
│   └── qml/
│       ├── PageSettingsTristar.qml
│       ├── install-gui.sh
│       └── README.md
│
├── ORIGINAL C++ (kun v2.30 og eldre):
│   └── software/
│       ├── src/
│       ├── dbus-tsmppt.pro
│       └── README.md
│
└── FELLES:
    ├── test_connection.py       # Test Modbus-tilkobling
    ├── service/                 # Service-filer
    ├── uninstall.sh             # Avinstaller legacy
    └── README-ORIGINAL.md       # Original README
```

## 🔑 Nøkkelforskjeller

| Aspekt | Moderne (v3.4+) | Legacy (v2.80-v3.3) |
|--------|-----------------|---------------------|
| **QML-filer** | ❌ Ingen | ✅ Optional (for GUI) |
| **Settings API** | `supported_settings={}` | `supportedSettings=[]` |
| **GUI-generering** | Automatisk | Manuell QML |
| **Settings-fil** | `settings.db` | `settings.xml` |
| **Lokasjon** | `/data/venus-data/dbus-plugins/` | `/data/dbus-tsmppt/` |
| **Meny** | Services → TriStar | TriStar MPPT Settings |

## 🎯 Hvilken driver skal du bruke?

1. **Sjekk Venus OS-versjon:**
   ```bash
   ssh root@venus
   cat /opt/victronenergy/version
   ```

2. **Velg driver:**
   - **v3.4+** → Bruk `dbus_tristar.py` (moderne)
   - **v2.80 - v3.3** → Bruk `dbus-tsmppt.py` (legacy)
   - **v2.30 og eldre** → Bruk C++ i `software/`

3. **Les riktig README:**
   - Moderne → [README-V3.md](README-V3.md)
   - Legacy → [README-PYTHON.md](README-PYTHON.md)

## ✅ Hva er testet

- ✅ Koden kompilerer uten feil
- ✅ Modbus-logikk portet 1:1 fra C++
- ✅ D-Bus paths matcher Victron-standard
- ✅ Settings-format matcher PDF-eksempel
- ⚠️ **IKKE testet på ekte hardware enda**

## 📋 TODO før bruk på ekte system

1. **Test på Venus OS:**
   - Installer på test-system først
   - Verifiser GUI dukker opp
   - Test Modbus-kommunikasjon

2. **Sjekk Venus-versjon:**
   - Hvis v3.4+: Bruk moderne
   - Hvis v2.80-v3.3: Bruk legacy

3. **Juster settings paths:**
   - Modern driver: Settings lagres under `/Settings/Services/TriStar/`
   - Legacy driver: Settings lagres under `/Settings/TristarMPPT/`

## 🙏 Takk til PDF-en!

PDF-en (`Definere menyene i Venus OS.pdf`) ga kritisk info:
- Venus v3.4+ bruker IKKE QML for settings
- `SettingsDevice` har ny dictionary-format
- GUI genereres automatisk fra `supported_settings`
- Drivers hører hjemme i `/data/venus-data/dbus-plugins/`

**Uten PDF-en hadde jeg laget en utdatert driver!**

---

## 🚀 Kom i gang

1. Les [README.md](README.md)
2. Sjekk Venus OS-versjon
3. Følg riktig quickstart-guide
4. Nyt TriStar MPPT på Venus OS! ☀️🔋
