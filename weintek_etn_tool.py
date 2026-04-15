#!/usr/bin/env python3
"""
Weintek iR-ETN Remote I/O Configuration Tool
Cross-platform (Windows/Linux) replacement for EasyRemoteIO
Requires: pip install pymodbus rich
"""

import sys
import time
from typing import Optional

try:
    from pymodbus.client import ModbusTcpClient
    from pymodbus.exceptions import ModbusException
except ImportError:
    print("ERROR: pymodbus not installed. Run: pip install pymodbus")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.text import Text
    from rich import box
    from rich.columns import Columns
    from rich.layout import Layout
    from rich.live import Live
except ImportError:
    print("ERROR: rich not installed. Run: pip install rich")
    sys.exit(1)

console = Console()

# ─── Product Code Lookup ────────────────────────────────────────────────────
PRODUCT_CODES = {
    0x0154: {"name": "iR-DI16-K",  "type": "digital", "di": 16, "do": 0,  "ai": 0, "ao": 0},
    0x0351: {"name": "iR-DM16-P",  "type": "digital", "di": 8,  "do": 8,  "ai": 0, "ao": 0},
    0x0352: {"name": "iR-DM16-N",  "type": "digital", "di": 8,  "do": 8,  "ai": 0, "ao": 0},
    0x0251: {"name": "iR-DQ16-P",  "type": "digital", "di": 0,  "do": 16, "ai": 0, "ao": 0},
    0x0252: {"name": "iR-DQ16-N",  "type": "digital", "di": 0,  "do": 16, "ai": 0, "ao": 0},
    0x0243: {"name": "iR-DQ08-R",  "type": "digital", "di": 0,  "do": 8,  "ai": 0, "ao": 0},
    0x0425: {"name": "iR-AI04-VI", "type": "analog",  "di": 0,  "do": 0,  "ai": 4, "ao": 0},
    0x0525: {"name": "iR-AQ04-VI", "type": "analog",  "di": 0,  "do": 0,  "ai": 0, "ao": 4},
    0x0635: {"name": "iR-AM06-VI", "type": "analog",  "di": 0,  "do": 0,  "ai": 4, "ao": 2},
    0x0426: {"name": "iR-AI04-TR", "type": "temp",    "di": 0,  "do": 0,  "ai": 4, "ao": 0},
    0x0702: {"name": "iR-ETN",     "type": "coupler", "di": 0,  "do": 0,  "ai": 0, "ao": 0},
    0x0A73: {"name": "iR-ETN40R",  "type": "coupler", "di": 0,  "do": 0,  "ai": 0, "ao": 0},
}

# Analog I/O mode tables (value -> label)
ANALOG_INPUT_MODES = {
    0: "Closed",
    1: "±10V (default)",
    2: "±5V",
    3: "1-5V",
    4: "±20mA",
    5: "4-20mA",
}
ANALOG_OUTPUT_MODES = {
    0: "Closed",
    1: "±10V (default)",
    2: "±5V",
    3: "1-5V",
    4: "±20mA",
    5: "4-20mA",
}

# Module register offsets (relative within 500-word block)
# For iR-AI04-VI / iR-AM06-VI / iR-AQ04-VI
REG_AO_MODE      = [0, 1, 2, 3]        # Output mode ch0-3
REG_AO_UPP       = [4, 5, 6, 7]        # AO upper scale limit ch0-3
REG_AO_LOW       = [8, 9, 10, 11]      # AO lower scale limit ch0-3
REG_AO_UPDATE    = [12, 13, 14, 15]    # AO update time ch0-3
REG_ERROR_CODE   = 16
REG_CONV_TIME    = 19                  # AI conversion time
REG_AI_MODE      = [20, 21, 22, 23]    # Input mode ch0-3
REG_AI_UPP       = [24, 25, 26, 27]    # AI upper scale limit ch0-3
REG_AI_LOW       = [28, 29, 30, 31]    # AI lower scale limit ch0-3
REG_FILTER_SIZE  = [32, 33, 34, 35]    # AI filter frame size ch0-3

# iBus information registers
IBUS_SLOT_BASE   = 10000   # 10000-10016 = slot 0-16 product codes
IBUS_NUM_MOD     = 10033
IBUS_NUM_DI      = 10035
IBUS_NUM_DO      = 10036
IBUS_NUM_AI      = 10037
IBUS_NUM_AO      = 10038

# Module information base (100 words each)
MOD_INFO_BASE    = 30000
MOD_INFO_SIZE    = 100
# Module register base (500 words each)
MOD_REG_BASE     = 20000
MOD_REG_SIZE     = 500


# ─── Modbus helpers ──────────────────────────────────────────────────────────
SLAVE_ID = 1  # iR-ETN Modbus slave ID


def read_regs(client: ModbusTcpClient, addr: int, count: int = 1) -> Optional[list]:
    """Read holding registers. Returns list of values or None on error."""
    try:
        resp = client.read_holding_registers(addr, count, slave=SLAVE_ID)
        if resp.isError():
            return None
        return resp.registers
    except Exception:
        return None


def write_reg(client: ModbusTcpClient, addr: int, value: int) -> bool:
    """Write single holding register. Returns True on success."""
    try:
        resp = client.write_register(addr, value, slave=SLAVE_ID)
        return not resp.isError()
    except Exception:
        return False


def signed16(val: int) -> int:
    """Convert unsigned 16-bit register value to signed."""
    return val - 65536 if val >= 32768 else val


# ─── Discovery ───────────────────────────────────────────────────────────────
def discover_system(client: ModbusTcpClient) -> dict:
    """Read all iBus info and build system map."""
    system = {"coupler": {}, "modules": []}

    # Coupler device info
    vendor = read_regs(client, 3000, 4)
    prod_code = read_regs(client, 3004, 1)
    fw = read_regs(client, 3005, 1)
    hw = read_regs(client, 3006, 1)
    pwr = read_regs(client, 3007, 1)
    ip_raw = read_regs(client, 1003, 2)

    system["coupler"] = {
        "vendor": bytes([v >> 8 for v in vendor] + [v & 0xFF for v in vendor]).decode("ascii", errors="?").strip("\x00") if vendor else "?",
        "product_code": prod_code[0] if prod_code else 0,
        "fw": f"{(fw[0]>>8)&0xFF}.{(fw[0]>>4)&0xF}.{fw[0]&0xF}" if fw else "?",
        "hw": f"{(hw[0]>>8)&0xFF}.{(hw[0]>>4)&0xF}.{hw[0]&0xF}" if hw else "?",
        "power_mw": pwr[0] if pwr else 0,
        "ip": f"{(ip_raw[0]>>8)&0xFF}.{ip_raw[0]&0xFF}.{(ip_raw[1]>>8)&0xFF}.{ip_raw[1]&0xFF}" if ip_raw else "?",
    }

    # Read slot product codes
    slots_raw = read_regs(client, IBUS_SLOT_BASE, 17)  # slot 0-16
    num_mod_r = read_regs(client, IBUS_NUM_MOD, 1)
    num_mod = num_mod_r[0] if num_mod_r else 0

    # Track address counters for IO mapping
    di_bit = 0
    do_bit = 0
    ai_word = 0
    ao_word = 256  # AO starts at offset 256 in analog space

    for slot_idx in range(1, 17):
        if not slots_raw or slot_idx >= len(slots_raw):
            break
        code = slots_raw[slot_idx]
        if code == 0 or code == 0xFFFF:
            continue

        info = PRODUCT_CODES.get(code, {"name": f"Unknown(0x{code:04X})", "type": "unknown",
                                        "di": 0, "do": 0, "ai": 0, "ao": 0})

        # Module parameter register base
        param_base = MOD_REG_BASE + (slot_idx - 1) * MOD_REG_SIZE
        # Module information register base
        mod_info_base = MOD_INFO_BASE + (slot_idx - 1) * MOD_INFO_SIZE

        mod = {
            "slot": slot_idx,
            "code": code,
            "name": info["name"],
            "type": info["type"],
            "di": info["di"],
            "do": info["do"],
            "ai": info["ai"],
            "ao": info["ao"],
            "param_base": param_base,
            "mod_info_base": mod_info_base,
            # IO address mapping
            "di_start": di_bit if info["di"] > 0 else None,
            "do_start": do_bit if info["do"] > 0 else None,
            "ai_start": ai_word if info["ai"] > 0 else None,
            "ao_start": ao_word if info["ao"] > 0 else None,
        }

        di_bit  += info["di"]
        do_bit  += info["do"]
        ai_word += info["ai"]
        ao_word += info["ao"]

        system["modules"].append(mod)

    return system


# ─── Display helpers ─────────────────────────────────────────────────────────
def print_system_overview(system: dict):
    c = system["coupler"]
    name = PRODUCT_CODES.get(c["product_code"], {}).get("name", "iR-ETN")
    console.print(Panel(
        f"[bold cyan]{name}[/bold cyan]  FW:{c['fw']}  HW:{c['hw']}  IP:{c['ip']}  Power:{c['power_mw']}mW",
        title="[bold white]Coupler Information", border_style="cyan"
    ))

    tbl = Table(title="Detected Modules", box=box.ROUNDED, show_lines=True)
    tbl.add_column("Slot", style="bold yellow", justify="center")
    tbl.add_column("Module", style="bold white")
    tbl.add_column("Type", style="cyan")
    tbl.add_column("DI", justify="center")
    tbl.add_column("DO", justify="center")
    tbl.add_column("AI", justify="center")
    tbl.add_column("AO", justify="center")
    tbl.add_column("Param Base Addr", style="dim")

    for m in system["modules"]:
        typ_color = {"digital": "green", "analog": "magenta", "temp": "yellow", "unknown": "red"}.get(m["type"], "white")
        tbl.add_row(
            str(m["slot"]),
            m["name"],
            f"[{typ_color}]{m['type']}[/{typ_color}]",
            str(m["di"]) if m["di"] else "-",
            str(m["do"]) if m["do"] else "-",
            str(m["ai"]) if m["ai"] else "-",
            str(m["ao"]) if m["ao"] else "-",
            str(m["param_base"]),
        )
    console.print(tbl)


def print_io_address_map(system: dict):
    tbl = Table(title="I/O Address Map (Modbus)", box=box.SIMPLE_HEAVY, show_lines=True)
    tbl.add_column("Slot", justify="center", style="yellow")
    tbl.add_column("Module")
    tbl.add_column("DI bits (dec)")
    tbl.add_column("DO bits (dec)")
    tbl.add_column("AI words (dec)")
    tbl.add_column("AO words (dec)")

    for m in system["modules"]:
        def fmt_range(start, count):
            if start is None or count == 0:
                return "-"
            return f"{start} – {start+count-1}"

        tbl.add_row(
            str(m["slot"]), m["name"],
            fmt_range(m["di_start"], m["di"]),
            fmt_range(m["do_start"], m["do"]),
            fmt_range(m["ai_start"], m["ai"]),
            fmt_range(m["ao_start"], m["ao"]),
        )
    console.print(tbl)


def read_live_io(client: ModbusTcpClient, system: dict):
    """Read and display current IO values."""
    console.print(Panel("[bold]Reading live I/O values...[/bold]", border_style="green"))

    for m in system["modules"]:
        if m["type"] == "digital":
            lines = []
            if m["di"] > 0 and m["di_start"] is not None:
                # Read DI as words from register 800+
                word_addr = 800 + m["di_start"] // 16
                num_words = (m["di"] + 15) // 16
                vals = read_regs(client, word_addr, num_words)
                if vals:
                    bits = 0
                    for i, v in enumerate(vals):
                        bits |= v << (i * 16)
                    di_str = " ".join(f"CH{i}:[bold {'green' if (bits>>i)&1 else 'red'}]{'ON ' if (bits>>i)&1 else 'OFF'}[/]" for i in range(m["di"]))
                    lines.append(f"[cyan]DI:[/cyan] {di_str}")
            if m["do"] > 0 and m["do_start"] is not None:
                word_addr = 864 + m["do_start"] // 16
                num_words = (m["do"] + 15) // 16
                vals = read_regs(client, word_addr, num_words)
                if vals:
                    bits = 0
                    for i, v in enumerate(vals):
                        bits |= v << (i * 16)
                    do_str = " ".join(f"CH{i}:[bold {'green' if (bits>>i)&1 else 'red'}]{'ON ' if (bits>>i)&1 else 'OFF'}[/]" for i in range(m["do"]))
                    lines.append(f"[magenta]DO:[/magenta] {do_str}")
            if lines:
                console.print(Panel("\n".join(lines), title=f"[yellow]Slot {m['slot']} {m['name']}[/yellow]", border_style="dim"))

        elif m["type"] in ("analog", "temp"):
            lines = []
            if m["ai"] > 0 and m["ai_start"] is not None:
                vals = read_regs(client, m["ai_start"], m["ai"])
                if vals:
                    ai_str = "  ".join(f"CH{i}: [bold cyan]{signed16(v)}[/bold cyan]" for i, v in enumerate(vals))
                    lines.append(f"[cyan]AI:[/cyan] {ai_str}")
            if m["ao"] > 0 and m["ao_start"] is not None:
                vals = read_regs(client, m["ao_start"], m["ao"])
                if vals:
                    ao_str = "  ".join(f"CH{i}: [bold magenta]{signed16(v)}[/bold magenta]" for i, v in enumerate(vals))
                    lines.append(f"[magenta]AO:[/magenta] {ao_str}")
            if lines:
                console.print(Panel("\n".join(lines), title=f"[yellow]Slot {m['slot']} {m['name']}[/yellow]", border_style="dim"))


def read_analog_params(client: ModbusTcpClient, mod: dict):
    """Read and display all analog parameters for a module."""
    base = mod["param_base"]
    has_ao = mod["ao"] > 0
    has_ai = mod["ai"] > 0

    tbl = Table(title=f"Slot {mod['slot']} {mod['name']} – Parameters", box=box.ROUNDED, show_lines=True)
    tbl.add_column("Register", style="dim", justify="right")
    tbl.add_column("Parameter", style="bold")
    tbl.add_column("Value", style="cyan", justify="right")
    tbl.add_column("Meaning", style="green")

    def add_row(offset, label, val, modes=None):
        addr = base + offset
        meaning = modes.get(val, str(val)) if modes else str(val)
        tbl.add_row(str(addr), label, str(val), meaning)

    if has_ao:
        for ch in range(mod["ao"]):
            v = read_regs(client, base + REG_AO_MODE[ch], 1)
            add_row(REG_AO_MODE[ch], f"AO Ch{ch} Mode", v[0] if v else "?", ANALOG_OUTPUT_MODES)
        for ch in range(mod["ao"]):
            v = read_regs(client, base + REG_AO_UPP[ch], 1)
            add_row(REG_AO_UPP[ch], f"AO Ch{ch} Scale Upper", signed16(v[0]) if v else "?")
        for ch in range(mod["ao"]):
            v = read_regs(client, base + REG_AO_LOW[ch], 1)
            add_row(REG_AO_LOW[ch], f"AO Ch{ch} Scale Lower", signed16(v[0]) if v else "?")
        for ch in range(mod["ao"]):
            v = read_regs(client, base + REG_AO_UPDATE[ch], 1)
            add_row(REG_AO_UPDATE[ch], f"AO Ch{ch} Update Time (x10ms)", v[0] if v else "?")

    err = read_regs(client, base + REG_ERROR_CODE, 1)
    add_row(REG_ERROR_CODE, "Error Code", err[0] if err else "?")

    if has_ai:
        ct = read_regs(client, base + REG_CONV_TIME, 1)
        add_row(REG_CONV_TIME, "AI Conversion Time", ct[0] if ct else "?")
        for ch in range(mod["ai"]):
            v = read_regs(client, base + REG_AI_MODE[ch], 1)
            add_row(REG_AI_MODE[ch], f"AI Ch{ch} Mode", v[0] if v else "?", ANALOG_INPUT_MODES)
        for ch in range(mod["ai"]):
            v = read_regs(client, base + REG_AI_UPP[ch], 1)
            add_row(REG_AI_UPP[ch], f"AI Ch{ch} Scale Upper", signed16(v[0]) if v else "?")
        for ch in range(mod["ai"]):
            v = read_regs(client, base + REG_AI_LOW[ch], 1)
            add_row(REG_AI_LOW[ch], f"AI Ch{ch} Scale Lower", signed16(v[0]) if v else "?")
        for ch in range(mod["ai"]):
            v = read_regs(client, base + REG_FILTER_SIZE[ch], 1)
            add_row(REG_FILTER_SIZE[ch], f"AI Ch{ch} Filter Frame Size", v[0] if v else "?")

    console.print(tbl)


def configure_analog_module(client: ModbusTcpClient, mod: dict):
    """Interactive configuration of an analog module."""
    while True:
        console.rule(f"[bold yellow]Configure Slot {mod['slot']} – {mod['name']}[/bold yellow]")
        read_analog_params(client, mod)

        console.print("\nWhat would you like to configure?")
        options = []
        if mod["ai"] > 0:
            options.append(("1", "Analog Input mode"))
            options.append(("2", "Analog Input scale range"))
            options.append(("3", "Analog Input filter size"))
            options.append(("4", "Analog Input conversion time"))
        if mod["ao"] > 0:
            options.append(("5", "Analog Output mode"))
            options.append(("6", "Analog Output scale range"))
            options.append(("7", "Analog Output update time"))
        options.append(("R", "Refresh / re-read parameters"))
        options.append(("B", "Back to module list"))

        for k, v in options:
            console.print(f"  [bold cyan]{k}[/bold cyan]  {v}")

        choice = Prompt.ask("Choice").strip().upper()

        base = mod["param_base"]

        if choice == "B":
            break

        elif choice == "R":
            continue

        elif choice == "1" and mod["ai"] > 0:
            ch = int(Prompt.ask(f"Channel (0-{mod['ai']-1})"))
            console.print("Available modes:")
            for k, v in ANALOG_INPUT_MODES.items():
                console.print(f"  [cyan]{k}[/cyan] = {v}")
            val = int(Prompt.ask("Enter mode value"))
            addr = base + REG_AI_MODE[ch]
            if Confirm.ask(f"Write value [bold]{val}[/bold] ({ANALOG_INPUT_MODES.get(val,'?')}) to register [bold]{addr}[/bold]?"):
                ok = write_reg(client, addr, val)
                console.print(f"[{'green' if ok else 'red'}]{'Success' if ok else 'FAILED'}[/]")

        elif choice == "2" and mod["ai"] > 0:
            ch = int(Prompt.ask(f"Channel (0-{mod['ai']-1})"))
            upper = int(Prompt.ask("Upper limit (e.g. 32000)"))
            lower = int(Prompt.ask("Lower limit (e.g. -32000)"))
            u_addr = base + REG_AI_UPP[ch]
            l_addr = base + REG_AI_LOW[ch]
            if Confirm.ask(f"Write upper={upper} to reg {u_addr}, lower={lower} to reg {l_addr}?"):
                ok1 = write_reg(client, u_addr, upper & 0xFFFF)
                ok2 = write_reg(client, l_addr, lower & 0xFFFF)
                console.print(f"Upper: [{'green' if ok1 else 'red'}]{'OK' if ok1 else 'FAIL'}[/]  Lower: [{'green' if ok2 else 'red'}]{'OK' if ok2 else 'FAIL'}[/]")

        elif choice == "3" and mod["ai"] > 0:
            ch = int(Prompt.ask(f"Channel (0-{mod['ai']-1})"))
            size = int(Prompt.ask("Filter frame size (default 5)"))
            addr = base + REG_FILTER_SIZE[ch]
            if Confirm.ask(f"Write {size} to reg {addr}?"):
                ok = write_reg(client, addr, size)
                console.print(f"[{'green' if ok else 'red'}]{'OK' if ok else 'FAIL'}[/]")

        elif choice == "4" and mod["ai"] > 0:
            console.print("Conversion time: 0=2ms(default), 6=60ms(50/60Hz filter), 1=500us(fast, 1ch only)")
            val = int(Prompt.ask("Conversion time value"))
            addr = base + REG_CONV_TIME
            if Confirm.ask(f"Write {val} to reg {addr}?"):
                ok = write_reg(client, addr, val)
                console.print(f"[{'green' if ok else 'red'}]{'OK' if ok else 'FAIL'}[/]")

        elif choice == "5" and mod["ao"] > 0:
            ch = int(Prompt.ask(f"Channel (0-{mod['ao']-1})"))
            console.print("Available modes:")
            for k, v in ANALOG_OUTPUT_MODES.items():
                console.print(f"  [cyan]{k}[/cyan] = {v}")
            val = int(Prompt.ask("Enter mode value"))
            addr = base + REG_AO_MODE[ch]
            if Confirm.ask(f"Write {val} ({ANALOG_OUTPUT_MODES.get(val,'?')}) to reg {addr}?"):
                ok = write_reg(client, addr, val)
                console.print(f"[{'green' if ok else 'red'}]{'OK' if ok else 'FAIL'}[/]")

        elif choice == "6" and mod["ao"] > 0:
            ch = int(Prompt.ask(f"Channel (0-{mod['ao']-1})"))
            upper = int(Prompt.ask("Upper limit"))
            lower = int(Prompt.ask("Lower limit"))
            u_addr = base + REG_AO_UPP[ch]
            l_addr = base + REG_AO_LOW[ch]
            if Confirm.ask(f"Write upper={upper} reg {u_addr}, lower={lower} reg {l_addr}?"):
                ok1 = write_reg(client, u_addr, upper & 0xFFFF)
                ok2 = write_reg(client, l_addr, lower & 0xFFFF)
                console.print(f"Upper: [{'green' if ok1 else 'red'}]{'OK' if ok1 else 'FAIL'}[/]  Lower: [{'green' if ok2 else 'red'}]{'OK' if ok2 else 'FAIL'}[/]")

        elif choice == "7" and mod["ao"] > 0:
            ch = int(Prompt.ask(f"Channel (0-{mod['ao']-1})"))
            t = int(Prompt.ask("Update time (x10ms, 0=disabled, max 3200)"))
            addr = base + REG_AO_UPDATE[ch]
            if Confirm.ask(f"Write {t} to reg {addr}?"):
                ok = write_reg(client, addr, t)
                console.print(f"[{'green' if ok else 'red'}]{'OK' if ok else 'FAIL'}[/]")

        else:
            console.print("[red]Invalid choice.[/red]")

        time.sleep(0.2)


def configure_digital_module(client: ModbusTcpClient, mod: dict):
    """Interactive digital output control."""
    while True:
        console.rule(f"[bold yellow]Slot {mod['slot']} – {mod['name']} (Digital)[/bold yellow]")
        read_live_io(client, {"modules": [mod]})

        console.print("\n  [cyan]1[/cyan]  Toggle/Set a Digital Output")
        console.print("  [cyan]B[/cyan]  Back")

        choice = Prompt.ask("Choice").strip().upper()
        if choice == "B":
            break
        elif choice == "1" and mod["do"] > 0:
            ch = int(Prompt.ask(f"Channel (0-{mod['do']-1})"))
            val = Prompt.ask("Value (0=OFF, 1=ON)")
            bit_addr = (mod["do_start"] or 0) + ch
            if Confirm.ask(f"Write {'ON' if val=='1' else 'OFF'} to DO channel {ch} (bit addr {bit_addr})?"):
                try:
                    resp = client.write_coil(bit_addr, val == "1", slave=SLAVE_ID)
                    ok = not resp.isError()
                except Exception:
                    ok = False
                console.print(f"[{'green' if ok else 'red'}]{'OK' if ok else 'FAIL'}[/]")
        else:
            console.print("[red]Invalid.[/red]")


def raw_register_tool(client: ModbusTcpClient):
    """Low-level read/write tool."""
    while True:
        console.rule("[bold]Raw Modbus Register Tool[/bold]")
        console.print("  [cyan]R[/cyan]  Read register(s)")
        console.print("  [cyan]W[/cyan]  Write register")
        console.print("  [cyan]B[/cyan]  Back")
        choice = Prompt.ask("Choice").strip().upper()
        if choice == "B":
            break
        elif choice == "R":
            addr = int(Prompt.ask("Start address (decimal)"))
            count = int(Prompt.ask("Count", default="1"))
            vals = read_regs(client, addr, count)
            if vals:
                tbl = Table(box=box.SIMPLE)
                tbl.add_column("Address")
                tbl.add_column("Dec (unsigned)")
                tbl.add_column("Dec (signed)")
                tbl.add_column("Hex")
                for i, v in enumerate(vals):
                    tbl.add_row(str(addr+i), str(v), str(signed16(v)), f"0x{v:04X}")
                console.print(tbl)
            else:
                console.print("[red]Read failed.[/red]")
        elif choice == "W":
            addr = int(Prompt.ask("Register address (decimal)"))
            val_str = Prompt.ask("Value (decimal or 0xHEX)")
            val = int(val_str, 0)
            if Confirm.ask(f"Write [bold]{val}[/bold] (0x{val&0xFFFF:04X}) to register [bold]{addr}[/bold]?"):
                ok = write_reg(client, addr, val & 0xFFFF)
                console.print(f"[{'green' if ok else 'red'}]{'OK' if ok else 'FAIL'}[/]")


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    console.print(Panel(
        "[bold cyan]Weintek iR-ETN Configuration Tool[/bold cyan]\n"
        "[dim]Cross-platform EasyRemoteIO replacement[/dim]",
        border_style="cyan"
    ))

    ip = Prompt.ask("Enter iR-ETN IP address", default="192.168.0.212")
    port = int(Prompt.ask("Modbus TCP port", default="502"))

    console.print(f"\n[dim]Connecting to {ip}:{port}...[/dim]")
    client = ModbusTcpClient(ip, port=port, timeout=3)

    if not client.connect():
        console.print(f"[bold red]Connection failed to {ip}:{port}[/bold red]")
        sys.exit(1)

    console.print("[bold green]Connected![/bold green]\n")

    with console.status("[bold green]Discovering modules..."):
        system = discover_system(client)

    if not system["modules"]:
        console.print("[yellow]No modules detected. Check wiring and iBus status.[/yellow]")

    while True:
        console.rule()
        print_system_overview(system)
        console.print("\n  [cyan]1[/cyan]  Show I/O address map")
        console.print("  [cyan]2[/cyan]  Read live I/O values")
        console.print("  [cyan]3[/cyan]  Configure a module")
        console.print("  [cyan]4[/cyan]  Raw register read/write")
        console.print("  [cyan]5[/cyan]  Rescan / refresh module list")
        console.print("  [cyan]Q[/cyan]  Quit")

        choice = Prompt.ask("\nMain menu").strip().upper()

        if choice == "Q":
            break

        elif choice == "1":
            print_io_address_map(system)

        elif choice == "2":
            read_live_io(client, system)

        elif choice == "3":
            if not system["modules"]:
                console.print("[red]No modules found.[/red]")
                continue
            console.print("Select slot:")
            for m in system["modules"]:
                console.print(f"  [cyan]{m['slot']}[/cyan]  {m['name']}")
            slot = int(Prompt.ask("Slot number"))
            mod = next((m for m in system["modules"] if m["slot"] == slot), None)
            if not mod:
                console.print("[red]Slot not found.[/red]")
                continue
            if mod["type"] in ("analog", "temp"):
                configure_analog_module(client, mod)
            elif mod["type"] == "digital":
                configure_digital_module(client, mod)
            else:
                console.print(f"[yellow]Configuration not supported for type '{mod['type']}'.[/yellow]")

        elif choice == "4":
            raw_register_tool(client)

        elif choice == "5":
            with console.status("[bold green]Rescanning..."):
                system = discover_system(client)
            console.print("[green]Rescan complete.[/green]")

        else:
            console.print("[red]Invalid choice.[/red]")

        time.sleep(0.1)

    client.close()
    console.print("[bold cyan]Disconnected. Bye![/bold cyan]")


if __name__ == "__main__":
    main()