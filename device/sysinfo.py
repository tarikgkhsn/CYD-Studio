# sysinfo.py - everything the dashboard shows about the board itself.
import gc
import os
import sys
import time
import machine
import network

_BOOT_MS = time.ticks_ms()

_RESET_CAUSES = {
    1: 'guc verildi',
    2: 'harici reset',
    3: 'yazilim reset',
    4: 'watchdog',
    5: 'derin uykudan',
    6: 'brownout (dusuk voltaj)',
}


def _fs(path):
    try:
        st = os.statvfs(path)
        block = st[0]
        total = block * st[2]
        free = block * st[3]
        return {'total': total, 'free': free, 'used': total - free}
    except (OSError, AttributeError):
        return None


def _mac():
    try:
        from binascii import hexlify
        raw = network.WLAN(network.STA_IF).config('mac')
        return hexlify(raw, ':').decode().upper()
    except Exception:
        return ''


def collect(deep=False, sd_mounted=False):
    """`sd_mounted` must come from the code that did the mounting: statvfs
    on an unmounted /sd quietly falls back to the root filesystem, which
    would otherwise report a card that is not there."""
    if deep:
        gc.collect()
    free = gc.mem_free()
    alloc = gc.mem_alloc()

    d = {
        'ram_free': free,
        'ram_used': alloc,
        'ram_total': free + alloc,
        'freq': machine.freq(),
        'uptime': time.ticks_diff(time.ticks_ms(), _BOOT_MS) // 1000,
        'flash': _fs('/'),
        'sd': _fs('/sd') if sd_mounted else None,
        'mpy': sys.version,
        'platform': sys.platform,
        'mac': _mac(),
    }

    try:
        d['reset_cause'] = _RESET_CAUSES.get(machine.reset_cause(),
                                             str(machine.reset_cause()))
    except Exception:
        d['reset_cause'] = ''

    try:
        import esp
        d['flash_size'] = esp.flash_size()
    except Exception:
        d['flash_size'] = 0

    try:
        import esp32
        d['temp'] = esp32.mcu_temperature()
    except Exception:
        d['temp'] = None

    # Internal DRAM - this, not the MicroPython heap, is what limits how
    # many project threads can exist at once.
    d['idf'] = None
    try:
        import esp32
        regions = esp32.idf_heap_info(esp32.HEAP_DATA)
        total = sum(r[0] for r in regions)
        free = sum(r[1] for r in regions)
        if total:
            d['idf'] = {'total': total, 'free': free, 'used': total - free}
    except Exception:
        pass

    try:
        wlan = network.WLAN(network.STA_IF)
        if wlan.active() and wlan.isconnected():
            d['rssi'] = wlan.status('rssi')
        else:
            d['rssi'] = None
    except Exception:
        d['rssi'] = None

    return d
