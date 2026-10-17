# main.py - CYD Studio: web-based project manager for the ESP32 CYD board.
#
# Everything here is defensive: if the screen, the SD card or the network
# fails we still want the REPL and, where possible, the web server.
import gc
import sys
import time

BANNER = 'CYD Studio'


def _dram(tag):
    """Internal DRAM is the scarce resource here (BLE/TLS need it), so the
    boot log records where it goes."""
    try:
        import esp32
        free = sum(r[1] for r in esp32.idf_heap_info(esp32.HEAP_DATA))
        print('  [dram] %-22s %4d KB bos' % (tag, free // 1024))
        return free
    except ImportError:
        import gc
        gc.collect()
        print('  [ram]  %-22s %4d KB bos' % (tag, gc.mem_free() // 1024))
        return 0
    except Exception:
        return 0


def _splash(settings, ip, mode, where):
    """Boot screen. Each board draws it at a size that fits its panel -
    the CYD has 320x240, the OLED board only 128x64."""
    import cyd
    satirlar = [BANNER]
    if mode == 'ap':
        satirlar.append('AP: ' + str(settings.get('ap_ssid')))
        satirlar.append('sifre: ' + str(settings.get('ap_password')))
        satirlar.append('192.168.4.1')
    else:
        satirlar.append('WiFi baglandi')
        satirlar.append(ip)
    satirlar.append(where)
    return cyd.splash(satirlar)


def _dosya_akit(srv):
    """Sade (ESP8266) sunucuda GET /api/file dosyayi RAM'e toptan okuyordu:
    4 KB'lik i2c_tara.py 'allocating 4352 bytes' verdi (23 Eyl 2026, 13 KB
    bos ama parcali), panel editore '[object Object]' yazdi. Sunucu
    firmware'e gomulu; yeniden derlemeden, dosyayi 512 B'lik parcalarla
    akitan _dosya() yoluna cevirir. WiFi ve USB koprusu ayni _route'tan
    gectigi icin ikisini de duzeltir. Tam sunucuda (_dosya yok) dokunmaz."""
    if not hasattr(srv, '_dosya'):
        return
    import os
    import store
    asil = srv._route

    def _route(conn, yontem, yol, q, govde):
        if yol == '/api/file':
            try:
                p = store.path(q.get('name', ''))
                os.stat(p)          # yoksa JSON hata (panel editore yazmasin)
            except Exception as e:
                return srv._err(conn, e)
            return srv._dosya(conn, p, 'text/plain; charset=utf-8')
        return asil(conn, yontem, yol, q, govde)
    srv._route = _route


def _boot():
    import settings
    import store
    from jobs import Manager

    print('\n=== %s ===' % BANNER)

    # Read and immediately clear the one-shot solo flag: whatever happens
    # next, the following boot brings the web panel back.
    _dram('acilis')
    solo = bool(settings.get('solo_once', False))

    # Sunucuyu ag acilmadan ONCE import ediyoruz. ESP8266'da yigin 35 KB ve
    # WiFi kalkinca fena parcalaniyor; sonrasinda Server sinifi icin gereken
    # bitisik blok bulunamiyor (MemoryError). Taze yiginda sorunsuz yukleniyor.
    # Solo modda hic import etmiyoruz - orada sunucu zaten acilmayacak ve
    # ESP32'de ~59 KB dahili DRAM'i projeye birakmis oluyoruz.
    Server = None
    if not solo:
        try:
            gc.collect()
            from server import Server
            gc.collect()
            _dram('sunucu yuklendi')
        except MemoryError as e:
            print('sunucu yuklenemedi (RAM):', e)
    solo_wifi = bool(settings.get('solo_wifi', True))
    if solo:
        try:
            settings.save(solo_once=False)
        except Exception as e:
            print('solo bayragi temizlenemedi:', e)
            solo = False

    # The display is NOT created here on purpose. Initialising SPI costs
    # internal DRAM, and that is the scarce resource a project needs for
    # BLE or TLS. cyd.display() builds it on first use instead. The SD
    # mount only touches VSPI, so the panel's HSPI stays free either way.

    # ---- storage ------------------------------------------------------
    try:
        base = store.init()
        where = 'SD kart' if store.on_sd() else 'dahili flash'
        print('projeler: %s (%s)' % (base, where))
    except Exception as e:
        print('depolama hatasi:', e)
        where = '?'
    _dram('depolama sonrasi')

    # ---- network ------------------------------------------------------
    # Bringing Wi-Fi up costs ~44 KB of internal DRAM. A solo project that
    # needs BLE cannot afford that, so it can ask for the radio to stay off.
    if solo and not solo_wifi:
        ip, mode = '0.0.0.0', 'kapali'
        print('ag: WiFi acilmadi (solo + BLE modu)')
    else:
        try:
            import netmgr
            ip, mode = netmgr.up(timeout=15)
            print('ag: %s  ip: %s' % (mode, ip))
        except Exception as e:
            print('ag hatasi:', e)
            ip, mode = '0.0.0.0', 'off'
    _dram('wifi sonrasi')

    # ---- screen -------------------------------------------------------
    if settings.get('splash', True):
        try:
            _splash(settings, ip, mode, where)
        except Exception as e:
            print('splash hatasi:', e)

    gc.collect()

    # ---- jobs + autostart ---------------------------------------------
    mgr = Manager()
    mgr.system('%s hazir - http://%s/' % (BANNER, ip))
    mgr.system('depolama: %s' % where)
    # Solo modda SADECE solo icin secilen proje calisir. Acilis listesi
    # (yildizlananlar) normal modun isi; "Calistir" onu kirletmemeli.
    if solo:
        tek = settings.get('solo_proje') or ''
        calisacak = [tek] if tek else settings.autostart_list()
    else:
        calisacak = settings.autostart_list()

    for name in calisacak:
        try:
            import os
            p = store.path(name)
            os.stat(p)
            print('otomatik baslat:', name)
            # Solo modda sunucu acilmayacagi icin projeyi ayri bir thread'e
            # koymanin anlami yok - hem ESP8266'da thread zaten yok. Dogrudan
            # calistirip bitmesini bekliyoruz; cikti kalici loga yaziliyor.
            if solo:
                mgr.start_blocking(name, p)
            else:
                mgr.start(name, p)
        except Exception as e:
            mgr.system('otomatik baslatma basarisiz (%s): %s' % (name, e))

    # ---- solo mode ----------------------------------------------------
    # No listening socket, so the project keeps the DRAM that lwIP would
    # otherwise take for good. Press RESET to get the panel back.
    if solo:
        print('SOLO MOD: web sunucusu acilmadi')
        mgr.system('SOLO MOD - panel kapali, bos DRAM projeye birakildi')
        try:
            import cyd
            mgr.system('bos DRAM: %d KB' % (cyd.dram() // 1024))
        except Exception:
            pass
        mgr.system('paneli geri getirmek icin karta RESET at')
        while True:
            time.sleep(5)
            if not mgr.running_jobs():
                mgr.system('calisan proje kalmadi - RESET at')
                time.sleep(25)

    # ---- web server ---------------------------------------------------
    _dram('isler sonrasi')
    if Server is None:
        print('sunucu yok - RAM yetmedi. REPL kullanilabilir.')
        while True:
            time.sleep(5)
    srv = Server(mgr, port=80)
    _dosya_akit(srv)
    srv.listen()
    _dram('soket sonrasi')
    # Thread'siz kartta projeler sunucuyla ayni is parcaciginda kosar;
    # cyd.sleep() bu pompayla sunucuya tur verir. Thread'li kartta gereksiz.
    # Ustune zamanlayici kesicisi: cyd.sleep() cagirmayan sıkı dongu bile
    # paneli dusuremez, durdurmayi yoksayan proje bekci ile resetlenir.
    # USB koprusu: panel WiFi olmadan da kablodan (tools/usb_panel.py).
    # Dosya FS'te yoksa sessizce gecer. Thread'li kartta kendi is parcacigi;
    # thread'siz kartta tik() sunucu pompasina eklenir (her turda yoklar).
    usb_tik = None
    try:
        import usbkopru
        if usbkopru.baslat(srv):
            print('usb kopru hazir: python tools/usb_panel.py <COM>')
        else:
            usb_tik = usbkopru.tik
    except ImportError:
        pass
    except Exception as e:
        print('usb kopru kurulamadi:', e)
    try:
        import runtime
        if not runtime.HAS_THREADS and hasattr(srv, 'tek_tur'):
            if usb_tik:
                def pompa(_t=srv.tek_tur, _u=usb_tik, _s=srv):
                    _u(_s)
                    return _t()
                print('usb kopru hazir (pompada): python tools/usb_panel.py <COM>')
            else:
                pompa = srv.tek_tur
            runtime.kesici_baslat(pompa, mgr.bekci_tik)
            print('kesici kayitli: proje calisirken panel acik kalir, '
                  'sıkı dongu de kesilir')
    except Exception as e:
        print('kesici kurulamadi:', e)
        try:
            runtime.pompa_kaydet(srv.tek_tur)
        except Exception:
            pass
    print('web arayuzu: http://%s/' % ip)
    print('=== hazir ===\n')
    while True:
        try:
            srv.serve_forever()
        except Exception as e:
            print('sunucu yeniden baslatiliyor:', e)
            try:
                if srv.sock:
                    srv.sock.close()
            except Exception:
                pass
            srv.sock = None
            time.sleep(1)


try:
    _boot()
except Exception as e:
    sys.print_exception(e)
    print('\n!!! main.py durdu - REPL kullanilabilir')
