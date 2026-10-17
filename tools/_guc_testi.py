# Kart uzerinde calisir: RADYOYA HIC DOKUNMADAN 90 saniye bosta bekler.
#
# Amac tek bir soruyu cevaplamak: 3.3V hatti WiFi olmadan da cokuyor mu?
#   cokmuyorsa -> akim yetersizligi (besleme/kablo/adaptor)
#   yine cokuyorsa -> kartin regulatoru ya da bir kisa devre arizali
#
# Bu calisirken 3.3V pinini olcmeye devam et.
import machine
import time
import gc

SEBEP = {1: 'guc verildi', 2: 'harici reset', 3: 'yazilim reset',
         4: 'WATCHDOG', 5: 'derin uyku', 6: 'BROWNOUT (dusuk voltaj)'}

print('=== GUC KARARLILIK TESTI ===')
print('son acilis sebebi:', SEBEP.get(machine.reset_cause(), machine.reset_cause()))
print('frekans:', machine.freq() // 1000000, 'MHz')
print('WiFi ACILMIYOR - radyo tamamen kapali')
print()
print('Simdi 3.3V pinini olc. Kart resetlenirse bu yazi bastan baslar.')
print()

# Daha da az akim cekmek icin islemciyi yavaslatalim
try:
    machine.freq(80000000)
    print('islemci 80 MHz e dusuruldu (daha az akim)')
except Exception as e:
    print('frekans dusurulemedi:', e)

for i in range(1, 91):
    gc.collect()
    if i % 5 == 0 or i < 5:
        print('%3d sn  ayakta   RAM %d KB' % (i, gc.mem_free() // 1024))
    time.sleep(1)

print()
print('90 SANIYE BOYUNCA AYAKTA KALDI.')
print('-> Radyo kapaliyken kart saglam. Sorun WiFi akimini karsilayamayan besleme.')
