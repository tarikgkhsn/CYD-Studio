# store.py - where user projects live. Prefers the SD card, falls back
# to the internal flash so the board is usable with no card inserted.
import os
import sys

FLASH_DIR = '/projects'
SD_DIR = '/sd/projects'

_base = None
_on_sd = False
_not = ''            # son init'in aciklamasi (panel/log icin)


def _ensure(path):
    try:
        os.mkdir(path)
    except OSError:
        pass
    os.listdir(path)
    return path


def mod():
    """Kullanicinin depolama tercihi: otomatik | flash | sd."""
    try:
        import settings
        m = settings.get('depolama', 'otomatik')
        return m if m in ('otomatik', 'flash', 'sd') else 'otomatik'
    except Exception:
        return 'otomatik'


def _sd_bagla():
    try:
        import cyd
        return bool(cyd.mount_sd('/sd'))
    except Exception:
        return False


def sd_var():
    """SD su an bagli mi (baglamayi da dener)."""
    return _sd_bagla()


def init(try_sd=True):
    global _base, _on_sd, _not
    m = mod()
    if try_sd and m != 'flash':
        if _sd_bagla():
            try:
                _base = _ensure(SD_DIR)
                _on_sd = True
                _not = 'SD kart (ayar: %s)' % m
                _sys_path()
                return _base
            except Exception:
                pass
        if m == 'sd':
            _not = "ayar 'sd' ama SD kart yok/okunamadi - dahili flash'a dusuldu"
        else:
            _not = 'dahili flash (SD takili degil)'
    else:
        _not = "dahili flash (ayar: 'flash')"
    _base = _ensure(FLASH_DIR)
    _on_sd = False
    _sys_path()
    return _base


def not_():
    base()
    return _not


def tasi(hedef, adlar=None):
    """Projeleri flash <-> SD arasinda TASIR (kopyala + sil). hedef: 'sd' |
    'flash'. adlar None ise kaynaktaki tum .py dosyalari. Donus:
    (tasinanlar, hatalar). SD yoksa ValueError."""
    if hedef not in ('sd', 'flash'):
        raise ValueError('hedef sd ya da flash olmali')
    if not _sd_bagla():
        raise ValueError('SD kart takili degil ya da okunamiyor')
    kaynak, hedef_dir = (FLASH_DIR, SD_DIR) if hedef == 'sd' else (SD_DIR, FLASH_DIR)
    _ensure(kaynak)
    _ensure(hedef_dir)
    if adlar is None:
        adlar = [n for n in os.listdir(kaynak) if n.endswith('.py')]
    tasinan, hatalar = [], []
    for ad in adlar:
        try:
            ad = safe(ad)
            src = kaynak + '/' + ad
            dst = hedef_dir + '/' + ad
            with open(src, 'rb') as fi, open(dst, 'wb') as fo:
                while True:
                    b = fi.read(512)
                    if not b:
                        break
                    fo.write(b)
            if os.stat(src)[6] != os.stat(dst)[6]:
                raise OSError('boyut tutmadi')
            os.remove(src)
            tasinan.append(ad)
        except Exception as e:
            hatalar.append('%s: %s' % (ad, e))
    return tasinan, hatalar


def _sys_path():
    if _base and _base not in sys.path:
        sys.path.append(_base)


def base():
    if _base is None:
        init()
    return _base


def on_sd():
    base()
    return _on_sd


def safe(name):
    name = (name or '').strip().replace('\\', '/')
    name = name.rsplit('/', 1)[-1]
    if not name or name in ('.', '..'):
        raise ValueError('gecersiz dosya adi')
    for ch in '\0:*?"<>|':
        if ch in name:
            raise ValueError('gecersiz karakter: %s' % ch)
    return name


def path(name):
    return base() + '/' + safe(name)


def listing():
    out = []
    b = base()
    try:
        entries = os.listdir(b)
    except OSError:
        return out
    for name in entries:
        full = b + '/' + name
        try:
            st = os.stat(full)
        except OSError:
            continue
        if st[0] & 0x4000:          # skip directories
            continue
        out.append({'name': name, 'size': st[6], 'mtime': st[8],
                    'py': name.endswith('.py')})
    out.sort(key=lambda e: e['name'].lower())
    return out


def read(name):
    with open(path(name)) as f:
        return f.read()


def write(name, data):
    p = path(name)
    if isinstance(data, str):
        data = data.encode('utf-8')
    with open(p, 'wb') as f:
        f.write(data)
    return p


def delete(name):
    os.remove(path(name))


def rename(old, new):
    os.rename(path(old), path(new))


def free_space():
    try:
        st = os.statvfs(base())
        return st[0] * st[3], st[0] * st[2]      # free, total
    except (OSError, AttributeError):
        return 0, 0
