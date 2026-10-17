"""Does BLE work at all on this firmware, or only when Wi-Fi is off?

Runs over the serial REPL with main.py stopped, so the web panel is not
involved. Answers three separate questions:
  1. BLE with Wi-Fi still up   (what a project would actually face)
  2. BLE with Wi-Fi torn down  (is the controller in the build at all?)
  3. how much internal DRAM each state leaves
"""
import subprocess
import sys

PORT = sys.argv[1] if len(sys.argv) > 1 else 'COM3'

SCRIPT = r'''
import gc, time, network, esp32

def dram():
    r = esp32.idf_heap_info(esp32.HEAP_DATA)
    return sum(x[1] for x in r) // 1024

def try_ble(tag):
    gc.collect()
    print(tag, "-> bos DRAM:", dram(), "KB")
    try:
        import bluetooth
        ble = bluetooth.BLE()
        ble.active(True)
        print(tag, "-> BLE ACILDI, mac =", ble.config("mac"))
        ble.active(False)
        return True
    except Exception as e:
        print(tag, "-> BLE HATA:", type(e).__name__, e)
        return False

sta = network.WLAN(network.STA_IF)
print("wifi acik mi:", sta.active())
try_ble("[wifi ACIK ]")

sta.active(False)
ap = network.WLAN(network.AP_IF)
ap.active(False)
time.sleep(1)
gc.collect()
try_ble("[wifi KAPALI]")

sta.active(True)
print("bitti")
'''

r = subprocess.run(
    [sys.executable, '-m', 'mpremote', 'connect', PORT, 'exec', SCRIPT],
    capture_output=True, text=True, timeout=180)
print(r.stdout)
if r.stderr.strip():
    print('--- stderr ---')
    print(r.stderr)
