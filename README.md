# CYD Studio

**Browser-managed MicroPython project runner for ESP32 / ESP8266 boards.**

**Website, docs and the Workshop (shared projects): https://cyd.nuvaka.com** · English: https://cyd.nuvaka.com/en/

Prepare the board once; after that there is **no compiling at all**. Projects are
plain `.py` files written or uploaded in the web panel, started and stopped with
one click. Several projects can run side by side.

The same system, the same panel and the same `import cyd` work on three
different boards. Board differences live in data, not in code (a `OZELLIKLER`
feature map per board); the panel hides buttons for hardware the board does
not have.

> Türkçe belge: [README_TR.md](README_TR.md)
> Tutorial for writing projects: [`docs/atolye_defteri.html`](docs/atolye_defteri.html) (Workshop Notebook, TR/EN).
> The on-board handbook shown by the panel's **Docs** button: [`device/docs_en.md`](device/docs_en.md).

---

## Boards

| Board | MCU | Hardware | Firmware | Concurrent projects |
|---|---|---|---|---|
| **CYD** (ESP32-2432S028R, "Cheap Yellow Display") | ESP32 | 320x240 ILI9341 display, XPT2046 touch, SD slot, RGB LED, LDR, speaker | **Custom image** (frozen core, fixed 96 KB heap, RAM diet) | 7 normal + 2-3 thread |
| **NodeMCU** | ESP8266 | on-board LED, A0 analog input | **Custom image** (frozen core, asyncio) | 3 normal (no threads) |
| **ESP32 OLED** | ESP32 | 128x64 SSD1306 OLED | Stock MicroPython v1.28, core on the filesystem | 4+ |

All numbers in this repository were **measured on the boards**, not estimated.

**Why MicroPython?** It is the only solid option that gives "write in the
browser, run instantly" on this hardware. Node.js is impossible (V8 wants
~50 MB RAM, the board has 520 KB); C/C++ and .NET nanoFramework need a PC
build for every change.

---

## Features

- **Web panel**: file list, editor, live console, persistent log, settings
  (WiFi / static IP / hostname / display rotation / storage), TR/EN interface,
  shortcuts (`Ctrl+S`, `Ctrl+Enter`, `/`, `Esc`).
- **Three run modes**, chosen with the **N / T / S** chip next to each project:

  | Mode | How it runs | Use it for |
  |---|---|---|
  | **N** Normal | asyncio task on a shared thread; `cyd.sleep` is rewritten to `await` on the fly | LEDs, sensors, small web pages; most projects |
  | **T** Thread | Its own thread (ESP32 only) | Display drawing, tight loops without sleep, heavy computation |
  | **S** Solo | Panel shuts down, board reboots, one project gets all the RAM; RESET brings the panel back | BLE, HTTPS |

- **Stop always works**: cooperative flag, then task cancellation, then a
  watchdog reset if needed. A stuck project can never lock the panel permanently.
- **Per-project web pages**: `cyd.rota('/path', fn)` registers a route on the
  main server. No second socket, same port.
- **Persistent log**: every project's output is also written to
  `/logs/<project>.log`, so it survives resets and solo mode.
- **USB bridge**: the panel over a serial cable, no WiFi needed:
  `tools/usb_panel.py` -> http://127.0.0.1:8080/
- **Interrupt-driven button**: `cyd.buton(pin, fn)`. Under load, polling caught
  5 of 50 presses; the interrupt caught 50 of 50 (measured).

---

## Quick start

1. Open the board's panel: `http://<board-ip>/`
   If the board cannot join your WiFi it opens its own access point
   (`CYD-Studio` / `cyd12345`) -> `http://192.168.4.1/`
2. Create a file with **+ new**, write your code, run it with **▶**.
   `print()` output streams to the console at the bottom.
3. Stop it with **■**.

### Project skeleton

```python
import cyd
from machine import Pin

led = Pin(getattr(cyd, 'D1', 22), Pin.OUT, value=0)   # NodeMCU: D1, CYD: GPIO22

try:
    while not cyd.should_stop():      # listen to the panel's Stop button
        led.value(1)
        if not cyd.sleep(0.5): break  # interruptible wait (seconds)
        led.value(0)
        if not cyd.sleep(0.5): break
finally:
    led.value(0)                      # clean up however the project ends
```

Rules:
- `while not cyd.should_stop()`, not `while True`.
- `cyd.sleep`, not `time.sleep`: it listens for Stop while waiting and yields to neighbouring projects.
- Do not open a second HTTP server; use `cyd.rota`.
- Do not call `wlan.active(False)` or `machine.reset()`; they take the panel down too.
- The NodeMCU has little RAM: keep `print` strings short and ship big
  libraries as precompiled `.mpy` (e.g. `bme280.mpy`).

### The `cyd` module (summary)

| | |
|---|---|
| `cyd.should_stop()` · `cyd.sleep(s)` | Stop contract |
| `cyd.display()` · `cyd.touch()` | Display / touch (raises a clear error on boards without them) |
| `cyd.led(r, g, b)` · `cyd.led_off()` | On-board LED |
| `cyd.light()` · `cyd.beep(freq, ms)` | Light sensor / speaker |
| `cyd.buton(pin, fn=None)` | Interrupt-driven button: `.basildi()`, `.sayac`, `.basili()` |
| `cyd.rota(path, fn)` · `cyd.rota_sil()` | The project's own web page |
| `cyd.dram()` · `cyd.wifi()` | Free internal DRAM / connected WiFi interface |
| `cyd.mount_sd()` | Mount the SD card at `/sd` (CYD only) |
| `cyd.D0` … `cyd.D8`, `cyd.A0` | NodeMCU pin labels |

The full list with measurements is in the on-board handbook
([`device/docs_en.md`](device/docs_en.md)).

---

## Setup and maintenance (PC side)

Requirements: Python 3.12, `pip install mpremote esptool mpy-cross pyserial`.
On Windows the serial port is `COM3`-style, on Linux `/dev/ttyUSB0`-style.

```bash
# CYD (custom firmware on the board): filesystem files only, the core is in the firmware
python tools/deploy.py --board cyd --port COM3 --frozen --samples --reset

# NodeMCU (custom firmware on the board)
python tools/deploy_mpy.py --board nodemcu --port COM4 --frozen --samples --reset

# ESP32 OLED (stock firmware): the core goes to the filesystem
python tools/deploy.py --board oled --port COM6 --samples

# Watch the boot log
python tools/bootlog.py COM3 25

# Open the panel over the USB cable (no WiFi needed)
python tools/usb_panel.py COM4 --board nodemcu    # -> http://127.0.0.1:8080/
```

With `--config`, `boards/<board>/config.json` is written to the board and
**overwrites** the settings stored there. Use it for the first install, then leave it out.

### WiFi settings (`config.json`)

`boards/*/config.json` is **not in the repository** because it holds the WiFi
password. Copy the example and fill it in:

```bash
cp boards/cyd/config.example.json boards/cyd/config.json
```

### Firmware

Ready-made images are in `firmware/`. Rebuilding needs WSL/Linux with ESP-IDF
v5.5.1 (ESP32) or the xtensa-lx106 toolchain (ESP8266):
`tools/frozen_esp32_build.py`, `tools/frozen_esp8266_build.py`.

| File | Board |
|---|---|
| `micropython-esp32-cydstudio.bin` | CYD, custom image |
| `micropython-esp8266-frozen.bin` | NodeMCU, custom image |
| `micropython-esp32.bin` · `micropython-esp8266.bin` | Stock backups |

**Flashing the CYD:** the board's auto-reset circuit cannot drive IO0.
Hold **BOOT**, press and release **RESET**, keep holding BOOT until the write
finishes, and run esptool with `--before no-reset --after no-reset --baud 115200`.

```bash
python tools/flash.py COM3 firmware/micropython-esp32-cydstudio.bin --koru   # --koru keeps the filesystem
```

**Important, shadowing:** never copy a core `.py` file onto a board that runs
the frozen firmware. The copy on the filesystem overrides the frozen module and
the RAM savings silently disappear. Always deploy to those boards with `--frozen`.

---

## Known limits

- **No HTTPS or BLE in Normal mode** (not enough internal DRAM); both work in **Solo** mode.
- The ESP32 OLED board browns out when WiFi starts if it is powered from a PC
  USB port; it runs fine from an external **3.3 V** supply (240 MHz, full TX power).
- The clone CH340 driver 3.9.2024.9 on Windows fails to open the port at
  38400 baud or above; open at 9600 and raise the speed afterwards.
- A CYD powered through an unpowered USB hub may drop off USB when WiFi
  starts; use a direct PC port or a powered hub.

---

## Repository layout

```
device/          shared core: main, server, jobs, runtime, store, netmgr,
                 settings, sysinfo, logstore, usbkopru, index.html, docs
device/samples/  example projects (LED, sensors, BME280, I2C scan, BLE, HTTPS...)
boards/<board>/  board layer: cyd.py (+ drivers, lite server/panel), config example
firmware/        ready-made images + frozen manifests
tools/           deploy, flash, boot log, USB bridge, tests
docs/            Workshop Notebook (tutorial, TR/EN)
```

Adding a board: put a `cyd.py` (with an `OZELLIKLER` dict) and a
`config.example.json` under `boards/<name>/`. The core does not need to change.

Identifiers and comments are a mix of Turkish and English; the panel UI is
bilingual (TR/EN).

---

## Built with Claude Code

[Claude Code](https://claude.com/claude-code), Anthropic's command-line coding
agent, was used in this project for:

- running the measurements on the boards over the serial port (RAM per project,
  stop latency, button interrupts under load) and recording the results,
- writing some of the Python tooling and test scripts in `tools/`,
- keeping the project notes and generating the on-board handbook
  (`device/docs.md`, `device/docs_en.md`) and the Workshop Notebook from them.

## License

MIT, see [LICENSE](LICENSE). The firmware images are built from
[MicroPython](https://micropython.org/) (MIT) and ESP-IDF (Apache-2.0).
