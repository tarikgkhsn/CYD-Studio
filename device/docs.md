<!-- Bu dosya kartin uzerinde durur ve panelin Dokuman sekmesinde gosterilir.
     Ingilizcesi docs_en.md (panel TR/EN secimine gore /api/docs?dil=en).
     Yeni bir Claude Code oturumuna verirken: panelde Dokuman -> Kopyala,
     ya da repodaki README_TR.md ile bu dosyayi goster. -->

# CYD Studio — kart üstü belge

**Ne bu?** Tek kartlı mini bilgisayarlar (ESP32 "CYD", NodeMCU ESP8266, OLED'li
ESP32) için küçük bir işletim sistemi: tarayıcıdan `.py` yazarsın, **Çalıştır**'a
basarsın, proje kartta koşar; loglar, çalışma modları, bekçi, projelerin kendi
web sayfaları, kart başına özellik haritası hepsi içeride. **C++ derlemesi yok** —
firmware'i geliştirici derler, kullanıcı yalnız Python yazar.

**Panel:** http://192.168.0.217/ (CYD) · http://192.168.0.215/ (NodeMCU) ·
**Kaynak:** repo klasörü (`CYD-Studio/`) · Genel tanıtım: `README_TR.md`

Aşağıdaki her sayı kartta **ölçüldü**, tahmin değil (10 Eyl 2026).

---

## 1. İlk 30 saniye

```powershell
cd CYD-Studio
python tools\bootlog.py COM3 20        # reset at, acilis logunu gor
curl http://192.168.0.217/api/status   # panel ayakta mi
```

Panel cevap vermiyorsa kart ya kapalı, ya solo modda, ya açılışta patlamış,
ya da `mpremote` onu REPL'de bırakmış (RTS reset: `deploy.py --reset`).

---

## 2. Deploy — kod nasıl gider

Ortak çekirdek `device/`, kart katmanı `boards/<ad>/cyd.py` (+ sürücüler).
**Her iki kartta çekirdek firmware'e gömülü (frozen):** flash'tan çalışır,
RAM'e girmez. FS'e aynı adlı `.py` atarsan dondurulmuşu **gölgeler** ve
RAM yer — çekirdek değişikliği = yeniden derleme.

```powershell
# CYD (ESP32) - derleme WSL'de, ~3 dk
python tools\frozen_esp32_build.py [--heap 96]
python tools\flash.py COM3 firmware\micropython-esp32-cydstudio.bin --koru   # FS korunur, BOOT basili
python tools\deploy.py --board cyd --port COM3 --frozen --samples --reset    # golgeleri siler

# NodeMCU (ESP8266) - otomatik reset, tus yok
python tools\frozen_esp8266_build.py
python tools\flash_esp8266.py COM3 --koru
python tools\deploy_mpy.py --board nodemcu --port COM3 --frozen --samples --reset
```

`--frozen` olmadan deploy etme: çekirdeği FS'e yazar. Tek dosyayı hızlı
denemek için `mpremote fs cp x.py :x.py` (gölge) olur, ama ölçümler o
durumda yanıltır; sonunda `--frozen` ile temizle.

**Dosya yazarken:** PowerShell `Set-Content -Encoding utf8` BOM ekler →
MicroPython `NameError`. Python'la yaz: `open(p,'w',encoding='utf-8',newline='\n')`.

---

## 3. Flash — CYD'de en kritik bilgi

CYD'nin oto-reset devresi IO0'ı süremiyor: **BOOT basılı tut → RESET
bas-bırak → BOOT'u "yazıldı" denene kadar bırakma**; esptool
`--before no-reset --after no-reset --baud 115200` (flash.py bunu yapar).

- Yazma ortasında port düşerse (`No more data to read`) kart **download
  modunda kalır**: tuşa tekrar gerek yok, `flash.py --koru`'yu hemen yeniden
  çalıştır.
- Yazma sonrası reset yine `boot:0x3 DOWNLOAD_BOOT` diyorsa BOOT hâlâ basılı.
- Geri dönüş: `flash.py COM3 firmware\micropython-esp32.bin --koru` (stok
  v1.28.0) + `deploy.py --board cyd --samples` (frozen'sız).

NodeMCU: `flash_esp8266.py` otomatik resetler; flash sonrası ~10 sn dokunma
(LittleFS formatı).

---

## 4. Bellek gerçeği

ESP32'de iki cep var: **Python heap** (projelerin verisi) ve **dahili DRAM**
(WiFi, soketler, thread yığınları, BLE/TLS). `gc.mem_free()` bol görünürken
thread açılamayabilir. Doğru ölçüm: panelin sistem kutusu ya da `cyd.dram()`.

| CYD | Stok v1.28.0 | **CYD Studio firmware'i** |
|---|---|---|
| Dahili DRAM boş, panel açık | 27,8 KB | **55 KB** |
| Python heap boş | 80 / 137 (otomatik büyür, DRAM'i yutar) | 75 / 94 (**sabit 96 KB**) |
| Aynı anda proje | 1 (2.'si `can't create thread`) | 7 normal + 2–3 thread |

Firmware ne yaptı: çekirdek 12 modül flash'a dondu; heap sabitlendi
(otomatik ikiye katlama DRAM'i 76→12 KB'ye düşürüyordu); lwIP/WiFi
tamponları küçüldü (`sdkconfig.free_ram`); canlı log halkası 250→100 satır
(250 satır 20,7 KB tutup heap'i parçalıyordu); sunucu soket zaman aşımı 5 sn.

Thread yığını **dahili DRAM'den** çıkar: proje başına 10–15 KB. Ekran çizen
proje heap'ten 25–33 KB alır (durunca geri gelir). Sızıntı yok (aynı proje
4 kez aç/kapat → 65,7/65,7/65,9/65,8 KB).

**BLE / HTTPS:** normal modda değil, **Solo**'da (33 / 45 KB bitişik DRAM ister).

---

## 5. Çalışma modları — satırdaki N / T / S cipi

Tıkla: sırayla değişir, dosyaya kayıtlı (`config.json` `modlar`). Varsayılan **N**.
Seçili dosyanın çubuğu: **Kaydet · N|T|S · Çalıştır/Durdur (tek düğme) · Sil** —
koşarken Durdur olur, S seçiliyse "Solo başlat". Ayrı Solo/Durdur düğmesi yok.

| Mod | Nasıl | Heap | Dahili DRAM | Ne için |
|---|---|---|---|---|
| **N Normal** | Tek ortak iş parçacığında asyncio görevi | 2–15 KB | **0** (ortak çalışan bir kez 17 KB) | LED, sensör, küçük sayfa — çoğu şey |
| **T Thread** | Kendi thread'i, GIL ile dilimli | aynı | 10–15 KB | ekran çizen, sleep'siz döngü, ağır hesap |
| **S Solo** | Panel kapalı, kart yeniden başlar, tek proje | hepsi | hepsi | BLE, HTTPS |

Normal modda proje satır satır `async def` içine sarılır (`cyd.sleep` →
`await`), geçici dosyaya akıtılıp `execfile` ile dosyadan derlenir (kaynak
string olarak heap'e girmez). Bekleme çağrısı bir `def` içindeyse dönüşüm
uymaz → proje **kendiliğinden T'de açılır**, log nedenini yazar.

**Gerçekten yan yana mı?** 10 ms'de tur atan proje, turlar arası en uzun boşluk:
tek başına 21 ms; + 4 normal proje 352 ms (tekil sıçramalar: flash'a log);
+ ekran çizen normal proje **973 ms**; + CPU bırakmayan thread **3,4 sn**;
aynı yük, proje T'de: **37 ms**. Kural: ekran çizen ve ağır hesap → T.

**Buton / giriş: yoklama değil kesme.** `b = cyd.buton(22)` (pin ↔ GND),
döngüde `if b.basildi():`. 50 taklit basış, ekran çizen + ağır thread
yanında: yoklama 5/50, **kesme 50/50**. Proje bitince kesme kapanır.

**Durdurma:** `should_stop()` dinleyen 3 sn içinde çıkar; dinlemeyen normal
görev iptal edilir (`finally` çalışır); hiç `await` etmeyen proje ortak
çalışanı kilitler → 5 sn sonra kart resetlenir (panel bu sırada cevap verir).
Thread'de: tek çalışan oysa reset, başkaları varsa "takıldı" + zorla düğmesi.

ESP8266: N = sunucunun asyncio döngüsünde görev (thread yok, T cipi yok), S var.
Ölçüldü (10 Eyl 2026): 3 normal proje yan yana, heap 19 → 9 KB (proje başına
2,5–5 KB), panel en uzun 0,69 sn; test_beraber 10/10, test_kesici 13/13.
Pratik sınır 3 proje (24 KB heap; panelde "Aynı anda proje: 3"). Bekleme `def`
içindeyse eski satır içi yol (tek proje) kullanılır. Sade panelde de Tümünü durdur var.

---

## 6. Proje yazma

```python
import cyd
d = cyd.display()                  # ekran (tembel)
while not cyd.should_stop():       # ZORUNLU: Durdur'a saygi
    ...
    cyd.sleep(0.1)                 # durdurulabilir bekleme
```

`print()` panele ve kalıcı loga akar. `should_stop()` global olarak da var.

| `cyd.` | |
|---|---|
| `display(rot=None,bgr=None)` · `touch()` · `set_display()` | ekran, dokunmatik |
| `led(r,g,b)` · `led_off()` · `light()` · `beep(f,ms)` | kart üstü RGB LED, LDR (0–4095, büyük=karanlık), hoparlör |
| `buton(pin, fn=None, aktif=0, sekme_ms=40)` | kesmeli buton: `.basildi()`, `.sayac`, `.basili()` |
| `rota('/yol', fn)` · `rota_sil()` · `rotalar()` | projenin web sayfası **ana portta**: `fn(istek)` → str=html, dict=json; `istek['sorgu']` |
| `sleep(sn)` · `should_stop()` · `job_name()` | |
| `dram()` · `wifi()` · `mount_sd()` | boş dahili DRAM; bağlı STA; SD → `/sd` |
| `claim_display()` | ekran sahipliği; ikinci proje çizerse loga uyarı |

**Yapılmayacaklar:** ikinci HTTP sunucusu açma (`cyd.rota` kullan — ikinci
soket DRAM'i tüketip paneli kilitledi); `wlan.active(False)`; `machine.reset()`;
sleep'siz sonsuz döngü (N'de komşuları bekletir, T'de Durdur reset atar).

Örnekler `/projects`'te: `buton_ornek.py`, `yuk_kontrol.py` (`/yuk` sayfası),
`gece_lambasi.py`, `hareket_led.py`, `sicaklik_led.py`, `kopru_uart.py` …

**Depolama (Ayarlar → Depolama):** Otomatik (SD varsa SD) | Hep flash | Hep SD;
projeleri flash ↔ SD taşı (kopyalar, doğrular, kaynağı siler; çalışan proje
varken yapılmaz). Canlı geçiş, reset gerekmez. SD yoksa 'sd' ayarı flash'a
düşer ve loga yazar. SD yuvası olmayan kartta kutu gizli.

---

## 7. Ağ

Statik IP `192.168.0.217/24`; bağlanamazsa **CYD-Studio** / `cyd12345` AP'si
→ `192.168.4.1`. Normal modda `http` ✅, `https` ❌ (Solo'da ✅), ham soket ✅,
NTP ✅, BLE Solo'da. Büyük dosya: `requests` gövdeyi RAM'e alır — ham soketle
parça parça (`ornek_sunucuya_yukle.py`, 22 KB DRAM'le 9690 B doğrulandı).
Yok: kamera modülü, WireGuard, Node.js/C#.

---

## 8. HTTP API

| Uç | İş |
|---|---|
| `GET /api/status` | işler (`mod` dahil), `sys` (heap/DRAM/flash/rssi), `net`, `autostart`, `rotalar` |
| `GET /api/list` | dosyalar + `modlar` |
| `GET /api/log?since=N[&source=]` · `POST /api/log/clear` | canlı log (100 satır halka) |
| `GET /api/log/file?name=` · `/api/log/files` · `POST /api/log/file/clear` | kalıcı log (8 KB/proje) |
| `GET /api/file?name=` · `POST /api/save?name=` · `delete` · `rename` | |
| `POST /api/run?name=[&mod=]` · `stop` · `stopall` | |
| `POST /api/mod?name=&mod=normal\|thread\|solo` | dosyanın kalıcı modu |
| `POST /api/solo?name=&wifi=0\|1` · `POST /api/autostart?name=&on=` | |
| `GET /api/rotalar` · `GET /<rota>` | projelerin sayfaları |
| `GET/POST /api/wifi` · `GET /api/scan` · `POST /api/reset` · `force` · `eval` | |
| `GET/POST /api/depolama[?mod=]` · `POST /api/tasi?hedef=sd\|flash` | projeler flash mı SD mi; taşıma |
| `GET /api/caps` · `GET /api/docs[?dil=en]` | özellik haritası; bu belge |

---

## 9. Bilinen tuzaklar

- Panel MISO bağlı değil: ekrandan geri okuma yok, yön **gözle** ayarlandı
  (`rotation=0`, `bgr=False`, 320×240 — dokunma).
- Modül adı ≠ klasör adı (`projects.py` + `/projects` çakıştı → `store.py`).
- SD yalnız VSPI (slot 3); slot 2 ekranın hattı, denersen ekran ölür. SD
  takılı değilken `os.statvfs('/sd')` köke düşer (sahte pozitif).
- `mpremote` kartı REPL'de bırakır; `--reset` şart.
- Kesici (ESP8266) bloke eden C çağrısının içine giremez (uart.write, büyük SPI).

---

## 10. Dosya haritası

Kartta: `boot.py main.py index.html docs.md docs_en.md config.json /projects /logs`
(çekirdek firmware'de: `runtime jobs server store netmgr sysinfo settings
logstore cyd` + sürücüler).

PC `tools/`: `deploy.py` (`--frozen --reset`), `deploy_mpy.py` (ESP8266),
`frozen_esp32_build.py`, `frozen_esp8266_build.py`, `flash.py --koru`,
`flash_esp8266.py`, `bootlog.py`, `run_once.py`, `solo_run.py`,
`test_beraber.py`, `test_kesici.py`, `test_multi.py`, `upload_server.py`.

---

## 11. Doğrulanmış durum ve açık işler

| | |
|---|---|
| CYD özel firmware (frozen + sabit heap + buton) | ✅ 10 Eyl 2026 |
| `test_beraber` / `test_kesici` | ✅ 10/10, 13/13 (her iki kart) |
| 7 proje yan yana (N), buton kesmesi yük altında | ✅ 50/50 |
| ESP8266 frozen, beraber mod, kesici | ✅ 24,7 KB boş |
| Ekran, dokunmatik, BLE (solo), HTTPS (solo), NTP | ✅ |

Açık: ESP8266'da çoklu normal proje + sade panele N/S cipi; SD kart (slot 3)
testi; ikinci ESP32 (OLED, USB'si bozuk) — güç sorunu çözülürse panele "vekil"
olarak eklenir (proje sayısı artar, tek projenin RAM'i artmaz); kamera için
özel derleme.
