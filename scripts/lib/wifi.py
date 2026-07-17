"""MT7628AN WiFi EEPROM register definitions and factory blob builder.

Register names and reset values from docs/wifi.md (MT7628AN datasheet, section 59).
Undocumented entries from driver source / VoCore2 NOR backup analysis
(docs/assets/vocore2_nor_backup.bin, factory partition at 0x40000).
"""

_TABLE: tuple[tuple[str, int, int, int], ...] = (
    ("chip_id",                0x0000, 2, 0x7628),
    ("eeprom_rev",             0x0002, 2, 0x0200),
    ("wlan_mac",               0x0004, 6, 0x2876E1430C00),
    ("eeprom_0x24",            0x0024, 2, 0x0020),
    ("mac0",                   0x0028, 6, 0x2976E1430C00),
    ("mac1",                   0x002E, 6, 0x2A76E1430C00),
    ("nic_confg_0",            0x0034, 2, 0x3422),
    ("nic_confg_1",            0x0036, 2, 0x0000),
    ("country_reg",            0x0039, 1, 0xFF),
    ("xtal_trim_1",            0x003A, 1, 0x00),
    ("led_mode",               0x003B, 1, 0x01),
    ("nic_confg_2",            0x0042, 2, 0x0022),
    ("ext_lna_gain",           0x0044, 1, 0x00),
    ("rssi_ofst",              0x0046, 2, 0x0000),
    ("rf_setting",             0x0048, 2, 0x0030),
    ("tx_power_delta",         0x0050, 1, 0x82),
    ("tx_power_bw80_delta_hi", 0x0053, 1, 0x94),
    ("tx_power_ext_pa_5g",     0x0054, 1, 0x40),
    ("temp_sen_cal",           0x0055, 1, 0xB0),
    ("tx0_pa_tssi_lsb",        0x0056, 1, 0xC0),
    ("tx0_pa_tssi_msb",        0x0057, 1, 0xCC),
    ("tx0_power",              0x0058, 1, 0x23),
    ("tx0_pwr_ofst_l",         0x0059, 1, 0x00),
    ("tx0_pwr_ofst_m",         0x005A, 1, 0x00),
    ("tx0_pwr_ofst_h",         0x005B, 1, 0x00),
    ("tx1_pa_tssi_lsb",        0x005C, 1, 0x40),
    ("tx1_pa_tssi_msb",        0x005D, 1, 0xCC),
    ("tx1_power",              0x005E, 1, 0x23),
    ("tx1_pwr_ofst_l",         0x005F, 1, 0x00),
    ("tx1_pwr_ofst_m",         0x0060, 1, 0x00),
    ("tx1_pwr_ofst_h",         0x0061, 1, 0x00),
    ("eeprom_0x9e",            0x009E, 2, 0x0000),
    ("tx_pwr_cck_0",           0x00A0, 1, 0xC6),
    ("tx_pwr_cck_1",           0x00A1, 1, 0xC6),
    ("tx_pwr_ofdm_0",          0x00A2, 1, 0xC6),
    ("tx_pwr_ofdm_1",          0x00A3, 1, 0xC6),
    ("tx_pwr_ofdm_2",          0x00A4, 1, 0xC6),
    ("tx_pwr_ofdm_3",          0x00A5, 1, 0xC6),
    ("tx_pwr_ofdm_4",          0x00A6, 1, 0xC6),
    ("tx_pwr_ht_mcs_0",        0x00A7, 1, 0xC6),
    ("tx_pwr_ht_mcs_1",        0x00A8, 1, 0xC6),
    ("tx_pwr_ht_mcs_2",        0x00A9, 1, 0xC6),
    ("tx_pwr_ht_mcs_3",        0x00AA, 1, 0xC6),
    ("tx_pwr_ht_mcs_4",        0x00AB, 1, 0xC6),
    ("tx_pwr_ht_mcs_5",        0x00AC, 1, 0xC6),
    ("tx_pwr_ht_mcs_6",        0x00AD, 1, 0xC6),
    ("ext_lna_rx_gain",        0x00C0, 1, 0x00),
    ("ext_lna_rx_nf",          0x00C1, 1, 0x00),
    ("ext_lna_rx_p1db",        0x00C2, 1, 0x00),
    ("ext_lna_bp_gain0",       0x00C3, 1, 0x00),
    ("ext_lna_bp_gain1",       0x00C4, 1, 0x00),
    ("ext_lna_bp_p1db",        0x00C5, 1, 0x00),
    ("step_num_neg_7",         0x00C6, 1, 0x00),
    ("step_num_neg_6",         0x00C7, 1, 0x00),
    ("step_num_neg_5",         0x00C8, 1, 0x00),
    ("step_num_neg_4",         0x00C9, 1, 0x1A),
    ("step_num_neg_3",         0x00CA, 1, 0x22),
    ("step_num_neg_2",         0x00CB, 1, 0x2A),
    ("step_num_neg_1",         0x00CC, 1, 0x31),
    ("step_num_neg_0",         0x00CD, 1, 0x35),
    ("step_num_ref",           0x00CE, 1, 0x01),
    ("step_num_temp",          0x00CF, 1, 0x35),
    ("step_num_pos_1",         0x00D0, 1, 0x39),
    ("step_num_pos_2",         0x00D1, 1, 0x40),
    ("step_num_pos_3",         0x00D2, 1, 0x46),
    ("step_num_pos_4",         0x00D3, 1, 0x4D),
    ("step_num_pos_5",         0x00D4, 1, 0x7F),
    ("step_num_pos_6",         0x00D5, 1, 0x7F),
    ("step_num_pos_7",         0x00D6, 1, 0x7F),
    ("eeprom_0xe0",            0x00E0, 16, 0x00),
    ("efuse_cp_ft_version",    0x00F0,  1, 0x00),
    ("eeprom_0xf2",            0x00F2,  1, 0x00),
    ("xtal_cal",               0x00F4,  1, 0xC0),
    ("xtal_trim2",             0x00F5,  1, 0x00),
    ("xtal_trim3",             0x00F6,  1, 0x00),
    ("efuse_xtal_wf_rfcal",    0x00F7,  1, 0x00),
    ("eeprom_0xf8",            0x00F8,  2, 0x0000),
    ("eeprom_0xfa",            0x00FA,  1, 0x00),
    ("eeprom_0x12e",           0x012E,  2, 0x0000),
    ("eeprom_0x130",           0x0130, 16, 0x00),
    ("eeprom_0x144",           0x0144,  2, 0x0000),
)


def build_factory(mac: bytes, overrides: dict[str, bytes], size: int) -> bytes:
    """Build a factory (WiFi EEPROM) blob for the MT7628AN.

    mac:       6-byte primary WiFi MAC address.
    overrides: per-register values from config.ini (key = register name, no 'wifi_' prefix).
               Any key absent from overrides uses the default value from _TABLE.
    size:      output buffer size in bytes (from the DTB eeprom nvmem cell).
    """
    eeprom = bytearray(b"\xff" * size)
    for name, offset, reg_size, default_int in _TABLE:
        val = overrides.get(name, default_int.to_bytes(reg_size, "little"))
        eeprom[offset : offset + reg_size] = val
    # WLAN MAC written from argument; MAC0 = primary+1, MAC1 = primary+3 (last octet).
    eeprom[0x004:0x00A] = mac
    eeprom[0x028:0x02E] = mac[:5] + bytes([(mac[5] + 1) & 0xFF])
    eeprom[0x02E:0x034] = mac[:5] + bytes([(mac[5] + 3) & 0xFF])
    return bytes(eeprom)
