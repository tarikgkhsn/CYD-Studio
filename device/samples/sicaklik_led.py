# Sicaklik esigi -> LED.  Asil kod sicaklik_mod.mpy icinde.
#
# Bu dosya bilerek iki satir: jobs.py projeyi calistirirken kaynagi
# compile() ediyor ve ESP8266'da bos RAM 2,5-5 KB kadar. 3 KB'lik kaynak
# bile MemoryError veriyordu (olculdu). Iki satiri derlemek ise bedava,
# asil kod da onceden derlenmis .mpy olarak hic derlenmeden yukleniyor.
#
# print'i parametre geciyoruz: jobs.py kendi log fonksiyonunu SADECE bu
# dosyanin globallerine 'print' adiyla koyuyor, ayri modul onu gormez.
# Boyle gecince cikti panele ve kalici loga akiyor.
#
# Ayarlar (esik, histerezis, araliklar) sicaklik_mod.py'nin basinda.
import sicaklik_mod

sicaklik_mod.calistir(print)
