# HEDEF KART ACILIS DOSYASI - WiFi yok, panel UART2 uzerinden servis edilir.
#
# Bu kartin beslemesi WiFi vericisinin anlik akimini kaldirmiyor: radyo
# acilir acilmaz brownout ile resetleniyor. Tahmin degil, kartin kendi boot
# logundan okundu:
#
#     [dram] depolama sonrasi  140 KB bos
#     E BOD: Brownout detector was triggered
#     rst:0x3 (SW_RESET)   ... ve bastan
#
# 5V besleme, 240 MHz, tam txpower - hepsi denendi, ayni noktada oluyor.
# Bu yuzden ag katmani hic acilmiyor. Panel UART2'den servis ediliyor;
# karsi uctaki CYD onu agda yayinliyor:
#
#     projects/panel_vekil.py  ->  http://<cyd-ip>:216/
#
# Gercek sistem main.off olarak duruyor. Besleme sorunu cozulurse
# (3.3V hattina 470-1000 uF, ya da USB konnektorunun lehimlenmesi)
# main.off -> main.py yapip normal WiFi paneline donebilirsin.
import time

print()
print('== hedef kart: panel UART2 uzerinden ==')
print('   kurtarma icin 2 sn icinde Ctrl-C')
# Kurtarma penceresi: panel_uart.py serve_forever'a girince REPL'e
# donmuyor. mpremote'un Ctrl-C ile araya girebilmesi icin burada bekliyoruz.
time.sleep(2)

try:
    exec(open('/projects/panel_uart.py').read())
except KeyboardInterrupt:
    print('durduruldu - REPL serbest')
except Exception as e:
    import sys
    sys.print_exception(e)
    print('panel_uart durdu - REPL serbest')
