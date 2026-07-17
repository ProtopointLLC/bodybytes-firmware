import configparser
from dataclasses import dataclass
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
STAGING_ADDR   = _x("jtag", "staging_addr")

NOR_SECTOR_SIZE   = int(_ini["nor"]["sector_size_kb"]) * 1024
NOR_FLASHROM_PROG = _s("nor", "flashrom_programmer")

DTB_PARTS_PATH = _s("paths", "dtb_parts_path")
DTB_CAL_EEPROM = _s("paths", "dtb_cal_eeprom")

UBOOT_DEFCONFIG = _p("paths", "uboot_defconfig")
UBOOT_BIN       = _p("paths", "uboot_bin")
UBOOT_RAM_BIN   = _p("paths", "uboot_ram_bin")
DTB_FILE        = _p("paths", "uboot_dtb")
OPENWRT_DTB     = _p("paths", "openwrt_dtb")
UBOOT_ENV_TXT   = _p("paths", "uboot_env_txt")
MKENVIMAGE      = _p("paths", "mkenvimage")
RECOVERY_BIN    = _p("paths", "recovery_bin")
NOR_IMAGE       = _p("paths", "nor_image")

BOARD_NAMES = ("bodybytes", "vocore2")


@dataclass(frozen=True)
class BoardConfig:
    name: str
    dram_size_mb: int
    nor_size: int
    nor_chip_name: str
    reset_config: str
    halt_cmd: str
    emmc_capacity_gb: int
    # wifi_* overrides from config.ini; key = register name without the 'wifi_' prefix.
    # Absent keys use the reset / default values defined in lib/wifi.py.
    wifi: dict[str, bytes]


def _load_wifi_overrides(s: configparser.SectionProxy) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for raw_key, raw_val in s.items():
        if not raw_key.startswith("wifi_"):
            continue
        name = raw_key[5:]  # strip "wifi_" prefix
        result[name] = bytes(int(v, 16) for v in raw_val.split())
    return result


def load_board(name: str) -> BoardConfig:
    section = f"board:{name}"
    if section not in _ini:
        raise SystemExit(f"error: unknown board '{name}'; available: {', '.join(BOARD_NAMES)}")
    s = _ini[section]
    return BoardConfig(
        name=name,
        dram_size_mb=int(s["dram_size_mb"]),
        nor_size=int(s["nor_total_size_mb"]) * 1024 * 1024,
        nor_chip_name=s["nor_chip_name"],
        reset_config=s["reset_config"],
        halt_cmd=s["halt_cmd"],
        emmc_capacity_gb=int(s.get("emmc_capacity_gb", "0")),
        wifi=_load_wifi_overrides(s),
    )
