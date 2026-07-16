import configparser
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
REPO = _SCRIPTS.parent

_ini = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
_ini.read(_SCRIPTS / "config.ini")

def _x(section: str, key: str) -> int:
    return int(_ini[section][key], 0)

def _p(section: str, key: str) -> Path:
    return REPO / _ini[section][key]

def _s(section: str, key: str) -> str:
    return _ini[section][key]

OPENOCD_HOST = _s("openocd", "host")
OPENOCD_PORT = _x("openocd", "port")

SERIAL_PORT    = _s("serial", "port")
SERIAL_BAUD    = _x("serial", "baud")
SERIAL_TIMEOUT = int(_ini["serial"]["timeout_min"]) * 60

UBOOT_RAM_ADDR = _x("jtag", "uboot_ram_addr")
CHIP_ID_ADDR   = _x("jtag", "chip_id_addr")
CHIP_ID_MAGIC  = _x("jtag", "chip_id_magic")
DRAM_SIZE_MB   = _x("jtag", "dram_size_mb")
STAGING_ADDR   = _x("jtag", "staging_addr")

NOR_SIZE              = int(_ini["nor"]["total_size_mb"]) * 1024 * 1024
NOR_SECTOR_SIZE       = int(_ini["nor"]["sector_size_kb"]) * 1024
NOR_FLASHROM_PROG     = _s("nor", "flashrom_programmer")
NOR_CHIP_NAME  = _s("nor", "chip_name")
DTB_PARTS_PATH    = _s("paths", "dtb_parts_path")
DTB_CAL_EEPROM    = _s("paths", "dtb_cal_eeprom")

WIFI_CHIP_ID   = _x("wifi", "chip_id")
WIFI_MAC       = bytes(int(b, 16) for b in _s("wifi", "mac_address").split(":"))

UBOOT_DEFCONFIG = _p("paths", "uboot_defconfig")
UBOOT_BIN       = _p("paths", "uboot_bin")
UBOOT_RAM_BIN = _p("paths", "uboot_ram_bin")
DTB_FILE      = _p("paths", "uboot_dtb")
OPENWRT_DTB   = _p("paths", "openwrt_dtb")
UBOOT_ENV_TXT = _p("paths", "uboot_env_txt")
MKENVIMAGE    = _p("paths", "mkenvimage")
RECOVERY_BIN  = _p("paths", "recovery_bin")
NOR_IMAGE     = _p("paths", "nor_image")
