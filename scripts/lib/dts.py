from pyfdt.pyfdt import FdtBlobParse, FdtNode

from lib.config import DTB_FILE, DTB_PARTS_PATH, DTB_CAL_EEPROM, OPENWRT_DTB
from lib.log import err


def parse_wifi_cal_size() -> int:
    """Return the WiFi calibration EEPROM size from the OpenWrt built DTB."""
    if not OPENWRT_DTB.exists():
        err(f"OpenWrt DTB not found: {OPENWRT_DTB}  (build OpenWrt first)")
    fdt = FdtBlobParse(OPENWRT_DTB.open("rb")).to_fdt()
    for item in fdt.resolve_path(DTB_CAL_EEPROM):
        if hasattr(item, "name") and item.name == "reg" and len(item.words) >= 2:
            return item.words[1]
    err(f"reg not found at {DTB_CAL_EEPROM} in {OPENWRT_DTB}")


def parse_nor_partitions() -> dict[str, tuple[int, int]]:
    """Return {label: (offset, size)} from the NOR partition table in the U-Boot DTB."""
    if not DTB_FILE.exists():
        err(f"DTB not found: {DTB_FILE}  (build U-Boot first)")
    fdt = FdtBlobParse(DTB_FILE.open("rb")).to_fdt()
    result: dict[str, tuple[int, int]] = {}
    for node in fdt.resolve_path(DTB_PARTS_PATH):
        if isinstance(node, FdtNode):
            props = {p.name: p for p in node.subdata if hasattr(p, "name")}
            if "label" in props and "reg" in props:
                result[props["label"].strings[0]] = (props["reg"].words[0], props["reg"].words[1])
    return result
