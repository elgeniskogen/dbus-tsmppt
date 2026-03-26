# TriStar MPPT Driver - Complete Documentation

**Version:** 2.26
**Author:** dbus-tristar driver
**Target:** Morningstar TriStar MPPT 60 via Modbus TCP

---

## Table of Contents

1. [Overview](#overview)
2. [D-Bus Paths Reference](#dbus-paths-reference)
3. [Voltage Override System](#voltage-override-system)
4. [Current Override System](#current-override-system)
5. [Charge Profile Management System](#charge-profile-management-system)
6. [Automatic Battery Full Detection](#automatic-battery-full-detection)
7. [Nightly Reset Logic](#nightly-reset-logic)
8. [Daily History & State Persistence](#daily-history--state-persistence)
9. [Configuration](#configuration)
10. [Modbus Register Reference](#modbus-register-reference)

---

## Overview

This driver reads data from a Morningstar TriStar MPPT charge controller via Modbus TCP and exposes it to Venus OS via D-Bus. It implements advanced features including:

- **Charge profile management** for seasonal battery optimization (EEPROM programming)
- **Voltage override** for battery top-charging (equalization)
- **Automatic battery full detection** via tail current monitoring
- **Cumulative time tracking** (tolerates brief voltage dips)
- **31-day history** tracking with daily max/min values (Day 0-30)
- **Nightly reset** to prevent stuck charging sessions
- **State persistence** across reboots

---

## D-Bus Paths Reference

### Standard Victron Paths

These paths follow the Victron solar charger specification:

#### Device Information
```
/ProductName         = "TriStar MPPT 60"
/Mgmt/ProductId      = 0xABCD
/Mgmt/Connection     = "Modbus TCP 192.168.2.103:502"
/FirmwareVersion     = 42 (TriStar firmware version)
/HardwareVersion     = "v1.1"
/Serial              = "1712069"
/DeviceInstance      = 0 (configurable)
/Connected           = 1
/ProductId           = 0xABCD
/CustomName          = "TriStar MPPT 60"
```

#### Real-time Measurements
```
/Dc/0/Voltage            = Battery voltage (V)
/Dc/0/Current            = Charge current (A)
/Pv/V                    = PV array voltage (V)
/Pv/I                    = PV array current (A)
/Yield/Power             = Output power (W)
/Dc/0/Temperature        = Battery temperature (°C)
```

#### Charge Control & State
```
/Mode                    = 1 (On) or 4 (Off) - WRITEABLE
/State                   = Victron charge state (0=Off, 2=Fault, 3=Bulk, 4=Absorption, 5=Float)
/MppOperationMode        = 0 (Off), 1 (Voltage/Current limited), 2 (MPPT tracking)
/ErrorCode               = Victron error code
```

#### Daily & Lifetime Yield
```
/History/Daily/0/Yield           = Today's yield (kWh)
/History/Daily/0/MaxPower        = Today's max power (W)
/History/Daily/0/MaxVoltage      = Today's max battery voltage (V)
/History/Daily/0/MinVoltage      = Today's min battery voltage (V)
/History/Daily/0/MaxCurrent      = Today's max charge current (A)
/History/Daily/0/TimeInBulk      = Time in Bulk today (seconds)
/History/Daily/0/TimeInAbsorption = Time in Absorption today (seconds)
/History/Daily/0/TimeInFloat     = Time in Float today (seconds)

/Yield/System                    = Lifetime total yield (kWh) - from state.json
```

#### Historical Data (Days 1-30)
```
/History/Daily/1/Yield           = Yesterday's yield (kWh)
/History/Daily/1/MaxPower        = Yesterday's max power (W)
... (same fields for days 1-30)
```

---

### Settings Paths

Located at: `venus-home/N/.../settings/0/Settings/TristarMPPT/...`

All settings are **writeable** and persistent.

#### Connection Settings
```
IPAddress               = "192.168.2.103"  (IP address of TriStar)
PortNumber              = 502              (Modbus TCP port, range: 1-65535)
SlaveID                 = 1                (Modbus slave ID, range: 1-247)
Interval                = 5000             (Poll interval in ms, range: 1000-60000)
DeviceInstance          = 0                (Venus device instance, range: 0-255)
```

#### Operational Settings
```
StateSaveInterval       = 300              (Save state.json every N seconds, range: 60-3600)
WatchdogTimeout         = 180              (Mark disconnected after N seconds, range: 30-600)
NightlyResetHour        = 3                (Reset at this hour local time, range: 0-23)
```

#### Voltage Override Settings
```
MaxVoltageOverrideVoltage = 28.7           (SAFETY LIMIT - max voltage, range: 24.0-32.0V)
MaxVoltageOverrideTime    = 7200           (Max time per day in seconds, range: 0-86400)
BatteryFullCurrent        = 2.0            (Tail current threshold in A, range: 0.0-100.0)
TailCurrentTime           = 300            (Sustained tail current time in seconds, range: 0-3600)
ExcessPowerThreshold      = 100            (Minimum excess power in W, range: -1-5000, -1=disabled)
```

#### Charge Profile Settings
```
ChargeProfiles/Summer/AbsorptionVoltage     = 28.4  (V, range: 26.0-32.0)
ChargeProfiles/Summer/FloatVoltage          = 27.2  (V, range: 24.0-30.0)
ChargeProfiles/Summer/AbsorptionTime        = 7200  (seconds, range: 3600-36000)
ChargeProfiles/Summer/FloatCancelVoltage    = 26.0  (V, range: 22.0-28.0)

ChargeProfiles/Winter/AbsorptionVoltage     = 28.8  (V, range: 26.0-32.0)
ChargeProfiles/Winter/FloatVoltage          = 27.6  (V, range: 24.0-30.0)
ChargeProfiles/Winter/AbsorptionTime        = 9000  (seconds, range: 3600-36000)
ChargeProfiles/Winter/FloatCancelVoltage    = 26.4  (V, range: 22.0-28.0)

ChargeProfiles/Custom/AbsorptionVoltage     = 28.6  (V, range: 26.0-32.0)
ChargeProfiles/Custom/FloatVoltage          = 27.4  (V, range: 24.0-30.0)
ChargeProfiles/Custom/AbsorptionTime        = 8400  (seconds, range: 3600-36000)
ChargeProfiles/Custom/FloatCancelVoltage    = 26.2  (V, range: 22.0-28.0)
```

**Note:** All voltage values are actual system voltages. Driver automatically converts to 12V-equivalent when writing to EEPROM (12V/24V/48V systems supported).

**Example:** Configure custom winter profile
```bash
dbus -y com.victronenergy.settings /Settings/TristarMPPT/ChargeProfiles/Custom/AbsorptionVoltage SetValue 29.0
dbus -y com.victronenergy.settings /Settings/TristarMPPT/ChargeProfiles/Custom/FloatVoltage SetValue 27.8
dbus -y com.victronenergy.settings /Settings/TristarMPPT/ChargeProfiles/Custom/AbsorptionTime SetValue 10800
dbus -y com.victronenergy.settings /Settings/TristarMPPT/ChargeProfiles/Custom/FloatCancelVoltage SetValue 26.6
```

**Example:** Change tail current threshold
```bash
dbus -y com.victronenergy.settings /Settings/TristarMPPT/BatteryFullCurrent SetValue 1.5
```

---

### Control Paths (Writeable)

Located at: `venus-home/N/.../solarcharger/0/Control/...`

#### Mode Control
```
/Mode                           WRITEABLE
  1 = On  (clears COIL_DISCONNECT, allows charging)
  4 = Off (sets COIL_DISCONNECT, stops charging)
```

#### Voltage Override
```
/Control/VoltageOverride        WRITEABLE (V)
  > 0   = Enable override at specified voltage (e.g., 28.7)
  <= 0  = Disable override

  Safety: Limited to MaxVoltageOverrideVoltage setting
  Register: PDU 89 (vb_ref_slave)
  Effect: Puts TriStar in SLAVE mode (ChargeState = 9)
```

#### Current Override
```
/Control/CurrentOverride        WRITEABLE (A)
  > 0   = Enable current limit (e.g., 10.0)
  <= 0  = Disable current limit

  Register: PDU 88 (Ib_ref_slave)
  NOTE: Auto-enables voltage override to maintain slave mode
  WARNING: Less tested than voltage-only override
```

#### Charge Profile Management
```
/Control/ApplyChargeProfile     WRITEABLE (text)
  "summer"  = Apply summer profile (lower voltage, shorter absorption)
  "winter"  = Apply winter profile (higher voltage, longer absorption)
  "custom"  = Apply custom profile (user-configurable via Settings)

  Effect: Writes charge parameters to EEPROM with safety checks
  Safety: DISCONNECT → Write → Verify → Reset controller
  Thread-safe: Main loop paused during operation
  Backup: Automatic backup before changes
  Status: Monitor via /Custom/ChargeProfile/ApplyStatus
```

#### Coil Controls (Momentary Triggers)
```
/Control/EqualizeTriggered      WRITEABLE (bool) - Trigger equalize charge
/Control/ChargerDisconnect      WRITEABLE (bool) - Force disconnect
/Control/ResetController        WRITEABLE (bool) - Reset TriStar controller
/Control/ResetCommServer        WRITEABLE (bool) - Reset TriStar comm server
```

---

### Custom Monitoring Paths (Read-Only)

Located at: `venus-home/N/.../solarcharger/0/Custom/...`

#### Voltage Override Status
```
/Custom/VoltageOverride/Active              (bool) - Is override active?
/Custom/VoltageOverride/CurrentVoltage      (V) - Current override setpoint
/Custom/VoltageOverride/RegisterReadback    (V) - Readback from PDU 89
/Custom/VoltageOverride/TimeAtTargetVoltage (sec) - Cumulative time at/above target
/Custom/VoltageOverride/TailCurrentTimer    (sec) - Time at tail current condition
/Custom/VoltageOverride/StopReason          (text) - Why override stopped
  Values: "BatteryFull", "TimeLimit", "UserDisabled", "NightlyReset"
/Custom/VoltageOverride/ExcessPower         (W) - Excess power available
```

#### Current Override Status
```
/Custom/CurrentOverride/Active              (bool) - Is current override active?
/Custom/CurrentOverride/CurrentValue        (A) - Current override setpoint
/Custom/CurrentOverride/RegisterReadback    (A) - Readback from PDU 88
```

#### Daily Register Tracking (For Debugging)
```
/Custom/Daily/ChargeWh                      (Wh) - Raw REG_WHC_DAILY value
/Custom/Daily/ChargeAh                      (Ah) - Daily Ah from TriStar
```

#### EEPROM Counters & Charge Parameters (TriStar's Internal)
```
/Custom/EEPROM/ChargeKwhTotal               (kWh) - Lifetime total from 0xE087
/Custom/EEPROM/ChargeKwhResetable           (kWh) - Resetable counter from 0xE086
/Custom/EEPROM/AbsorptionVoltage            (V) - Active absorption voltage (0xE000)
/Custom/EEPROM/FloatVoltage                 (V) - Active float voltage (0xE001)
/Custom/EEPROM/AbsorptionTime               (sec) - Active absorption time (0xE002)
/Custom/EEPROM/FloatCancelVoltage           (V) - Active float cancel voltage (0xE005)
/Custom/EEPROM/EqualizeVoltage              (V) - Configured equalize voltage
/Custom/EEPROM/TempCompensation             (V/C) - Temperature compensation
/Custom/EEPROM/MaxRegulationLimit           (V) - Max regulation voltage limit
```

**Note:** Voltage values are automatically scaled for 12V/24V/48V systems. EEPROM stores 12V-equivalent values, driver converts to actual system voltage.

#### Charge Profile Status
```
/Custom/ChargeProfile/ApplyStatus           (text) - Profile apply operation status
  Values: "idle", "validating", "disconnecting", "writing", "resetting", "success", "failed"
/Custom/ChargeProfile/ProgressPercent       (%) - Apply operation progress (0-100)
/Custom/ChargeProfile/LastError             (text) - Last error message (if failed)
/Custom/ChargeProfile/LastApplied           (text) - "profile_name at YYYY-MM-DD HH:MM:SS"
```

#### Battery & Internal Monitoring
```
/Custom/Battery/SenseVoltage                (V) - Battery sense terminal voltage
/Custom/Battery/CurrentFast                 (A) - Fast charge current sample
/Custom/Battery/VoltageSlow                 (V) - Slow (filtered) battery voltage
/Custom/InternalSupply/Rail12V              (V) - Internal 12V rail
/Custom/InternalSupply/Rail3V               (V) - Internal 3.3V rail
/Custom/InternalSupply/Rail5V               (V) - Internal 5V rail
```

#### TriStar Charge State (Raw)
```
/Custom/TriStarChargeState                  (int) - Raw TriStar charge state
  0 = Start/Night
  1 = Night Check
  2 = Disconnect
  3 = Night
  4 = Fault
  5 = Bulk (MPPT)
  6 = Absorption
  7 = Float
  8 = Equalize
  9 = Slave (override active)
```

---

## Voltage Override System

### Purpose
Top-charge (equalize) the battery to a higher voltage than normal absorption for cell balancing.

### How It Works

#### 1. User Enables Override
```
Topic: W/.../solarcharger/0/Control/VoltageOverride
Payload: 28.7   (target voltage)
```

#### 2. Driver Validates & Writes
```python
# Safety check
if voltage > MaxVoltageOverrideVoltage:
    REJECT  # Critical safety limit

# Convert to register value
register_value = int(voltage * 182.04)

# Write to TriStar
write_holding_register(89, register_value)  # PDU 89 = vb_ref_slave

# TriStar enters SLAVE mode (ChargeState = 9)
```

#### 3. Cumulative Time Tracking

**Goal:** Measure total time at or above target voltage, tolerating brief dips.

```python
# At target: V >= target (NOT within ±0.1V tolerance!)
at_target = v_battery >= target_voltage

# Accumulate time (Home Assistant history_stats pattern)
if at_target and override_start_time is None:
    override_start_time = current_time
    time_above_target_accumulated = 0

if at_target:  # ONLY accumulates when V >= target!
    delta = current_time - last_update
    if 0 < delta < 10:  # Sanity check
        time_above_target_accumulated += delta
# If V < target: Counter PAUSES (doesn't increase, doesn't reset)

# Result: Cumulative seconds at/above target
time_at_target = time_above_target_accumulated
```

**Behavior during voltage dips:**
- ✅ Counts ONLY when V >= target voltage
- ✅ PAUSES when V < target (stops counting)
- ✅ Does NOT reset when voltage dips
- ✅ RESUMES counting when V >= target again

**Example:**
```
10:00 - V=28.70V → Counter starts, accumulated = 0s
10:30 - V=28.71V → accumulated = 1800s (30 min AT target)
10:30 - V=28.68V → PAUSED at 1800s (below target, stops counting)
10:31 - V=28.67V → Still 1800s (paused, not counting)
10:32 - V=28.70V → RESUMES counting from 1800s
10:33 - V=28.71V → accumulated = 1860s (30 min + 1 min AT target)
```

This is **cumulative time AT/ABOVE target**, not total elapsed time. Brief dips don't reset the counter, they just pause it.

#### 4. Tail Current Detection

**Condition:** Battery is "full" when:
- Voltage ≥ target voltage, AND
- Current < BatteryFullCurrent (e.g., 2.0A), AND
- Excess power check passes (if enabled), AND
- Sustained for TailCurrentTime seconds (e.g., 300s)

```python
if at_target and i_charge < battery_full_current:
    if tail_current_start_time is None:
        tail_current_start_time = current_time

    tail_duration = current_time - tail_current_start_time

    if tail_duration >= tail_current_time:
        # Battery full!
        stop_reason = "BatteryFull"
        write_holding_register(89, -1)  # Disable override
else:
    tail_current_start_time = None  # RESET timer to zero!
```

**Behavior during current fluctuations:**
- ✅ Counts only when ALL conditions are met (V >= target AND I < threshold)
- ❌ RESETS to zero if ANY condition fails
- ⚠️ Different from TimeAtTarget which only pauses!

**Example:**
```
11:00 - V=28.70V, I=1.8A → Timer starts, duration = 0s
11:02 - V=28.71V, I=1.7A → duration = 120s
11:03 - V=28.72V, I=2.1A → RESET to 0s! (I > 2.0A)
11:04 - V=28.71V, I=1.9A → Timer starts again, duration = 0s
11:09 - V=28.70V, I=1.8A → duration = 300s → BATTERY FULL!
```

**CRITICAL:** This must be **300 seconds continuously** with low current. Any spike above threshold resets the timer!

#### 5. Time Limit

**Condition:** Override active for too long.

```python
if time_at_target >= max_voltage_override_time:
    # Time limit reached!
    stop_reason = "TimeLimit"
    write_holding_register(89, -1)  # Disable override
```

#### 6. User Disables
```
Payload: 0   (or any value <= 0)
```

Immediately writes -1 (0xFFFF in two's complement) to PDU 89 to disable slave mode.

### Monitoring

**Active status:**
```
/Custom/VoltageOverride/Active = True/False
```

**Progress:**
```
/Custom/VoltageOverride/TimeAtTargetVoltage = 1234  (seconds)
/Custom/VoltageOverride/TailCurrentTimer = 45       (seconds at tail current)
```

**Completion:**
```
/Custom/VoltageOverride/StopReason = "BatteryFull"
```

### Timer Comparison: TimeAtTarget vs TailCurrent

**Important:** These two timers work differently!

| Timer | Behavior | Reset Condition | Purpose |
|-------|----------|-----------------|---------|
| **TimeAtTarget** | PAUSES during dips | Never resets (only on disable) | Safety time limit (2h max) |
| **TailCurrent** | RESETS to zero | Resets if I > threshold OR V < target | Detect battery full |

**Example scenario:**
```
10:00 - V=28.70V, I=8.0A
  → TimeAtTarget starts (0s)
  → TailCurrent not started (I too high)

10:30 - V=28.71V, I=1.8A
  → TimeAtTarget = 1800s (counting continuously)
  → TailCurrent starts (0s)

10:32 - V=28.68V, I=1.9A  (brief voltage dip)
  → TimeAtTarget = 1920s (PAUSED, but not reset)
  → TailCurrent RESET to 0s! (V < target)

10:33 - V=28.70V, I=1.7A
  → TimeAtTarget = 1920s (RESUMES counting)
  → TailCurrent starts again (0s)

10:38 - V=28.71V, I=1.6A
  → TimeAtTarget = 2220s
  → TailCurrent = 300s → BATTERY FULL!
```

**Key insight:** TimeAtTarget is forgiving (pauses), TailCurrent is strict (resets). This ensures we only stop charging when conditions have been stable for 5 continuous minutes.

---

## Current Override System

### Purpose
Limit charge current (rarely needed, voltage override alone is sufficient).

### How It Works

Very similar to voltage override, but:
- Writes to PDU 88 (Ib_ref_slave) instead of PDU 89
- **Auto-enables voltage override** to maintain slave mode (TriStar requirement)
- Sets voltage to MaxVoltageOverrideVoltage

### Usage
```
Topic: W/.../solarcharger/0/Control/CurrentOverride
Payload: 10.0   (current limit in Amps)
```

### Warning
Less tested than voltage-only override. Testing showed voltage override alone is sufficient for top-charging.

---

## Charge Profile Management System

### Purpose
Switch between seasonal battery charging profiles (summer/winter/custom) by safely programming EEPROM charge parameters. Optimizes battery life and capacity based on temperature and usage patterns.

### Use Cases
- **Summer:** Lower voltage (28.4V), shorter absorption (2h) - prevents overcharging in warm weather
- **Winter:** Higher voltage (28.8V), longer absorption (2.5h) - ensures full charge in cold weather
- **Custom:** User-defined profile for specific battery type or location

### Parameters Programmed
Each profile sets four EEPROM charge parameters:
- **AbsorptionVoltage** (EV_absorp) - Target voltage for absorption stage
- **FloatVoltage** (EV_float) - Voltage for float/maintenance stage
- **AbsorptionTime** (Et_absorp) - Duration of absorption stage
- **FloatCancelVoltage** (EV_float_cancel) - Voltage below which float is cancelled

### How It Works

#### 1. Configure Profile (Optional)
```bash
# Customize the custom profile via D-Bus Settings
dbus -y com.victronenergy.settings /Settings/TristarMPPT/ChargeProfiles/Custom/AbsorptionVoltage SetValue 28.8
dbus -y com.victronenergy.settings /Settings/TristarMPPT/ChargeProfiles/Custom/FloatVoltage SetValue 27.6
dbus -y com.victronenergy.settings /Settings/TristarMPPT/ChargeProfiles/Custom/AbsorptionTime SetValue 9000
dbus -y com.victronenergy.settings /Settings/TristarMPPT/ChargeProfiles/Custom/FloatCancelVoltage SetValue 26.4
```

Summer and winter profiles have fixed defaults and cannot be customized via D-Bus.

#### 2. Apply Profile
```bash
# Via D-Bus
dbus -y com.victronenergy.solarcharger.tristar_0 /Control/ApplyChargeProfile SetValue "winter"

# Via MQTT (Home Assistant)
mosquitto_pub -h <venus-ip> -t "W/<portal-id>/solarcharger/0/Control/ApplyChargeProfile" -m '{"value": "winter"}'
```

#### 3. Driver Executes Safe EEPROM Write Procedure
Following Morningstar's recommended procedure:

**Step 1: Validation**
- Read profile settings from D-Bus
- Validate parameter relationships (float < absorption, etc.)
- Read current EEPROM values
- Compare and filter (only write changed parameters)

**Step 2: Backup**
- Create timestamped backup: `/data/dbus-tristar/eeprom_backups/backup_YYYYMMDD_HHMMSS.json`
- Backup includes all four charge parameters

**Step 3: DISCONNECT**
- Set COIL_DISCONNECT (stop charging)
- Poll for DISCONNECT state (max 5s)
- Ensures controller is not actively regulating

**Step 4: Write EEPROM**
- Write parameters in safe order (lowest voltage first):
  1. FloatCancelVoltage (EV_float_cancel, register 0xE005)
  2. FloatVoltage (EV_float, register 0xE001)
  3. AbsorptionVoltage (EV_absorp, register 0xE000)
  4. AbsorptionTime (Et_absorp, register 0xE002)
- Automatic voltage scaling (12V→24V→48V conversion)
- 200ms delay between writes

**Step 5: Verify**
- Read back all written parameters
- Convert from 12V-equivalent to actual voltage
- Tolerance: ±0.1V for voltages, exact match for time
- Raises exception if verification fails

**Step 6: Reset Controller**
- Write COIL_RESET_CTRL (Morningstar recommended)
- Controller reboots (connection closes - expected)
- Smart reconnect with polling (typical 0.5-1.0s)

**Step 7: Verify Normal Operation**
- Check charge state (should exit DISCONNECT)
- Update active EEPROM display paths
- Mark operation as successful

### Thread Safety
- Main update loop **paused** during entire operation
- Dedicated Modbus client created for EEPROM writes
- Prevents collision with regular polling
- Main loop resumes in finally block (even on error)

### Voltage Scaling (Critical)
EEPROM stores **12V-equivalent** values. Driver automatically detects system voltage from V_PU:
- **V_PU < 100:** 12V system (scale = 1×)
- **V_PU < 200:** 24V system (scale = 2×)
- **V_PU ≥ 200:** 48V system (scale = 4×)

**Example:** Writing 28.6V on 24V system:
```python
voltage_12v = 28.6 / 2 = 14.3V               # Convert to 12V-equivalent
raw_value = round(14.3 / (v_pu * 2^-15))     # Scale to register value
# Write raw_value to EEPROM
# Read back: 14.3V × 2 = 28.6V                # Convert back to system voltage
```

This matches MS View behavior and ensures exact values (e.g., 26.2V reads back as 26.2V, not 26.19V).

### Monitoring

#### Status
```bash
# Check operation status
dbus -y com.victronenergy.solarcharger.tristar_0 /Custom/ChargeProfile/ApplyStatus GetValue
# Returns: "idle", "validating", "disconnecting", "writing", "resetting", "success", "failed"

# Check progress
dbus -y com.victronenergy.solarcharger.tristar_0 /Custom/ChargeProfile/ProgressPercent GetValue
# Returns: 0-100

# Check for errors
dbus -y com.victronenergy.solarcharger.tristar_0 /Custom/ChargeProfile/LastError GetValue

# Check what was last applied
dbus -y com.victronenergy.solarcharger.tristar_0 /Custom/ChargeProfile/LastApplied GetValue
# Returns: "winter at 2026-03-26 20:45:48"
```

#### Active EEPROM Values
```bash
# Check what's actually programmed in the controller
dbus -y com.victronenergy.solarcharger.tristar_0 /Custom/EEPROM/AbsorptionVoltage GetValue
dbus -y com.victronenergy.solarcharger.tristar_0 /Custom/EEPROM/FloatVoltage GetValue
dbus -y com.victronenergy.solarcharger.tristar_0 /Custom/EEPROM/AbsorptionTime GetValue
dbus -y com.victronenergy.solarcharger.tristar_0 /Custom/EEPROM/FloatCancelVoltage GetValue
```

These values update automatically after successful profile apply.

### Safety Features
1. **Parameter validation** - Ensures float < absorption, values in safe ranges
2. **DISCONNECT before writes** - Controller not actively regulating
3. **Backups** - Automatic timestamped backup before changes
4. **Verification** - Read-after-write with tolerance checking
5. **Thread safety** - Main loop paused, no Modbus collisions
6. **Voltage limits** - Enforced in Settings (26.0-32.0V absorption, 24.0-30.0V float)
7. **Smart retry** - Control path resets to '' after each operation, allows immediate retry
8. **Status tracking** - ApplyStatus prevents concurrent operations

### Typical Operation Time
- **No changes:** < 1 second (validation only)
- **With EEPROM writes:** 10-15 seconds
  - Validation: 1s
  - DISCONNECT: 1s
  - Write 4 parameters: 2s
  - Verify: 1s
  - Reset + reconnect: 5-8s
  - Final verification: 1s

### Error Handling
If operation fails:
- Status set to "failed"
- Error message available in LastError path
- Controller attempts to re-enable charging (clear DISCONNECT)
- Main loop resumes (driver continues normal operation)
- User can retry after fixing issue (status resets to "idle" on next attempt)

### Home Assistant Integration Example
```yaml
# Seasonal automation
automation:
  - alias: "Apply Winter Charge Profile"
    trigger:
      - platform: time
        at: "00:00:00"
    condition:
      - condition: template
        value_template: "{{ now().month in [11, 12, 1, 2, 3] }}"  # Nov-Mar
    action:
      - service: mqtt.publish
        data:
          topic: "W/<portal-id>/solarcharger/0/Control/ApplyChargeProfile"
          payload: '{"value": "winter"}'

  - alias: "Apply Summer Charge Profile"
    trigger:
      - platform: time
        at: "00:00:00"
    condition:
      - condition: template
        value_template: "{{ now().month in [4, 5, 6, 7, 8, 9, 10] }}"  # Apr-Oct
    action:
      - service: mqtt.publish
        data:
          topic: "W/<portal-id>/solarcharger/0/Control/ApplyChargeProfile"
          payload: '{"value": "summer"}'
```

---

## Automatic Battery Full Detection

### Algorithm

Battery is considered "full" when **all** conditions are met:

1. **Voltage at target:** `v_battery >= target_voltage`
2. **Low current:** `i_charge < BatteryFullCurrent` (e.g., 2.0A)
3. **Excess power (if enabled):** `excess_power > ExcessPowerThreshold` OR threshold = -1
4. **Sustained:** Condition held for `TailCurrentTime` seconds (e.g., 300s)

### Excess Power Check

**Purpose:** Only stop charging if there's excess solar power available. Don't stop if battery acceptance is low due to lack of sun.

```python
excess_power = (v_pv * i_pv) - (v_battery * i_charge)

# Check passes if:
# - Threshold is -1 (disabled), OR
# - excess_power > 0
check_excess_power = (threshold == -1) or (excess_power > 0)
```

**Example:**
- Solar input: 28V × 8A = 224W
- Battery charge: 28.7V × 2A = 57W
- Excess: 224 - 57 = 167W > threshold (100W) ✓

If excess < threshold, don't stop (battery might accept more if sun was stronger).

### Monitoring Tail Current

```
/Custom/VoltageOverride/TailCurrentTimer = 0-300  (seconds)
```

When timer reaches TailCurrentTime setting → **Battery full**, override disables.

---

## Nightly Reset Logic

### Purpose
Prevent stuck charging sessions (e.g., if battery never reaches tail current).

### When
Every night at `NightlyResetHour` (default: 03:00 local time).

### What It Does

```python
if local_hour == reset_hour and 0 <= local_minute < 5:
    if not nightly_reset_done:
        # 1. Disable voltage override
        write_holding_register(89, -1)
        pending_voltage_override = None
        voltage_override_active = False
        stop_reason = "NightlyReset"

        # 2. Reset cumulative time counter
        time_above_target_accumulated = 0
        override_start_time = None
        tail_current_start_time = None

        # 3. Reset TriStar comm server (clears any stale state)
        write_coil(COIL_RESET_COMM, True)

        nightly_reset_done = True

elif local_hour != reset_hour:
    nightly_reset_done = False  # Reset flag for next night
```

### Why 03:00?
- Battery is not charging (no sun)
- Unlikely to interfere with user activity
- Configurable via `/Settings/TristarMPPT/NightlyResetHour`

---

## Daily History & State Persistence

### State File
Location: `/data/dbus-tristar/state.json`

### Structure
```json
{
  "current_date": "2026-03-15",
  "daily_register_has_reset": false,
  "total_yield_kwh": 266.11,
  "today": {
    "date": "2026-03-15",
    "yield_kwh": 0.537,
    "max_power_w": 201,
    "max_voltage": 28.55,
    "min_voltage": 27.82,
    "max_current": 6.9,
    "time_bulk_s": 1234,
    "time_absorption_s": 567,
    "time_float_s": 890
  },
  "history": [
    {
      "date": "2026-03-14",
      "yield_kwh": 0.69,
      "max_power_w": 182,
      ...
    },
    ...
  ],
  "lifetime": {
    "max_voltage": 29.1,
    "min_voltage": 24.5,
    "max_power_w": 350,
    "max_current": 12.5
  }
}
```

### Daily Register Reset Detection

**Problem:** TriStar's daily register (REG_WHC_DAILY) is frozen from midnight until sunrise.

**Solution:** Track reset state with flag.

```python
# At midnight (local time):
daily_register_has_reset = False  # Register is now frozen

# At sunrise - detect actual reset:
if current_daily_wh < last_daily_register_value:
    # Register decreased = reset happened!
    daily_register_has_reset = True
elif current_daily_wh > 0 and last_daily_register_value == 0:
    # Edge case: No charging yesterday (was 0, now > 0)
    daily_register_has_reset = True

# Use appropriate value:
if daily_register_has_reset:
    daily_kwh = current_daily_wh / 1000.0  # Use Modbus
else:
    daily_kwh = state['today']['yield_kwh']  # Use state.json
```

### Midnight Rollover

**Trigger:** Local date changes (checked every update cycle).

```python
if local_date != state['current_date']:
    # 1. Save today's final values to history
    history.insert(0, {
        'date': state['current_date'],
        'yield_kwh': state['today']['yield_kwh'],
        'max_power_w': state['today']['max_power_w'],
        ...
    })

    # 2. Add today's yield to lifetime total
    total_yield_kwh += state['today']['yield_kwh']

    # 3. Keep only 30 days of history (Day 1-30, plus Day 0 = 31 total)
    history = history[:30]

    # 4. Reset today's values
    state['today'] = {
        'date': local_date,
        'yield_kwh': 0.0,
        'max_power_w': 0,
        'max_voltage': 0.0,
        'min_voltage': 999.0,
        ...
    }

    # 5. Set flag to False (register is frozen)
    daily_register_has_reset = False

    # 6. Update current date
    state['current_date'] = local_date

    # 7. Save state.json immediately
    save_state()
```

### Periodic Save

State is saved:
- Every `StateSaveInterval` seconds (default: 300s = 5 min)
- Immediately at midnight rollover
- Immediately when important changes occur

---

## Configuration

### CONFIG Dictionary (dbus_tristar.py)

```python
CONFIG = {
    # Connection
    'default_ip': '192.168.2.103',
    'default_modbus_port': 502,
    'default_slave_id': 1,
    'default_device_instance': 0,
    'default_poll_interval_ms': 5000,

    # Timing
    'state_save_interval_sec': 300,
    'watchdog_timeout_sec': 180,
    'nightly_reset_hour': 3,

    # Voltage override
    'excess_power_threshold': 100,
    'max_voltage_override_voltage': 28.7,
    'max_voltage_override_time': 7200,
    'battery_full_current': 2.0,
    'tail_current_time': 300,

    # Device
    'custom_name': 'TriStar MPPT 60',
}
```

All values can be overridden via `/Settings/TristarMPPT/...` paths (persistent).

---

## Modbus Register Reference

### Key Registers Used

#### Input Registers (Read-Only)
```
REG_V_PU = 0                   # Voltage scaling factor (v_pu)
REG_I_PU = 2                   # Current scaling factor (i_pu)
REG_VER_SW = 4                 # Software version
REG_V_BAT = 24                 # Battery voltage
REG_I_CC = 28                  # Charge current
REG_V_PV = 27                  # PV array voltage
REG_I_PV = 29                  # PV array current
REG_T_BAT = 37                 # Battery temperature
REG_I_CC_1M = 39               # Charge current (1-min average)
REG_CHARGE_STATE = 50          # Charge state (0-9)
REG_V_TARGET = 51              # Target regulation voltage
REG_POUT = 58                  # Output power
REG_V_BAT_MIN = 64             # Min battery voltage (daily)
REG_V_BAT_MAX = 65             # Max battery voltage (daily)
REG_V_PV_MAX = 66              # Max PV voltage (daily)
REG_AHC_DAILY = 67             # Ah charge daily
REG_WHC_DAILY = 68             # Wh charge daily
REG_POUT_MAX_DAILY = 70        # Max power (daily)
REG_T_ABS = 77                 # Time in absorption
REG_T_EQ = 78                  # Time in equalize
REG_T_FLOAT = 79               # Time in float
REG_FLAGS = 91                 # Alarm/fault flags
```

#### Holding Registers (Read/Write)
```
PDU 88 = Ib_ref_slave          # Current override (slave mode)
PDU 89 = vb_ref_slave          # Voltage override (slave mode) ← PRIMARY
PDU 90 = va_ref_fixed          # Array voltage fixed (disables MPPT)
PDU 91 = va_ref_fixed_pct      # Array voltage fixed percent
```

**Note:** PDU address = Logical address - 1

#### EEPROM Registers (Input, Read-Only)
```
0xE000 = EV_absorp             # Absorption voltage
0xE007 = EV_eq                 # Equalize voltage
0xE00D = EV_tempcomp           # Temperature compensation
0xE010 = Evb_ref_lim           # Max regulation voltage limit
0xE086 = EkWhc_r               # kWh charge resetable
0xE087 = EkWhc_t               # kWh charge total (lifetime)
```

#### Coil Registers (Read/Write Boolean)
```
COIL_RESET_CONTROL = 0         # Reset controller
COIL_RESET_COMM = 1            # Reset comm server
COIL_DISCONNECT = 2            # Disconnect charger
COIL_EQUALIZE = 5              # Trigger equalize
```

### Scaling Formulas

```python
# Voltage (V)
v_pu = read_input_register(0) / 32768.0 * 96.667
voltage = register_value * v_pu / 32768.0

# Current (A)
i_pu = read_input_register(2) / 32768.0 * 79.16
current = register_value * i_pu / 32768.0

# Temperature (°C)
temp = register_value / 10.0

# Power (W)
power = register_value * v_pu * i_pu / 131072.0

# Override register conversion
voltage_register = int(voltage * 182.04)  # 24V system
current_register = int(current * 409.6)
```

---

## Troubleshooting

### Voltage Override Not Working

1. **Check safety limit:**
   ```
   /Settings/TristarMPPT/MaxVoltageOverrideVoltage >= target
   ```

2. **Verify register write:**
   ```
   /Custom/VoltageOverride/RegisterReadback should match CurrentVoltage
   ```

3. **Check TriStar charge state:**
   ```
   /Custom/TriStarChargeState should = 9 (SLAVE) when active
   ```

### Battery Full Detection Not Triggering

1. **Check tail current:**
   ```
   /Dc/0/Current < BatteryFullCurrent?
   ```

2. **Check timer:**
   ```
   /Custom/VoltageOverride/TailCurrentTimer should increase to TailCurrentTime
   ```

3. **Check excess power (if enabled):**
   ```
   /Custom/VoltageOverride/ExcessPower > ExcessPowerThreshold?

   # Or disable check:
   /Settings/TristarMPPT/ExcessPowerThreshold = -1
   ```

### Daily Yield Shows 0

Check if register has reset:
```
/Custom/Daily/ChargeWh shows actual Modbus value
```

If non-zero but /History/Daily/0/Yield = 0:
- Flag issue: Driver thinks register is frozen
- Check logs for "daily_register_has_reset" messages

### Midnight Spike in /Yield/System

Fixed in v2.24. If still present:
- Check logs for "Large /Yield/System change" warnings
- Indicates timing issue in rollover or reset detection

---

## Example Workflows

### Manual Top-Charge Session

```bash
# 1. Enable voltage override to 28.7V
dbus -y com.victronenergy.solarcharger.tristar_0 \
  /Control/VoltageOverride SetValue 28.7

# 2. Monitor progress
watch 'dbus -y com.victronenergy.solarcharger.tristar_0 /Custom/VoltageOverride/TimeAtTargetVoltage GetValue'

# 3. Check tail current timer
dbus -y com.victronenergy.solarcharger.tristar_0 \
  /Custom/VoltageOverride/TailCurrentTimer GetValue

# 4. Wait for automatic stop (BatteryFull)
# OR manually disable:
dbus -y com.victronenergy.solarcharger.tristar_0 \
  /Control/VoltageOverride SetValue 0
```

### Adjust Tail Current Settings

```bash
# Set tail current threshold to 1.5A
dbus -y com.victronenergy.settings \
  /Settings/TristarMPPT/BatteryFullCurrent SetValue 1.5

# Set sustained time to 10 minutes
dbus -y com.victronenergy.settings \
  /Settings/TristarMPPT/TailCurrentTime SetValue 600
```

### Change Nightly Reset Time

```bash
# Reset at 02:00 instead of 03:00
dbus -y com.victronenergy.settings \
  /Settings/TristarMPPT/NightlyResetHour SetValue 2
```

---

## Version History

**v2.24** (Current)
- Fix: Midnight spike in /Yield/System (recalculate daily_kwh after flag changes)
- Fix: Sunrise spike detection (don't set flag prematurely on charging detection)
- Add: Comprehensive logging for spike debugging
- Add: EEPROM lifetime kWh counters exposed
- Add: Daily register tracking for debugging

**v2.23**
- Add: Cumulative time tracking (Home Assistant style)
- Add: Nightly reset at configurable hour
- Fix: Voltage override register addressing (PDU 89, not 90)

**v2.22**
- Add: Tail current detection for battery full
- Add: Excess power threshold check
- Add: Automatic override stopping conditions

---

## Support

**Issues & Questions:**
- Check logs: `/var/log/dbus-tristar/current`
- State file: `/data/dbus-tristar/state.json`
- Driver code: `/data/dbus-tristar/dbus_tristar.py`

**Key Log Messages:**
```
"Voltage override enabled: X.XXV"
"Tail current detected: V=X.XX, I=X.XX"
"Battery full detected: voltage at X.XX, tail current X.XX for XXXs"
"Detected REG_WHC_DAILY reset: XXX → XXX Wh (sun came up)"
"Performing midnight rollover"
"Nightly reset at XX:00"
```

---

**End of Documentation**
