# CYD Studio

**ESP32 / ESP8266 kartları için tarayıcıdan yönetilen MicroPython proje çalıştırıcı.**

**Site, belgeler ve Atölye (paylaşılan projeler): https://cyd.nuvaka.com**

Kart bir kez hazırlanır; ondan sonra **hiç derleme yapılmaz**. Projeler `.py`
dosyası olarak panelden yazılır ya da yüklenir, tek tıkla çalıştırılır, durdurulur.
Aynı anda birden fazla proje yan yana koşabilir.

Aynı sistem, aynı panel, aynı `import cyd` üç farklı kartta çalışır. Kartlar
arasındaki farklar koda değil, veriye yazılmıştır (`OZELLIKLER` sözlüğü); panel
kartta olmayan donanımın düğmelerini kendisi gizler.

> English: [README.md](README.md)
> Projeler için öğretici belge: [`docs/atolye_defteri.html`](docs/atolye_defteri.html) (Atölye Defteri, TR/EN).
> Panelin **Doküman** düğmesinde gösterilen kart üstü belge: [`device/docs.md`](device/docs.md).

---

## Kartlar

| Kart | İşlemci | Donanım | Firmware | Aynı anda proje |
|---|---|---|---|---|
| **CYD** (ESP32-2432S028R, "Cheap Yellow Display") | ESP32 | 320x240 ILI9341 ekran, XPT2046 dokunmatik, SD, RGB LED, LDR, hoparlör | **Özel imaj** (çekirdek dondurulmuş, sabit 96 KB heap, RAM diyeti) | 7 normal + 2-3 thread |
| **NodeMCU** | ESP8266 | dahili LED, A0 analog | **Özel imaj** (çekirdek dondurulmuş, asyncio) | 3 normal (thread yok) |
| **ESP32 OLED** | ESP32 | 128x64 SSD1306 OLED | Stok MicroPython v1.28, çekirdek dosya sisteminde | 4+ |

Bu depodaki bütün sayılar **kart üzerinde ölçülmüştür**, tahmin değildir.

**Neden MicroPython?** "Tarayıcıdan yaz, anında çalıştır" davranışını bu
donanımda veren tek sağlam seçenek. Node.js imkânsız (V8 ~50 MB RAM ister,
kartta 520 KB var); C/C++ ve .NET nanoFramework her değişiklikte PC'de derleme ister.

---

## Özellikler

- **Tarayıcı paneli**: dosya listesi, editör, canlı konsol, kayıtlı log, ayarlar
  (WiFi / statik IP / hostname / ekran yönü / depolama), TR/EN arayüz,
  kısayollar (`Ctrl+S`, `Ctrl+Enter`, `/`, `Esc`).
- **Üç çalışma modu**, her projenin yanındaki **N / T / S** cipiyle seçilir:

  | Mod | Nasıl koşar | Ne için |
  |---|---|---|
  | **N** Normal | Ortak iş parçacığında asyncio görevi; `cyd.sleep` otomatik `await`'e çevrilir | LED, sensör, küçük sayfa; çoğu proje |
  | **T** Thread | Kendi thread'i (yalnız ESP32) | Ekran çizen, sleep'siz sıkı döngü, ağır hesap |
  | **S** Solo | Panel kapanır, kart yeniden başlar, tek proje tüm RAM'i alır; RESET panele döner | BLE, HTTPS |

- **Durdurma her koşulda çalışır**: nazik bayrak, sonra görev iptali, gerekirse
  bekçi reseti. Kilitlenen proje paneli kalıcı düşüremez.
- **Projenin kendi web sayfası**: `cyd.rota('/yol', fn)` ana sunucuya rota kaydeder.
  İkinci soket yok, aynı port.
- **Kalıcı log**: her projenin çıktısı `/logs/<proje>.log`'a da yazılır; reset ve
  solo modda da kaybolmaz.
- **USB köprüsü**: panel WiFi olmadan kablodan:
  `tools/usb_panel.py` -> http://127.0.0.1:8080/
- **Kesme tabanlı buton**: `cyd.buton(pin, fn)`. Yük altında yoklama 50 basıştan
  5'ini yakalarken kesme 50/50 yakaladı (ölçüldü).

---

## Hızlı başlangıç

1. Kartın paneline gir: `http://<kartın-ip>/`
   WiFi'ye bağlanamazsa kart kendi erişim noktasını açar
   (`CYD-Studio` / `cyd12345`) -> `http://192.168.4.1/`
2. **+ yeni** ile dosya oluştur, yaz, **▶** ile çalıştır. `print()` çıktısı alttaki
   konsola akar.
3. **■** ile durdur.

### Proje iskeleti

```python
import cyd
from machine import Pin

led = Pin(getattr(cyd, 'D1', 22), Pin.OUT, value=0)   # NodeMCU: D1, CYD: GPIO22

try:
    while not cyd.should_stop():      # paneldeki Durdur'u dinle
        led.value(1)
        if not cyd.sleep(0.5): break  # durdurulabilir bekleme (saniye)
        led.value(0)
        if not cyd.sleep(0.5): break
finally:
    led.value(0)                      # nasıl biterse bitsin temizle
```

Kurallar:
- `while True` değil, `while not cyd.should_stop()`.
- `time.sleep` değil, `cyd.sleep`: beklerken de Durdur'u dinler, komşu projelere sıra verir.
- İkinci HTTP sunucusu açma; `cyd.rota` kullan.
- `wlan.active(False)` / `machine.reset()` çağırma; paneli de düşürür.
- NodeMCU'da RAM az: uzun `print` metinlerinden kaçın, büyük kütüphaneleri
  önceden derlenmiş `.mpy` olarak koy (ör. `bme280.mpy`).

### `cyd` modülü (özet)

| | |
|---|---|
| `cyd.should_stop()` · `cyd.sleep(sn)` | Durdurma sözleşmesi |
| `cyd.display()` · `cyd.touch()` | Ekran / dokunmatik (kartta yoksa açık hata fırlatır) |
| `cyd.led(r, g, b)` · `cyd.led_off()` | Kart üstü LED |
| `cyd.light()` · `cyd.beep(freq, ms)` | Işık sensörü / hoparlör |
| `cyd.buton(pin, fn=None)` | Kesme tabanlı buton: `.basildi()`, `.sayac`, `.basili()` |
| `cyd.rota(yol, fn)` · `cyd.rota_sil()` | Projenin web sayfası |
| `cyd.dram()` · `cyd.wifi()` | Boş dahili DRAM / bağlı WiFi arayüzü |
| `cyd.mount_sd()` | SD kartı `/sd` altına bağla (yalnız CYD) |
| `cyd.D0` … `cyd.D8`, `cyd.A0` | NodeMCU pin etiketleri |

Ölçümlerle birlikte tam liste kart üstü belgede: [`device/docs.md`](device/docs.md).

---

## Kurulum ve bakım (PC)

Gerekenler: Python 3.12, `pip install mpremote esptool mpy-cross pyserial`.
Seri port Windows'ta `COM3`, Linux'ta `/dev/ttyUSB0` biçimindedir.

```bash
# CYD (özel firmware kartta): yalnız FS dosyaları, çekirdek firmware'de
python tools/deploy.py --board cyd --port COM3 --frozen --samples --reset

# NodeMCU (özel firmware kartta)
python tools/deploy_mpy.py --board nodemcu --port COM4 --frozen --samples --reset

# ESP32 OLED (stok firmware): çekirdek dosya sistemine gider
python tools/deploy.py --board oled --port COM6 --samples

# Açılış logunu izle
python tools/bootlog.py COM3 25

# Paneli USB kablosundan aç (WiFi gerekmez)
python tools/usb_panel.py COM4 --board nodemcu    # -> http://127.0.0.1:8080/
```

`--config` verilirse `boards/<kart>/config.json` karta yazılır ve karttaki
ayarları **ezer**; ilk kurulumda ver, sonra verme.

### WiFi ayarları (`config.json`)

Şifre içerdiği için `boards/*/config.json` **repoda yok**. Örnekten kopyala ve doldur:

```bash
cp boards/cyd/config.example.json boards/cyd/config.json
```

### Firmware

Hazır imajlar `firmware/` altında. Yeniden derlemek WSL/Linux + ESP-IDF v5.5.1
(ESP32) ya da xtensa-lx106 toolchain (ESP8266) ister:
`tools/frozen_esp32_build.py`, `tools/frozen_esp8266_build.py`.

| Dosya | Kart |
|---|---|
| `micropython-esp32-cydstudio.bin` | CYD, özel imaj |
| `micropython-esp8266-frozen.bin` | NodeMCU, özel imaj |
| `micropython-esp32.bin` · `micropython-esp8266.bin` | Stok yedekler |

**CYD'yi flash'larken:** kartın otomatik reset devresi IO0'ı süremez.
BOOT'u basılı tut, RESET'e bas-bırak, BOOT'u işlem bitene kadar bırakma;
esptool'u `--before no-reset --after no-reset --baud 115200` ile çalıştır.

```bash
python tools/flash.py COM3 firmware/micropython-esp32-cydstudio.bin --koru   # --koru: dosya sistemi silinmez
```

**Önemli, gölgeleme:** dondurulmuş çekirdekli karta çekirdek `.py` dosyası
atma. Dosya sistemindeki kopya firmware'dekini ezer ve RAM kazancı sessizce
kaybolur. Deploy araçlarını bu kartlarda hep `--frozen` ile çalıştır.

---

## Bilinen sınırlar

- **Normal modda HTTPS ve BLE yok** (dahili DRAM yetmez); ikisi de **Solo** modda çalışır.
- ESP32 OLED kartı PC USB'sinden beslenince WiFi açılırken brownout'a girer;
  harici **3,3 V** kaynakla sorunsuz (240 MHz, tam verici gücü).
- Windows'ta klon CH340 sürücüsü 3.9.2024.9 portu 38400 ve üstü hızda açarken
  hata verir; 9600'de açıp sonra hızı yükselt.
- Beslemesiz USB hub üzerindeki CYD, WiFi açılınca USB'den düşebilir; doğrudan
  PC portu ya da beslemeli hub kullan.

---

## Dizin yapısı

```
device/          ortak çekirdek: main, server, jobs, runtime, store, netmgr,
                 settings, sysinfo, logstore, usbkopru, index.html, docs
device/samples/  örnek projeler (LED, sensör, BME280, I2C tarama, BLE, HTTPS...)
boards/<kart>/   kart katmanı: cyd.py (+ sürücüler, sade sunucu/panel), config örneği
firmware/        hazır imajlar + frozen manifestleri
tools/           deploy, flash, bootlog, USB köprüsü, testler
docs/            Atölye Defteri (öğretici, TR/EN)
```

Yeni kart eklemek: `boards/<ad>/` altına `cyd.py` (bir `OZELLIKLER` sözlüğüyle)
ve `config.example.json` koy. Çekirdeğe dokunmak gerekmez.

---

## Claude Code katkısıyla

Anthropic'in komut satırı kodlama ajanı [Claude Code](https://claude.com/claude-code)
bu projede şunlar için kullanıldı:

- ölçümlerin seri port üzerinden kartlarda çalıştırılması (proje başına RAM,
  durdurma gecikmesi, yük altında buton kesmesi) ve sonuçların not edilmesi,
- `tools/` altındaki bazı Python araç ve test betiklerinin yazılması,
- proje notlarının tutulması ve bu notlardan kart üstü belgenin
  (`device/docs.md`, `device/docs_en.md`) ile Atölye Defteri'nin oluşturulması.

## Lisans

MIT, bkz. [LICENSE](LICENSE). Firmware imajları
[MicroPython](https://micropython.org/) (MIT) ve ESP-IDF (Apache-2.0) ile derlenmiştir.
