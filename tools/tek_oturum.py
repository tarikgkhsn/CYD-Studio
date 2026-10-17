"""Tek seri oturum: port BIR kez acilir, kartin acilisi beklenir, butun
kopyala/sil/calistir islemleri ayni baglantida yapilir.

Neden (22 Eyl 2026, bu PC, CH340 3.9.2024.9): port her acilista kart
RESETLENIYOR. Dosya basina bir `mpremote` = dosya basina bir reset; mpremote
Ctrl-C'yi hemen gonderiyor, kart o an ROM acilisinda oldugu icin kaciyor ->
"could not enter raw repl", 6/6 dosya HATA. Burada acilistan sonra
`=== hazir ===` (ya da sessizlik) beklenir, sonra Ctrl-C + ham REPL.

    from tek_oturum import Oturum
    k = Oturum('COM4')
    k.cp('yerel.py', 'uzak.py'); k.rm('eski.py'); print(k.exec('print(1)'))
    k.reset()
"""
import time

from mpremote.transport_serial import SerialTransport, TransportError

ACILIS_BITTI = (b'=== hazir ===', b'>>> ', b'raw REPL')


class Oturum:
    def __init__(self, port, bekle=25):
        self.t = SerialTransport(port, baudrate=115200)
        self._acilisi_bekle(bekle)
        for deneme in range(3):
            try:
                self.t.enter_raw_repl(soft_reset=True)   # temiz heap
                return
            except TransportError:
                time.sleep(1)
        raise TransportError('ham REPL acilamadi: %s' % port)

    def _acilisi_bekle(self, sure):
        """Acilis mesajlari bitene kadar oku. Kart resetlenmediyse (hic cikti
        yok) 2 sn, acilis basladiysa 8 sn sessizlikten sonra devam (WiFi baglanirken
        kart 4-5 sn susuyor)."""
        s = self.t.serial
        t0 = son = time.time()
        buf = b''
        while time.time() - t0 < sure:
            n = s.in_waiting
            if n:
                buf = (buf + s.read(n))[-400:]
                son = time.time()
                if any(k in buf for k in ACILIS_BITTI):
                    time.sleep(0.3)
                    break
            elif time.time() - son > (8 if buf else 2):
                break
            time.sleep(0.05)
        s.read(s.in_waiting or 0)

    def exec(self, kod):
        return self.t.exec(kod).decode('utf-8', 'replace')

    def cp(self, yerel, uzak):
        with open(yerel, 'rb') as f:
            self.t.fs_writefile(uzak, f.read())

    def rm(self, uzak):
        """Silindiyse True, yoksa False."""
        return self.exec('import os\ntry:\n os.remove(%r); print(1)\n'
                         'except OSError: print(0)\n' % uzak).strip() == '1'

    def mkdir(self, uzak):
        self.exec('import os\ntry: os.mkdir(%r)\nexcept OSError: pass\n' % uzak)

    def reset(self):
        """machine.reset(); cevap beklenmez (kart hemen gider)."""
        self.t.exec_raw_no_follow('import machine\nmachine.reset()')
        time.sleep(0.3)
        self.t.close()

    def close(self):
        try:
            self.t.exit_raw_repl()
        finally:
            self.t.close()
