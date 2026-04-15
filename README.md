# Weintek iR-ETN Configuration Tool

A cross-platform (Windows & Linux) terminal-based replacement for Weintek's **EasyRemoteIO** software. Configure and monitor your iR-ETN remote I/O system entirely over Modbus TCP/IP — no Windows required.

---

## Requirements

- Python 3.7 or newer
- Network access to your iR-ETN coupler

### Python dependencies

The script will **automatically install** the correct versions of all dependencies when first run. No manual pip install is needed.

If you prefer to install manually:

```bash
pip install pymodbus==3.5.4 rich
```

> **Important:** This tool requires **pymodbus exactly 3.5.4**. Newer versions changed the API in breaking ways. The auto-install will force-reinstall the correct version if a different one is detected.

---

## Usage

```bash
python weintek_etn_tool.py
```

You will be prompted for the iR-ETN IP address (default: `192.168.0.212`) and Modbus TCP port (default: `502`).

---

## Features

### Auto-Discovery
On connect, the tool reads the iR-ETN iBus information registers to automatically detect all connected modules. For each module it identifies:
- Module name and type (digital, analog, temperature)
- Number of DI / DO / AI / AO channels
- Modbus parameter base address
- Sequential I/O address mapping

Coupler information (firmware version, hardware version, IP address, power consumption) is also read and displayed.

### Main Menu Options

| Option | Description |
|--------|-------------|
| `1` | Show I/O address map — lists the exact Modbus bit/word addresses for every module's inputs and outputs |
| `2` | Read live I/O values — current digital states and analog raw values |
| `3` | Configure a module — interactive parameter editor |
| `4` | Raw register read/write — low-level Modbus access tool |
| `5` | Rescan — re-reads all iBus registers and refreshes the module list |
| `Q` | Quit and disconnect |

---

## Module Configuration

### Analog Modules (iR-AI04-VI, iR-AM06-VI, iR-AQ04-VI)

The following parameters can be read and written interactively:

**Analog Inputs**
| Parameter | Description |
|-----------|-------------|
| Input Mode | Signal type per channel (see table below) |
| Scale Range Upper/Lower | Engineering unit limits (default ±32000) |
| Filter Frame Size | Averaging filter for signal stability (default 5) |
| Conversion Time | Sample rate: `0`=2ms (default), `6`=60ms (50/60Hz filter), `1`=500µs (fast, 1 channel only) |

**Analog Outputs**
| Parameter | Description |
|-----------|-------------|
| Output Mode | Signal type per channel (see table below) |
| Scale Range Upper/Lower | Engineering unit limits |
| Update Time | Soft-start slew rate in units of 10ms (0 = disabled, max 3200 = 32s) |

#### Analog Mode Values

| Value | Input Mode | Output Mode |
|-------|-----------|-------------|
| `0` | Channel closed | Channel closed |
| `1` | ±10V *(default)* | ±10V *(default)* |
| `2` | ±5V | ±5V |
| `3` | 1–5V | 1–5V |
| `4` | ±20mA | ±20mA |
| `5` | 4–20mA | 4–20mA |

> **Important:** When switching modes, scale range limits reset to their defaults. Always set the mode *before* configuring the scale range.

### Digital Modules (iR-DM16-P, iR-DM16-N, iR-DQ16-P, iR-DQ16-N, iR-DQ08-R, iR-DI16-K)

- View current state of all digital inputs and outputs
- Toggle individual digital output channels ON/OFF

---

## Modbus Address Reference

### I/O Data Registers

| Data | Address (dec) | Read FC | Write FC | Notes |
|------|--------------|---------|----------|-------|
| Digital Input (bit) | 0 – 511 | FC02 | — | Read only |
| Digital Output (bit) | 0 – 511 | FC01 | FC05 (single), FC15 (multiple) | |
| Digital Input (word) | 800 – 863 | FC03, FC23 | — | Read only |
| Digital Output (word) | 864 – 927 | FC03, FC23 | FC06 (single), FC16 (multiple) | |
| Analog Input | 0 – 255 | FC03, FC04, FC23 | — | Sequential, one word per channel |
| Analog Output | 256 – 511 | FC03, FC23 | FC06 (single), FC16 (multiple) | |

#### Function Code Reference

| FC | Name | Description |
|----|------|-------------|
| FC01 | Read Coils | Read digital output (DO) bit states |
| FC02 | Read Discrete Inputs | Read digital input (DI) bit states |
| FC03 | Read Holding Registers | Read AI, AO, or DO word values; also module parameters |
| FC04 | Read Input Registers | Alternate read for analog input values |
| FC05 | Write Single Coil | Set a single digital output bit ON or OFF |
| FC06 | Write Single Register | Write a single analog output or parameter register |
| FC15 | Write Multiple Coils | Set multiple digital output bits in one request |
| FC16 | Write Multiple Registers | Write multiple analog output or parameter registers |
| FC23 | Read/Write Multiple Registers | Combined read and write in a single request |

### Module Parameter Registers

Each module has a 500-word parameter block:

```
Base address = 20000 + (slot_number - 1) × 500
```

| Slot | Parameter Base |
|------|---------------|
| 1 | 20000 |
| 2 | 20500 |
| 3 | 21000 |
| 4 | 21500 |
| … | … |
| 16 | 27500 |

**Key parameter offsets within each module block:**

| Offset | Parameter |
|--------|-----------|
| 0–3 | AO Channel 0–3 Output Mode |
| 4–7 | AO Channel 0–3 Scale Upper Limit |
| 8–11 | AO Channel 0–3 Scale Lower Limit |
| 12–15 | AO Channel 0–3 Update Time |
| 16 | Error Code |
| 19 | AI Conversion Time |
| 20–23 | AI Channel 0–3 Input Mode |
| 24–27 | AI Channel 0–3 Scale Upper Limit |
| 28–31 | AI Channel 0–3 Scale Lower Limit |
| 32–35 | AI Channel 0–3 Filter Frame Size |

### iBus Information Registers

| Address | Description |
|---------|-------------|
| 10000 | Slot 0 product code (iR-ETN coupler) |
| 10001–10016 | Slot 1–16 module product codes |
| 10033 | Number of modules connected |
| 10035 | Total digital input points |
| 10036 | Total digital output points |
| 10037 | Total analog input channels |
| 10038 | Total analog output channels |

### Module Product Codes

| Code | Module | DI | DO | AI | AO |
|------|--------|----|----|----|----|
| `0x0154` | iR-DI16-K | 16 | 0 | 0 | 0 |
| `0x0351` | iR-DM16-P | 8 | 8 | 0 | 0 |
| `0x0352` | iR-DM16-N | 8 | 8 | 0 | 0 |
| `0x0251` | iR-DQ16-P | 0 | 16 | 0 | 0 |
| `0x0252` | iR-DQ16-N | 0 | 16 | 0 | 0 |
| `0x0243` | iR-DQ08-R | 0 | 8 | 0 | 0 |
| `0x0425` | iR-AI04-VI | 0 | 0 | 4 | 0 |
| `0x0525` | iR-AQ04-VI | 0 | 0 | 0 | 4 |
| `0x0635` | iR-AM06-VI | 0 | 0 | 4 | 2 |
| `0x0426` | iR-AI04-TR | 0 | 0 | 4 | 0 |

---

## Raw Register Tool

Select option `4` from the main menu to access the raw register tool. This allows you to read or write any Modbus holding register directly — useful for diagnostics or accessing registers not covered by the module menus (e.g. life guarding, error modes, TCP/IP settings).

All write operations require confirmation before being sent.

---

## Analog Data Format

Raw analog values are 16-bit signed integers. Default scale ranges by mode:

| Mode | Lower Limit | Upper Limit |
|------|------------|-------------|
| ±10V | -32000 | 32000 |
| ±5V | -32000 | 32000 |
| 1–5V | 0 | 32000 |
| ±20mA | -32000 | 32000 |
| 4–20mA | 0 | 32000 |

---

## Default iR-ETN Network Settings

| Parameter | Default |
|-----------|---------|
| IP Address | `192.168.11.199` |
| Subnet Mask | `255.255.255.0` |
| Modbus TCP Port | `502` |

To reset the coupler to factory defaults, hold the reset button for more than 2 seconds after the unit is running (wait until the ENET ERR LED blinks).

---

## Limitations & Notes

- Temperature module (iR-AI04-TR) parameter configuration (thermocouple type, unit) is not yet implemented in this tool. Raw values can still be read via the live I/O view or the raw register tool.
- IP address changes via Modbus (registers 1003–1004) require a warm reset to take effect. Write `0x5257` to register `6000` to trigger a warm reset.
- This tool uses **0-based Modbus addressing** consistent with pymodbus. If cross-referencing with documentation that uses 1-based addressing, subtract 1 from the address shown in the docs.

---

## License

MIT — free to use, modify, and distribute.
