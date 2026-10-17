# CYD Studio - NodeMCU icin dondurulmus cekirdek (tools/frozen_esp8266_build.py uretir).
# Stok listeyi koru, ustune asyncio (normal mod gorevleri) ve bizim moduller.
include("$(PORT_DIR)/boards/manifest.py")
include("$(MPY_DIR)/extmod/asyncio")
freeze("/root/cydstudio-frozen/modules")
