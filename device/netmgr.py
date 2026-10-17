# netmgr.py - join the configured Wi-Fi, otherwise fall back to an access
# point so the board is always reachable from a browser.
import network
import time

import settings

_state = {'mode': 'off', 'ip': '0.0.0.0', 'ssid': ''}


def status():
    return dict(_state)


def scan():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    out = []
    seen = set()
    try:
        for net in wlan.scan():
            ssid = net[0].decode('utf-8', 'replace')
            if not ssid or ssid in seen:
                continue
            seen.add(ssid)
            out.append({'ssid': ssid, 'rssi': net[3], 'secure': net[4] != 0})
    except OSError:
        pass
    out.sort(key=lambda n: -n['rssi'])
    return out[:24]


def connect(timeout=15):
    cfg = settings.load()
    ssid = cfg.get('ssid') or ''
    if not ssid:
        return None
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    # Zayif beslemede WiFi vericisi anlik ~300 mA cekip gerilimi dusurur ve
    # kart brownout ile resetlenir. Verici gucunu kismak bu akimi belirgin
    # sekilde azaltir; menzil biraz duser ama kart ayakta kalir.
    tx = cfg.get('txpower')
    if tx:
        try:
            wlan.config(txpower=int(tx))
            print('wifi verici gucu: %s dBm' % tx)
        except (OSError, ValueError) as e:
            print('txpower ayarlanamadi:', e)

    # Modem power save: radyo dinlemedigi anlarda uykuya girer, ortalama
    # akimi belirgin dusurur. Gecikme birkac ms artar, panel icin onemsiz.
    if cfg.get('wifi_pm'):
        try:
            wlan.config(pm=network.WLAN.PM_POWERSAVE)
            print('wifi power save acik')
        except (OSError, ValueError, AttributeError) as e:
            print('power save ayarlanamadi:', e)

    try:
        wlan.config(dhcp_hostname=cfg.get('hostname') or 'cyd')
    except (OSError, ValueError):
        pass
    ip = cfg.get('ip') or ''
    if ip:
        gw = cfg.get('gateway') or ''
        mask = cfg.get('netmask') or '255.255.255.0'
        dns = cfg.get('dns') or gw or '8.8.8.8'
        try:
            wlan.ifconfig((ip, mask, gw, dns))
        except (OSError, ValueError) as e:
            print('statik ip ayarlanamadi:', e)
    pw = cfg.get('password') or ''
    for attempt in (1, 2):
        if wlan.isconnected():
            break
        try:
            wlan.connect(ssid, pw)
        except OSError as e:
            print('wifi connect hatasi:', e)
        deadline = time.ticks_add(time.ticks_ms(), int(timeout * 1000))
        while not wlan.isconnected():
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                break
            time.sleep_ms(200)
        if wlan.isconnected():
            break
        try:
            print('wifi denemesi %d basarisiz, durum=%s' % (attempt, wlan.status()))
        except Exception:
            print('wifi denemesi %d basarisiz' % attempt)
        try:
            wlan.disconnect()
        except OSError:
            pass
        time.sleep_ms(600)
    if not wlan.isconnected():
        wlan.active(False)
        return None
    ip = wlan.ifconfig()[0]
    _state.update(mode='sta', ip=ip, ssid=ssid)
    return ip


def start_ap():
    cfg = settings.load()
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    name = cfg.get('ap_ssid') or 'CYD-Studio'
    pw = cfg.get('ap_password') or 'cyd12345'
    try:
        if len(pw) >= 8:
            ap.config(essid=name, password=pw, authmode=network.AUTH_WPA_WPA2_PSK)
        else:
            ap.config(essid=name, authmode=network.AUTH_OPEN)
    except (OSError, ValueError):
        ap.config(essid=name)
    for _ in range(50):
        if ap.active():
            break
        time.sleep_ms(100)
    ip = ap.ifconfig()[0]
    _state.update(mode='ap', ip=ip, ssid=name)
    return ip


def up(timeout=15):
    """Try station mode, fall back to AP. Always returns an IP."""
    ip = connect(timeout)
    if ip:
        return ip, 'sta'
    ip = start_ap()
    return ip, 'ap'
