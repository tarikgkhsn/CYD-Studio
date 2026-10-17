<!-- Lives on the board; shown by the panel's Docs button when the language
     is EN (/api/docs?dil=en). Turkish original: docs.md. -->

# CYD Studio — on-board handbook

**What is this?** A small operating system for single-board micro PCs (ESP32
"CYD", NodeMCU ESP8266, an OLED ESP32): you write `.py` in the browser, press
**Run**, the project runs on the board — logs, run modes, a watchdog, per-project
web pages and a per-board feature map are all built in. **No C++ builds** — the
firmware is compiled by the developer, the user only writes Python.

**Panel:** http://192.168.0.217/ (CYD) · http://192.168.0.215/ (NodeMCU) ·
**Source:** the repo folder (`CYD-Studio/`) · Overview: `README.md`

Every number below was **measured** on the board, not guessed (10 Sep 2026).

---

## 1. First 30 seconds

```powershell
cd CYD-Studio
python tools\bootlog.py COM3 20        # reset and watch the boot log
curl http://192.168.0.217/api/status   # is the panel up?
```

If the panel does not answer the board is off, in solo mode, crashed at boot,
or `mpremote` left it at the REPL (RTS reset: `deploy.py --reset`).

---

## 2. Deploy — how code gets there

Shared core in `device/`, board layer in `boards/<name>/cyd.py` (+ drivers).
**On both boards the core is frozen into the firmware:** it runs from flash and
never enters RAM. A same-named `.py` on the filesystem **shadows** the frozen
copy and eats RAM — a core change means a rebuild.

```powershell
# CYD (ESP32) - builds in WSL, ~3 min
python tools\frozen_esp32_build.py [--heap 96]
python tools\flash.py COM3 firmware\micropython-esp32-cydstudio.bin --koru   # keeps FS, BOOT held
python tools\deploy.py --board cyd --port COM3 --frozen --samples --reset    # removes shadows

# NodeMCU (ESP8266) - auto reset, no button
python tools\frozen_esp8266_build.py
python tools\flash_esp8266.py COM3 --koru
python tools\deploy_mpy.py --board nodemcu --port COM3 --frozen --samples --reset
```

Never deploy without `--frozen`: it writes the core to the FS. For a quick
single-file experiment `mpremote fs cp x.py :x.py` (a shadow) is fine, but
measurements are misleading in that state; clean up with `--frozen` afterwards.

**Writing files:** PowerShell `Set-Content -Encoding utf8` adds a BOM →
MicroPython `NameError`. Write with Python: `open(p,'w',encoding='utf-8',newline='\n')`.

---

## 3. Flashing — the most critical fact about the CYD

The CYD's auto-reset circuit cannot drive IO0: **hold BOOT → tap RESET → keep
BOOT held until told "written"**; esptool with `--before no-reset --after
no-reset --baud 115200` (flash.py does this).

- If the port drops mid-write (`No more data to read`) the board **stays in
  download mode**: no need to hold the button again, just rerun
  `flash.py --koru` immediately.
- If a reset after writing still shows `boot:0x3 DOWNLOAD_BOOT`, BOOT is still
  pressed.
- Rollback: `flash.py COM3 firmware\micropython-esp32.bin --koru` (stock
  v1.28.0) + `deploy.py --board cyd --samples` (without `--frozen`).

NodeMCU: `flash_esp8266.py` resets automatically; leave it alone ~10 s after
flashing (LittleFS format).

---

## 4. The memory reality

The ESP32 has two pockets: the **Python heap** (project data) and **internal
DRAM** (Wi-Fi, sockets, thread stacks, BLE/TLS). `gc.mem_free()` can look
generous while a thread cannot be created. Measure with the panel's system box
or `cyd.dram()`.

| CYD | Stock v1.28.0 | **CYD Studio firmware** |
|---|---|---|
| Internal DRAM free, panel up | 27.8 KB | **55 KB** |
| Python heap free | 80 / 137 (auto-grows, swallows DRAM) | 75 / 94 (**fixed 96 KB**) |
| Concurrent projects | 1 (2nd: `can't create thread`) | 7 normal + 2–3 threads |

What the firmware changed: 12 core modules frozen into flash; the heap is fixed
(auto-doubling dropped DRAM from 76 to 12 KB); smaller lwIP/Wi-Fi buffers
(`sdkconfig.free_ram`); live log ring 250→100 lines (250 lines held 20.7 KB
and fragmented the heap); server socket timeout 5 s.

Thread stacks come **out of internal DRAM**: 10–15 KB per project. A project
drawing on the display takes 25–33 KB of heap (returned on stop). No leak (same
project started/stopped 4× → 65.7/65.7/65.9/65.8 KB).

**BLE / HTTPS:** not in normal mode — in **Solo** (needs 33 / 45 KB of
contiguous DRAM).

---

## 5. Run modes — the N / T / S chip on each row

Click to cycle; saved per file (`config.json` `modlar`). Default **N**.
The selected file's bar: **Save · N|T|S · Run/Stop (one button) · Delete** — it
turns into Stop while running, "Start solo" when S is selected. No separate
Solo/Stop buttons.

| Mode | How | Heap | Internal DRAM | For |
|---|---|---|---|---|
| **N Normal** | asyncio task on one shared thread | 2–15 KB | **0** (shared worker 17 KB once) | LEDs, sensors, small pages — most things |
| **T Thread** | own thread, sliced by the GIL | same | 10–15 KB | display drawing, loops without sleep, heavy compute |
| **S Solo** | panel off, board reboots, single project | all | all | BLE, HTTPS |

In normal mode the script is wrapped line by line into an `async def`
(`cyd.sleep` → `await`), streamed to a temp file and compiled from the file with
`execfile` (the source never sits in the heap as a string). If a sleep call is
inside a `def`, the transform does not apply → the project **opens as T by
itself** and the log says why.

**Truly side by side?** A project trying to loop every 10 ms; longest gap
between turns: alone 21 ms; + 4 normal projects 352 ms (isolated spikes: flash
log writes); + a display-drawing normal project **973 ms**; + a thread that never
yields the CPU **3.4 s**; same load with the project in T: **37 ms**. Rule:
display drawing and heavy compute → T.

**Buttons / input: interrupts, not polling.** `b = cyd.buton(22)` (pin ↔ GND),
in the loop `if b.basildi():`. 50 simulated presses next to a display project +
a heavy thread: polling 5/50, **interrupt 50/50**. The IRQ is released when the
project ends.

**Stopping:** a project that checks `should_stop()` exits within 3 s; a normal
task that ignores it is cancelled (`finally` runs); a project that never
`await`s locks the shared worker → the board resets after 5 s (the panel keeps
answering meanwhile). Threads: reset if it is the only one running, otherwise
flagged "stuck" with a force button.

ESP8266: N = a task in the server's asyncio loop (no threads, no T chip), S
available. Measured (10 Sep 2026): 3 normal projects side by side, heap 19 → 9 KB
(2.5–5 KB each), panel max 0.69 s; test_beraber 10/10, test_kesici 13/13.
Practical limit 3 projects (24 KB heap; the panel shows "Projects at once: 3").
If a sleep is inside a `def`, the old inline path (single project) is used. The
lite panel has Stop all too.

---

## 6. Writing a project

```python
import cyd
d = cyd.display()                  # display (lazy)
while not cyd.should_stop():       # MANDATORY: honour Stop
    ...
    cyd.sleep(0.1)                 # interruptible wait
```

`print()` streams to the panel and the persistent log. `should_stop()` is also
injected as a global.

| `cyd.` | |
|---|---|
| `display(rot=None,bgr=None)` · `touch()` · `set_display()` | display, touch |
| `led(r,g,b)` · `led_off()` · `light()` · `beep(f,ms)` | on-board RGB LED, LDR (0–4095, high=dark), speaker |
| `buton(pin, fn=None, aktif=0, sekme_ms=40)` | interrupt button: `.basildi()`, `.sayac`, `.basili()` |
| `rota('/path', fn)` · `rota_sil()` · `rotalar()` | the project's web page **on the main port**: `fn(req)` → str=html, dict=json; `req['sorgu']` = query |
| `sleep(s)` · `should_stop()` · `job_name()` | |
| `dram()` · `wifi()` · `mount_sd()` | free internal DRAM; connected STA; SD → `/sd` |
| `claim_display()` | display ownership; a second drawer gets a log warning |

**Don'ts:** a second HTTP server (use `cyd.rota` — a second socket drained DRAM
and froze the panel); `wlan.active(False)`; `machine.reset()`; endless loops
without sleep (in N they stall the neighbours, in T Stop resets the board).

Samples in `/projects`: `buton_ornek.py`, `yuk_kontrol.py` (the `/yuk` page),
`gece_lambasi.py`, `hareket_led.py`, `sicaklik_led.py`, `kopru_uart.py` …

**Storage (Settings → Storage):** Automatic (SD when present) | Always flash |
Always SD; move projects flash ↔ SD (copies, verifies, deletes the source; not
while a project runs). Live switch, no reset. With no card the 'sd' setting
falls back to flash and logs it. Hidden on boards without an SD slot.

---

## 7. Network

Static IP `192.168.0.217/24`; fallback AP **CYD-Studio** / `cyd12345` →
`192.168.4.1`. Normal mode: `http` ✅, `https` ❌ (✅ in Solo), raw sockets ✅,
NTP ✅, BLE in Solo. Large uploads: `requests` buffers the body in RAM — send
in chunks over a raw socket (`ornek_sunucuya_yukle.py`, 9690 B verified with
22 KB DRAM). Not available: camera module, WireGuard, Node.js/C#.

---

## 8. HTTP API

| Endpoint | Purpose |
|---|---|
| `GET /api/status` | jobs (with `mod`), `sys` (heap/DRAM/flash/rssi), `net`, `autostart`, `rotalar` |
| `GET /api/list` | files + `modlar` |
| `GET /api/log?since=N[&source=]` · `POST /api/log/clear` | live log (100-line ring) |
| `GET /api/log/file?name=` · `/api/log/files` · `POST /api/log/file/clear` | persistent log (8 KB/project) |
| `GET /api/file?name=` · `POST /api/save?name=` · `delete` · `rename` | |
| `POST /api/run?name=[&mod=]` · `stop` · `stopall` | |
| `POST /api/mod?name=&mod=normal\|thread\|solo` | the file's persistent mode |
| `POST /api/solo?name=&wifi=0\|1` · `POST /api/autostart?name=&on=` | |
| `GET /api/rotalar` · `GET /<route>` | project pages |
| `GET/POST /api/wifi` · `GET /api/scan` · `POST /api/reset` · `force` · `eval` | |
| `GET/POST /api/depolama[?mod=]` · `POST /api/tasi?hedef=sd\|flash` | projects on flash or SD; moving |
| `GET /api/caps` · `GET /api/docs[?dil=en]` | feature map; this document |

---

## 9. Known traps

- Display MISO is not wired: nothing can be read back, orientation was set
  **by eye** (`rotation=0`, `bgr=False`, 320×240 — leave it).
- Module name ≠ folder name (`projects.py` + `/projects` clashed → `store.py`).
- SD only on VSPI (slot 3); slot 2 is the display's bus, trying it kills the
  display. With no card `os.statvfs('/sd')` falls back to root (false positive).
- `mpremote` leaves the board at the REPL; `--reset` is required.
- The ESP8266 pre-emptor cannot enter a blocking C call (uart.write, big SPI).

---

## 10. File map

On the board: `boot.py main.py index.html docs.md docs_en.md config.json
/projects /logs` (core in firmware: `runtime jobs server store netmgr sysinfo
settings logstore cyd` + drivers).

PC `tools/`: `deploy.py` (`--frozen --reset`), `deploy_mpy.py` (ESP8266),
`frozen_esp32_build.py`, `frozen_esp8266_build.py`, `flash.py --koru`,
`flash_esp8266.py`, `bootlog.py`, `run_once.py`, `solo_run.py`,
`test_beraber.py`, `test_kesici.py`, `test_multi.py`, `upload_server.py`.

---

## 11. Verified state and open items

| | |
|---|---|
| CYD custom firmware (frozen + fixed heap + button) | ✅ 10 Sep 2026 |
| `test_beraber` / `test_kesici` | ✅ 10/10, 13/13 (both boards) |
| 7 projects side by side (N), button IRQ under load | ✅ 50/50 |
| ESP8266 frozen, together mode, pre-emptor | ✅ 24.7 KB free |
| Display, touch, BLE (solo), HTTPS (solo), NTP | ✅ |

Open: multiple normal projects on the ESP8266 + N/S chip in the lite panel; SD
card (slot 3) test; the second ESP32 (OLED, broken USB) — once its power problem
is solved it can join the panel as a "proxy" (more projects, not more RAM per
project); a custom build for a camera.
