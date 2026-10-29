# DVCC Integration Notes

Findings from 2026-10-29, verified against the Venus OS source on the GX (`/opt/victronenergy/dbus-systemcalc-py/delegates/dvcc.py` and `batterysense.py`).

## Background

- The battery is 7S NMC with a passive BMS (no communication). Absorption is 28.7 V (4.10 V/cell).
- The BMV is the selected battery monitor (shown as "Battery" in *Settings → System Setup → Batteries → Battery monitor*).
- DVCC was turned on, with SVS, STS and SCS enabled, so that the MultiPlus regulates on BMV voltage. Before that, the MultiPlus regulated on its own measurement, which reads slightly lower than the BMV, and the BMV showed 28.74 V during absorption.
- The MultiPlus VE.Bus firmware is 1384 (0x568), which meets the DVCC requirement (0x422).

## Problem: GX Error #48 "DVCC with incompatible firmware"

This error appeared as soon as DVCC was enabled. `com.victronenergy.system /Dvcc/Alarms/FirmwareInsufficient = 1`.

**Cause:** `dbus_tristar.py` publishes `/FirmwareVersion = 0` and `/ProductId = 0xABCD`.

`SolarCharger.has_externalcontrol_support` in `dvcc.py` (around lines 322–349) checks in this order:

1. If `0xA102 <= ProductId <= 0xA10E`, it returns True. These are known Victron products, so this does not apply to us.
2. If `FirmwareVersion is None`, it returns True ("If the firmware version is not known, don't raise a false warning").
3. If `FirmwareVersion & 0xFF0000` is set, it requires `>= 0x10200` (VE.Can, 24-bit). Otherwise it requires `>= 0x129` (VE.Direct).

A value of 0 is not None and is below 0x129, so the check returns False and the alarm is raised (`dvcc.py` around line 1241).

**Fix (one line):** `dbus_tristar.py:826`
```python
s.add_path('/FirmwareVersion', None)   # was 0. None = "unknown", which suppresses the false DVCC warning
```
Alternative: publish the TriStar's real firmware version. It must then be `>= 0x129` to avoid the warning.

**This is safe.** The firmware version only affects the warning. Venus decides whether to *write* to a solar charger based on which `/Link/*` paths the service has:

| Feature | Condition in Venus source | What Venus writes |
|---|---|---|
| SVS (shared voltage sense) | `batterysense.py:299`: skips the charger unless `seen(service, '/Link/VoltageSense')` | `/Link/VoltageSense` = battery monitor voltage |
| SCS (shared current sense) | `batterysense.py:339`: skips unless `seen(service, '/Link/BatteryCurrent')` | `/Link/BatteryCurrent` = battery monitor current |
| STS (shared temperature sense) | `batterysense.py:370–375`: requires `/Link/NetworkMode` not None and `/Link/TemperatureSense` seen | `/Link/TemperatureSense` |
| DVCC charge limits | `dvcc.py:1632`: "We use /Link/NetworkMode to detect Hub support in the solarcharger. Existence of this item implies existence of the other /Link/* fields." | `/Link/NetworkMode`, `/Link/ChargeVoltage`, `/Link/ChargeCurrent` |

The driver publishes no `/Link/*` paths today, so Venus writes nothing to it regardless of the firmware version.

## Optional: let the TriStar take part in DVCC

### Step 1: receive data only (low risk, no change to regulation)

Add these writeable paths:
- `/Link/VoltageSense`: BMV voltage from SVS. Use it for diagnostics and for comparison with `/Dc/0/Voltage`. It could later drive a voltage correction.
- `/Link/BatteryCurrent`: BMV current from SCS. This is the true battery current, unaffected by loads, and gives better tail-current detection than the TriStar's own output current (see `battery_full_current` / `tail_current_time` and the VoltageOverride logic). "SCS status" in the GUI should then change from "Disabled (no chargers)".

Treat both as optional. If no value has arrived recently, fall back to the driver's own measurements.

### Step 2: let DVCC control the TriStar (needs a design decision)

Publish `/Link/NetworkMode`, `/Link/ChargeVoltage` and `/Link/ChargeCurrent`, and map them to `Vb_ref_slave` (PDU 89) and `Ib_ref_slave` (PDU 88).

This conflicts with the driver's own seasonal charge profiles and VoltageOverride logic, so a priority rule is needed first. It only matters if "Limit charge current" is enabled in DVCC, or if a BMS that communicates with Venus is added later.

## Voltage sense for the TriStar

The TriStar has no Modbus register that accepts an external sense voltage. There are two options:
1. **Physical battery-sense wires** on the TriStar's sense terminals (recommended). Check `/Custom/Battery/SenseVoltage` first: 0 probably means the wires are not connected.
2. **Software correction**: adjust `Vb_ref_slave` by the difference between BMV voltage and TriStar voltage. This adds a control loop on top of the TriStar's own regulation and is more fragile than two wires.

## Useful commands on the GX

```sh
dbus -y com.victronenergy.system /Dvcc/Alarms/FirmwareInsufficient GetValue
dbus -y com.victronenergy.solarcharger.tristar_0 /FirmwareVersion GetValue
dbus -y com.victronenergy.system /Control/BatteryCurrentSense GetValue
cd /opt/victronenergy/dbus-systemcalc-py/delegates && grep -n "/Link/" dvcc.py batterysense.py
```
