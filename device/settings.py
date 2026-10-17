# settings.py - tiny JSON-backed config store on the internal flash.
import json

PATH = '/config.json'

DEFAULTS = {
    'ssid': '',
    'password': '',
    'ap_ssid': 'CYD-Studio',
    'ap_password': 'cyd12345',
    'autostart': [],        # project file names to run at boot
    'splash': True,         # draw the boot screen, or leave the panel free
    'rotation': 0,          # 0/2 landscape (native), 1/3 portrait
    # This panel showed NAVY as red with the BGR bit set, so it wants RGB.
    'bgr': False,
    # One-shot: boot without the web server so a project gets the ~59 KB of
    # internal DRAM the listening socket would take (BLE and TLS need it).
    # main.py clears this before doing anything else, so a reset always
    # brings the panel back.
    'solo_once': False,
    'solo_wifi': True,      # in solo mode, keep Wi-Fi up? off frees ~44 KB
    # Solo'da calisacak proje. Ayri tutuluyor: "Calistir" bir projeyi
    # kalici olarak acilis listesine yazmamali - autostart kullanicinin
    # bilerek yildizladigi seyler icin.
    'solo_proje': '',
    # Projeler nerede dursun: 'otomatik' (SD takiliysa SD, yoksa flash),
    # 'flash' (SD taksan da dahili flash), 'sd' (SD sart; yoksa flash'a duser
    # ve loga yazar). Tasima: POST /api/tasi?hedef=sd|flash[&names=a,b]
    'depolama': 'otomatik',
    # Wi-Fi transmit power in dBm. None keeps the default (highest). On a
    # weakly powered board the radio's current spike browns the chip out;
    # around 11 dBm cuts that noticeably at some cost in range.
    'txpower': None,
    'cpu_freq': 240,        # MHz. 80 belirgin akim tasarrufu saglar.
    'wifi_pm': False,       # modem power save - ortalama akimi dusurur
    # Zayif beslemede son care: brownout korumasini kapatir. RISK: gerilim
    # gercekten cokerse temiz reset yerine flash bozulabilir.
    'disable_bod': False,
    'hostname': 'cyd',
    # static addressing - leave 'ip' empty to fall back to DHCP
    'ip': '',
    'netmask': '255.255.255.0',
    'gateway': '',
    'dns': '',
}

_cache = None


def load():
    global _cache
    if _cache is None:
        cfg = dict(DEFAULTS)
        try:
            with open(PATH) as f:
                cfg.update(json.load(f))
        except (OSError, ValueError):
            pass
        _cache = cfg
    return _cache


def save(**kw):
    cfg = load()
    cfg.update(kw)
    with open(PATH, 'w') as f:
        json.dump(cfg, f)
    return cfg


def get(key, default=None):
    return load().get(key, DEFAULTS.get(key, default))


def autostart_list():
    """Stored as a list; tolerate the old single-string format."""
    v = get('autostart')
    if isinstance(v, str):
        return [v] if v else []
    return list(v or [])
