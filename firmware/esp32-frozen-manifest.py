# CYD Studio - CYD icin dondurulmus cekirdek (tools/frozen_esp32_build.py uretir).
include("$(PORT_DIR)/boards/manifest.py")
freeze("/root/cydstudio-frozen-esp32/modules")
