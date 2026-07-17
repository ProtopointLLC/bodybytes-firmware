# WiFi EEPROM - MT7628AN

The MT7628AN WiFi subsystem has a dedicated on-chip MCU for RF control: TX power ramping, TSSI temperature compensation, crystal trim, and LNA configuration. These parameters are board- and silicon-specific, so they are stored in a 512-byte EEPROM blob that the driver loads at probe time.

On bodybytes and VoCore2 there is no physical EEPROM IC — the blob lives in the `factory` NOR partition, declared as an NVMEM cell in the device tree. `flash_nor_images.py` builds it on the fly from `config.ini` and `scripts/lib/wifi.py` (`build_factory()`), then writes it at the offset given by the DTB partition table.

At probe the driver reads the blob from NVMEM, optionally overwrites four bytes from on-chip OTP (see eFuse merge below), then forwards the offsets in `req_fields[]` (`mt7603/mcu.c`) to the MCU via `MT_CMD_LOAD_CR`. The **MCU** column: `Y` = in `req_fields[]`; **N** = consumed by the host driver only.

### eFuse merge

Enabled by `mediatek,eeprom-merge-otp` in the DT node (bodybytes has it), gated on `mt7603_has_cal_free_data()` verifying that **all** of the following OTP slots are non-zero:

| OTP sentinel | Offset | Role |
|---|---|---|
| `MT_EE_TEMP_SENSOR_CAL` | `0x055` | TEMP_SEN_CAL |
| `MT_EE_TX_POWER_0_START_2G` (16-bit) | `0x056` | TX0_PA_TSSI_LSB + MSB — sentinel only on MT7628, not merged |
| `MT_EE_TX_POWER_1_START_2G` (16-bit) | `0x05C` | TX1_PA_TSSI_LSB + MSB — sentinel only on MT7628, not merged |
| `MT_EE_CP_FT_VERSION` | `0x0F0` | efuse_cp_ft_version |
| `MT_EE_XTAL_FREQ_OFFSET` | `0x0F4` | XTAL_CAL |
| `MT_EE_XTAL_WF_RFCAL` | `0x0F7` | efuse_xtal_wf_rfcal |

If **any** sentinel is zero → no merge. If all pass → bytes at `0x055`, `0x0F0`, `0x0F4`, `0x0F7` are overwritten unconditionally (`eeprom[offset] = efuse[offset]`). The TX power fields are sentinels only; they are skipped in the actual copy on MT7628 (`n -= 4`).

On a production MT7628AN the OTP is fully programmed, so the merge always fires and those four NOR bytes have no runtime effect. A blank OTP (bare die) would skip the merge entirely.

## Register map

| Column | Meaning |
|--------|---------|
| **Register** | Field name. Backtick-formatted (`NAME`) if the register appears in the datasheet table; *italic* if reconstructed from driver source only. |
| **Offset** | Byte offset in the EEPROM blob (hex). |
| **Width** | Field size in bytes. |
| **Type** | `DC` = factory-programmed, do not change at runtime; `RW` = readable/writable by software; `UNK` = not in datasheet table. |
| **`config.ini` key** | `wifi_*` key used to override this field. All fields have one. |
| **Reset** | Default value written by `build_factory()` when no `config.ini` override is present, in little-endian hex bytes. DS=Y fields use the datasheet reset value; DS=**N** fields default to `0x00` unless a known-good value was read from the VoCore2 NOR backup. MAC fields are unconditionally overwritten by `--mac`; eFuse fields are unconditionally overwritten by the driver at probe. All EEPROM bytes not covered by any table entry are left at `0xFF` (the NOR flash erase value). |
| **VoCore2** | Actual value in the VoCore2 factory NOR backup (same MT7628AN SoC). *Default* = matches Reset; *Custom* = derived from device MAC; explicit hex = differs from Reset. |
| **Bodybytes** | Value produced by `build_factory()` for `[board:bodybytes]` in config.ini. *Default* = matches Reset; *Custom* = derived from `--mac`; explicit hex = overridden in config.ini. eFuse=**Y** fields show the NOR placeholder written; actual runtime value comes from OTP at probe. |
| **DS** | `Y` = in the datasheet register table; **N** = address-based / undocumented. |
| **eFuse** | `N` = NOR value used as-is; **Y** = driver unconditionally overwrites from on-chip OTP at every probe (`mt7603_apply_cal_free_data()`); NOR value is a placeholder only. |
| **MCU** | `Y` = byte(s) are in `req_fields[]` and forwarded to the on-chip MCU at probe via `MT_CMD_LOAD_CR`; **N** = consumed by the host driver only. |
| **Notes** | Additional context. |

| Register | Offset | Width | Type | `config.ini` key | Reset | VoCore2 | Bodybytes | DS | eFuse | MCU | Notes |
| -------- | :----: | :-: | :--: | ---------------- | ---: | -----: | -----: | :--: | :---: | :---: | ----- |
| `CHIP_ID` | `0x0000` | 2 | DC | `wifi_chip_id` | `28 76` | *Default* | *Default* | Y | N | **N** | Checked by `mt7603_check_eeprom()`; 16-bit LE value must equal `0x7628` (bytes `28 76` in memory) |
| `EEPROM_REV` | `0x0002` | 2 | DC | `wifi_eeprom_rev` | `00 02` | *Default* | *Default* | Y | N | **N** | Format version 0x0200 |
| `WLAN_MAC` | `0x0004` | 6 | RW | `wifi_wlan_mac` | `00 0c 43 e1 76 28` | *Custom* | *Custom* | Y | N | **N** | Primary MAC; overwritten by `build_factory()` from `--mac` |
| *eeprom_0x24* | `0x0024` | 2 | UNK | `wifi_eeprom_0x24` | `20 00` | *Default* | *Default* | **N** | N | Y | MCU init WORD; labeled unknown in driver |
| `MAC0` | `0x0028` | 6 | RW | `wifi_mac0` | `00 0c 43 e1 76 29` | *Custom* | *Custom* | Y | N | **N** | LAN MAC; primary MAC+1 (last octet); overwritten by `build_factory()` from `--mac` |
| `MAC1` | `0x002E` | 6 | RW | `wifi_mac1` | `00 0c 43 e1 76 2a` | *Custom* | *Custom* | Y | N | **N** | WAN MAC; primary MAC+3 (last octet); overwritten by `build_factory()` from `--mac` |
| `NIC_CONFG_0` | `0x0034` | 2 | RW | `wifi_nic_confg_0` | `22 34` | `11 34` | `11 34` | Y | N | Y | TX/RX path; byte[0] bits[7:4]=TX_PATH bits[3:0]=RX_PATH; `0x11`=1T1R |
| `NIC_CONFG_1` | `0x0036` | 2 | RW | `wifi_nic_confg_1` | `00 00` | `00 20` | *Default* | Y | N | Y | TSSI_COMP[13], ANT_DIV_CTRL[12:11], BW_40M_2P4G[8] (0=enable 40M), WF0/1_AUX[2:3], TX_POWER[1], HW_RADIO[0]; `0x2000`=TSSI_COMP only |
| `COUNTRY_REG` | `0x0039` | 1 | RW | `wifi_country_reg` | `ff` | *Default* | *Default* | Y | N | Y | BAND_2P4G[7:0] channel plan; 0=CH1-11, 1=CH1-13, 5=CH1-14; 0xFF (reset) = read from host/INF registry |
| *xtal_trim_1* | `0x003A` | 2 | UNK | `wifi_xtal_trim_1` | `00 01` | *Default* | *Default* | **N** | N | Y | MT_EE_XTAL_TRIM_1; byte[1] at `0x3b` = LED_MODE (reset `01`); only byte[1] sent to MCU |
| `NIC_CONFG_2` | `0x0042` | 2 | RW | `wifi_nic_confg_2` | `22 00` | *Default* | *Default* | Y | N | Y | TEMP_COMP_DIS[11], XTAL_OPT[10:9], ANT_DIV[8]; TX_STREAM[7:4], RX_STREAM[3:0]; `0x0022`=2T2R |
| `EXT_LNA_GAIN` | `0x0044` | 1 | RW | `wifi_ext_lna_gain` | `00` | *Default* | *Default* | Y | N | **N** | EXT_LNA_2P4G |
| `RSSI_OFST` | `0x0046` | 2 | RW | `wifi_rssi_ofst` | `00 00` | *Default* | *Default* | Y | N | **N** | byte[1]=RSSI1_OFST[15:8], byte[0]=RSSI0_OFST[7:0]; per-chain 2.4G RX RSSI correction |
| *rf_setting* | `0x0048` | 2 | UNK | `wifi_rf_setting` | `30 00` | *Default* | *Default* | **N** | N | Y | MT_EE_WIFI_RF_SETTING; only byte[0] sent to MCU |
| `TX_POWER_DELTA` | `0x0050` | 1 | RW | `wifi_tx_power_delta` | `82` | *Default* | *Default* | Y | N | Y | HT40 vs HT20 TX power delta; bit[7]=DELTA_EN, bit[6]=DELTA_INC, bits[5:0]=DELTA; `0x82`=enabled, -1 dBm |
| *tx_power_bw80_delta_hi* | `0x0053` | 1 | UNK | `wifi_tx_power_bw80_delta_hi` | `94` | *Default* | *Default* | **N** | N | Y | 5G BW80 delta; unused on MT7628 (2.4G only) |
| *tx_power_ext_pa_5g* | `0x0054` | 1 | UNK | `wifi_tx_power_ext_pa_5g` | `40` | *Default* | *Default* | **N** | N | Y | 5G ext-PA back-off; unused on MT7628 |
| `TEMP_SEN_CAL` | `0x0055` | 1 | RW | `wifi_temp_sen_cal` | `b0` | `b6` | *Default* | Y | **Y** | Y | TEMP_COMP_EN, THADC_SLOP; eFuse-merged at probe |
| `TX0_PA_TSSI_LSB` | `0x0056` | 1 | RW | `wifi_tx0_pa_tssi_lsb` | `c0` | *Default* | *Default* | Y | N | Y | calibration-free; bits[7:4]=TX0_TSSI_OFST[3:0], bits[3:0]=TX0_TSSI_SLOP |
| `TX0_PA_TSSI_MSB` | `0x0057` | 1 | RW | `wifi_tx0_pa_tssi_msb` | `cc` | `ca` | `ca` | Y | N | Y | calibration-free; TX0_TSSI_OFST[11:4]; `0xCA`=MT7628 A/N, `0xC8`=MT7628K |
| `TX0_POWER` | `0x0058` | 1 | RW | `wifi_tx0_power` | `23` | `1e` | *Default* | Y | N | Y | TX0 2.4G target power at 54 Mbps (dBm); base for `mt7603_init_txpower()` |
| `TX0_PWR_OFST_L` | `0x0059` | 1 | RW | `wifi_tx0_pwr_ofst_l` | `00` | `80` | *Default* | Y | N | Y | bit[7]=EN, bit[6]=INC, bits[5:0]=delta; TX0 CH1-5 power adjustment |
| `TX0_PWR_OFST_M` | `0x005A` | 1 | RW | `wifi_tx0_pwr_ofst_m` | `00` | `c0` | *Default* | Y | N | Y | TX0 CH6-10 power adjustment |
| `TX0_PWR_OFST_H` | `0x005B` | 1 | RW | `wifi_tx0_pwr_ofst_h` | `00` | `c0` | *Default* | Y | N | Y | TX0 CH11-14 power adjustment |
| `TX1_PA_TSSI_LSB` | `0x005C` | 1 | RW | `wifi_tx1_pa_tssi_lsb` | `40` | *Default* | *Default* | Y | N | Y | calibration-free; same bit layout as TX0_PA_TSSI_LSB |
| `TX1_PA_TSSI_MSB` | `0x005D` | 1 | RW | `wifi_tx1_pa_tssi_msb` | `cc` | `ca` | `ca` | Y | N | Y | calibration-free; TX1_TSSI_OFST[11:4]; `0xCA`=MT7628 A/N |
| `TX1_POWER` | `0x005E` | 1 | RW | `wifi_tx1_power` | `23` | `1e` | *Default* | Y | N | Y | TX1 2.4G target power at 54 Mbps (dBm) |
| `TX1_PWR_OFST_L` | `0x005F` | 1 | RW | `wifi_tx1_pwr_ofst_l` | `00` | `81` | *Default* | Y | N | Y | TX1 CH1-5 power adjustment |
| `TX1_PWR_OFST_M` | `0x0060` | 1 | RW | `wifi_tx1_pwr_ofst_m` | `00` | `c0` | *Default* | Y | N | Y | TX1 CH6-10 power adjustment |
| `TX1_PWR_OFST_H` | `0x0061` | 1 | RW | `wifi_tx1_pwr_ofst_h` | `00` | `c1` | *Default* | Y | N | Y | TX1 CH11-14 power adjustment |
| *eeprom_0x9e* | `0x009E` | 2 | UNK | `wifi_eeprom_0x9e` | `00 00` | *Default* | *Default* | **N** | N | Y | 5G chain-1 TSSI tail; unused on MT7628 |
| `TX_PWR_CCK_0` | `0x00A0` | 1 | RW | `wifi_tx_pwr_cck_0` | `c6` | *Default* | *Default* | Y | N | Y | CCK 1M/2M power offset; bit[7]=COMP_EN, bit[6]=INC, bits[5:0]=DELTA vs TX0_POWER; start of 14-byte rate block (0xA0–0xAD) |
| `TX_PWR_CCK_1` | `0x00A1` | 1 | RW | `wifi_tx_pwr_cck_1` | `c6` | *Default* | *Default* | Y | N | Y | CCK 5.5M/11M power offset |
| `TX_PWR_OFDM_0` | `0x00A2` | 1 | RW | `wifi_tx_pwr_ofdm_0` | `c6` | `c4` | *Default* | Y | N | Y | OFDM 6M/9M power offset |
| `TX_PWR_OFDM_1` | `0x00A3` | 1 | RW | `wifi_tx_pwr_ofdm_1` | `c6` | `c4` | *Default* | Y | N | Y | OFDM 12M/18M power offset |
| `TX_PWR_OFDM_2` | `0x00A4` | 1 | RW | `wifi_tx_pwr_ofdm_2` | `c6` | `c4` | *Default* | Y | N | Y | OFDM 24M/36M power offset |
| `TX_PWR_OFDM_3` | `0x00A5` | 1 | RW | `wifi_tx_pwr_ofdm_3` | `c6` | `c0` | *Default* | Y | N | Y | OFDM 48M power offset |
| `TX_PWR_OFDM_4` | `0x00A6` | 1 | RW | `wifi_tx_pwr_ofdm_4` | `c6` | `c0` | *Default* | Y | N | Y | OFDM 54M power offset |
| `TX_PWR_HT_MCS_0` | `0x00A7` | 1 | RW | `wifi_tx_pwr_ht_mcs_0` | `c6` | `c4` | *Default* | Y | N | Y | HT MCS=0/8 power offset |
| `TX_PWR_HT_MCS_1` | `0x00A8` | 1 | RW | `wifi_tx_pwr_ht_mcs_1` | `c6` | `c4` | *Default* | Y | N | Y | HT MCS=32 power offset (40MHz duplicate spatial stream) |
| `TX_PWR_HT_MCS_2` | `0x00A9` | 1 | RW | `wifi_tx_pwr_ht_mcs_2` | `c6` | `c4` | *Default* | Y | N | Y | HT MCS=1,2/9,10 power offset |
| `TX_PWR_HT_MCS_3` | `0x00AA` | 1 | RW | `wifi_tx_pwr_ht_mcs_3` | `c6` | `c4` | *Default* | Y | N | Y | HT MCS=3,4/11,12 power offset |
| `TX_PWR_HT_MCS_4` | `0x00AB` | 1 | RW | `wifi_tx_pwr_ht_mcs_4` | `c6` | `c4` | *Default* | Y | N | Y | HT MCS=5/13 power offset |
| `TX_PWR_HT_MCS_5` | `0x00AC` | 1 | RW | `wifi_tx_pwr_ht_mcs_5` | `c6` | `c0` | *Default* | Y | N | Y | HT MCS=6/14 power offset |
| `TX_PWR_HT_MCS_6` | `0x00AD` | 1 | RW | `wifi_tx_pwr_ht_mcs_6` | `c6` | `c0` | *Default* | Y | N | Y | HT MCS=7/15 power offset; end of 14-byte rate block |
| `EXT_LNA_RX_GAIN` | `0x00C0` | 1 | RW | `wifi_ext_lna_rx_gain` | `00` | *Default* | *Default* | Y | N | Y | ext LNA gain; active only when NIC_CONFG_1 WF0/1_AUX set; no ext LNA on bodybytes |
| `EXT_LNA_RX_NF` | `0x00C1` | 1 | RW | `wifi_ext_lna_rx_nf` | `00` | *Default* | *Default* | Y | N | Y | ext LNA noise figure |
| `EXT_LNA_RX_P1DB` | `0x00C2` | 1 | RW | `wifi_ext_lna_rx_p1db` | `00` | *Default* | *Default* | Y | N | Y | ext LNA RX P1dB compression point |
| `EXT_LNA_BP_GAIN0` | `0x00C3` | 1 | RW | `wifi_ext_lna_bp_gain0` | `00` | *Default* | *Default* | Y | N | Y | ext LNA bypass RX gain 0 |
| `EXT_LNA_BP_GAIN1` | `0x00C4` | 1 | RW | `wifi_ext_lna_bp_gain1` | `00` | *Default* | *Default* | Y | N | Y | ext LNA bypass RX gain 1 |
| `EXT_LNA_BP_P1DB` | `0x00C5` | 1 | RW | `wifi_ext_lna_bp_p1db` | `00` | *Default* | *Default* | Y | N | Y | ext LNA bypass P1dB |
| `STEP_NUM_NEG_7` | `0x00C6` | 1 | RW | `wifi_step_num_neg_7` | `00` | *Default* | *Default* | Y | N | Y | TSSI temp-comp step table (start) |
| `STEP_NUM_NEG_6` | `0x00C7` | 1 | RW | `wifi_step_num_neg_6` | `00` | *Default* | *Default* | Y | N | Y |  |
| `STEP_NUM_NEG_5` | `0x00C8` | 1 | RW | `wifi_step_num_neg_5` | `00` | *Default* | *Default* | Y | N | Y |  |
| `STEP_NUM_NEG_4` | `0x00C9` | 1 | RW | `wifi_step_num_neg_4` | `1a` | *Default* | *Default* | Y | N | Y |  |
| `STEP_NUM_NEG_3` | `0x00CA` | 1 | RW | `wifi_step_num_neg_3` | `22` | *Default* | *Default* | Y | N | Y |  |
| `STEP_NUM_NEG_2` | `0x00CB` | 1 | RW | `wifi_step_num_neg_2` | `2a` | *Default* | *Default* | Y | N | Y |  |
| `STEP_NUM_NEG_1` | `0x00CC` | 1 | RW | `wifi_step_num_neg_1` | `31` | *Default* | *Default* | Y | N | Y |  |
| `STEP_NUM_NEG_0` | `0x00CD` | 1 | RW | `wifi_step_num_neg_0` | `35` | *Default* | *Default* | Y | N | Y |  |
| `STEP_NUM_REF` | `0x00CE` | 1 | RW | `wifi_step_num_ref` | `01` | *Default* | *Default* | Y | N | Y | 2.4G TSSI calibration reference step anchor |
| `STEP_NUM_TEMP` | `0x00CF` | 1 | RW | `wifi_step_num_temp` | `35` | *Default* | *Default* | Y | N | Y | 2.4G reference temperature for TSSI temp-comp step table |
| `STEP_NUM_POS_1` | `0x00D0` | 1 | RW | `wifi_step_num_pos_1` | `39` | *Default* | *Default* | Y | N | Y |  |
| `STEP_NUM_POS_2` | `0x00D1` | 1 | RW | `wifi_step_num_pos_2` | `40` | *Default* | *Default* | Y | N | Y |  |
| `STEP_NUM_POS_3` | `0x00D2` | 1 | RW | `wifi_step_num_pos_3` | `46` | *Default* | *Default* | Y | N | Y |  |
| `STEP_NUM_POS_4` | `0x00D3` | 1 | RW | `wifi_step_num_pos_4` | `4d` | *Default* | *Default* | Y | N | Y |  |
| `STEP_NUM_POS_5` | `0x00D4` | 1 | RW | `wifi_step_num_pos_5` | `7f` | *Default* | *Default* | Y | N | Y |  |
| `STEP_NUM_POS_6` | `0x00D5` | 1 | RW | `wifi_step_num_pos_6` | `7f` | *Default* | *Default* | Y | N | Y |  |
| `STEP_NUM_POS_7` | `0x00D6` | 1 | RW | `wifi_step_num_pos_7` | `7f` | *Default* | *Default* | Y | N | Y | End of 17-byte step table |
| *eeprom_0xe0* | `0x00E0` | 16 | UNK | `wifi_eeprom_0xe0` | `00 ×16` | `11 1d 11 1d 1c 35 1c 35 1e 35 1e 35 17 19 17 19` | *Default* | **N** | N | **N** | Undocumented; 4 WORD pairs suggest 4 channel groups × 2 chains |
| *efuse_cp_ft_version* | `0x00F0` | 1 | UNK | `wifi_efuse_cp_ft_version` | `00` | `02` | *Default* | **N** | **Y** | **N** | Chip-probe/final-test revision; eFuse-merged at probe |
| *eeprom_0xf2* | `0x00F2` | 1 | UNK | `wifi_eeprom_0xf2` | `00` | *Default* | *Default* | **N** | N | Y | MT_EE_TX_POWER_TSSI_OFF; guard `ext_pa && is_mt7603()` is always false on MT7628 |
| `XTAL_CAL` | `0x00F4` | 1 | RW | `wifi_xtal_cal` | `c0` | `bc` | *Default* | Y | **Y** | Y | bit[7]=XTAL_CAP_VLD (0=use ROM default), bits[6:0]=XTAL_CAP; calibration-free; eFuse-merged at probe |
| `XTAL_TRIM2` | `0x00F5` | 1 | RW | `wifi_xtal_trim2` | `00` | `8e` | *Default* | Y | N | Y | bit[7]=EN, bit[6]=DEC (0=increase), bits[5:0]=delta; customer re-trim on top of XTAL_CAL |
| `XTAL_TRIM3` | `0x00F6` | 1 | RW | `wifi_xtal_trim3` | `00` | `80` | *Default* | Y | N | Y | bit[7]=EN, bit[6]=DEC, bits[5:0]=delta; second re-trim; final_cap=0xF4[6:0]±trim2[5:0]±trim3[5:0] |
| *efuse_xtal_wf_rfcal* | `0x00F7` | 1 | UNK | `wifi_efuse_xtal_wf_rfcal` | `00` | `88` | *Default* | **N** | **Y** | Y | WiFi RF calibration word; eFuse-merged at probe |
| *eeprom_0xf8* | `0x00F8` | 2 | UNK | `wifi_eeprom_0xf8` | `00 00` | `0a 00` | *Default* | **N** | N | Y | MCU WORD; labeled unknown in driver |
| *eeprom_0xfa* | `0x00FA` | 1 | UNK | `wifi_eeprom_0xfa` | `00` | *Default* | *Default* | **N** | N | Y | unknown |
| *eeprom_0x12e* | `0x012E` | 2 | UNK | `wifi_eeprom_0x12e` | `00 00` | `77 00` | *Default* | **N** | N | Y | byte[0] only sent to MCU; byte[1] read by host driver only |
| *eeprom_0x130* | `0x0130` | 16 | UNK | `wifi_eeprom_0x130` | `00 *16` | `11 1d 11 1d 15 7f 15 7f 17 7f 17 7f 10 3b 10 3b` | *Default* | **N** | N | Y | 8 WORDs; undocumented; similar WORD-pair structure to eeprom_0xe0 |
| *eeprom_0x144* | `0x0144` | 2 | UNK | `wifi_eeprom_0x144` | `00 00` | `11 00` | *Default* | **N** | N | **N** | Undocumented |

---

## Decoded VoCore2 calibration

This section decodes every field where the VoCore2 NOR backup differs from the datasheet reset. VoCore2 is used as the bodybytes baseline because both boards share the same MT7628AN. Fields with eFuse=**Y** are overwritten at probe; their NOR values are chip-specific placeholders, recorded here for completeness.

### RF/antenna configuration

**`NIC_CONFG_0`** `22 34` → `11 34`

byte[0] = TX_PATH[7:4] / RX_PATH[3:0]. Reset `0x22` = 2T2R; VoCore2 `0x11` = 1T1R (WF0 only).

VoCore2 routes WF0 to an on-board ceramic SMT antenna and WF1 to a U.FL connector. The stock image ships 1T1R; the vendor `ant2.sh` mod patches byte[0] from `0x11` → `0x22` to enable 2T2R — no other EEPROM field is touched, and the TX1 calibration values in the backup become active only after the mod. The NOR backup here is the stock 1T1R image.

byte[1] `0x34` unchanged (undocumented MCU init flags).

**`NIC_CONFG_1`** `00 00` → `00 20`

`0x0000` → `0x2000`: bit 13 (TSSI_COMP) set, enabling TSSI-based TX-power temperature compensation. All other bits remain 0: 40 MHz BW enabled, no antenna diversity, no HW radio GPIO.

### TX chain calibration

**`TX0_PA_TSSI_MSB` / `TX1_PA_TSSI_MSB`** `cc` → `ca`

TSSI_OFST[11:4]. Datasheet: `0xCA` for MT7628 A/N, `0xC8` for MT7628K; reset `0xCC` is an uncalibrated placeholder. Both boards are MT7628 A/N, so `0xCA` is correct for both chains.

**`TX0_POWER` / `TX1_POWER`** `23` → `1e`

Target TX power at 54 Mbps. Reduced from reset 35 (`0x23`) to 30 (`0x1E`); all per-channel and per-rate offsets are relative to this ceiling.

**`TX0_PWR_OFST_L`** `00` → `80`

`0x80` = {EN=1, INC=0, OFST=0} → CH1–5: **0 dBm**. Reset `0x00` has EN=0 (layer disabled). VoCore2 arms the per-channel path at zero delta, leaving it ready to tune per-board.

**`TX0_PWR_OFST_M`** `00` → `c0`

`0xC0` = {EN=1, INC=1, OFST=0} → CH6–10: **0 dBm**. INC direction irrelevant at OFST=0.

**`TX0_PWR_OFST_H`** `00` → `c0`

CH11–14: **0 dBm**. Same as TX0_PWR_OFST_M.

**`TX1_PWR_OFST_L`** `00` → `81`

`0x81` = {EN=1, INC=0, OFST=1} → CH1–5 TX1: **−0.5 dBm**. Per-chain RF path asymmetry on the VoCore2 PCB.

**`TX1_PWR_OFST_M`** `00` → `c0`

CH6–10 TX1: **0 dBm**. Same as TX0.

**`TX1_PWR_OFST_H`** `00` → `c1`

`0xC1` = {EN=1, INC=1, OFST=1} → CH11–14 TX1: **+0.5 dBm**; compensates roll-off on TX1.

### Per-rate TX power profile

All rate-power bytes: bit[7]=COMP_EN, bit[6]=INC, bits[5:0]=DELTA (0.5 dBm/step). Deltas below are relative to TX_POWER = 30 (`0x1E`).

| Rate group | Register(s) | Reset | VoCore2 | Decoded delta |
|---|---|---|---|---|
| CCK 1M/2M | `TX_PWR_CCK_0` | `c6` | `c6` *(unchanged)* | +3 dBm |
| CCK 5.5M/11M | `TX_PWR_CCK_1` | `c6` | `c6` *(unchanged)* | +3 dBm |
| OFDM 6M/9M | `TX_PWR_OFDM_0` | `c6` | `c4` | +2 dBm |
| OFDM 12M/18M | `TX_PWR_OFDM_1` | `c6` | `c4` | +2 dBm |
| OFDM 24M/36M | `TX_PWR_OFDM_2` | `c6` | `c4` | +2 dBm |
| OFDM 48M | `TX_PWR_OFDM_3` | `c6` | `c0` | 0 dBm |
| OFDM 54M | `TX_PWR_OFDM_4` | `c6` | `c0` | 0 dBm |
| HT MCS=0/8 through MCS=5/13 | `TX_PWR_HT_MCS_0`–`_4` | `c6` | `c4` | +2 dBm |
| HT MCS=6/14, 7/15 | `TX_PWR_HT_MCS_5`–`_6` | `c6` | `c0` | 0 dBm |

Standard power-taper: lower rates carry extra headroom; higher rates needing better EVM back off to the TX_POWER baseline. VoCore2 places the high-rate ceiling 3 dBm below the datasheet reset.

### Crystal frequency calibration

**`XTAL_CAL`** `c0` → `bc` *(eFuse=**Y**, NOR value overwritten at probe)*

`0xC0` = {VLD=1, CAP=64} → `0xBC` = {VLD=1, CAP=60}: lower cap reduces crystal load, pulling frequency higher. Chip-specific; the driver replaces it from OTP at every probe.

**`XTAL_TRIM2`** `00` → `8e`

`0x8E` = {EN=1, DEC=0, delta=14}: +14 cap steps on top of XTAL_CAL. The VoCore2 needed a +14-step customer re-trim after factory calibration.

**`XTAL_TRIM3`** `00` → `80`

`0x80` = {EN=1, DEC=0, delta=0}: armed but contributes zero delta — reserved for a second correction pass. Effective: OTP_cap + 14.

### eFuse placeholder fields

In-NOR snapshots of OTP values at VoCore2 production time. The driver overwrites these from OTP at probe; informational only.

| Field | NOR value | Meaning |
|---|---|---|
| `TEMP_SEN_CAL` | `b6` (vs reset `b0`) | THADC_SLOP = 54 (vs reset 48); per-chip temperature-ADC sensitivity calibration code |
| `efuse_cp_ft_version` | `02` (vs reset `00`) | Chip-probe/FT revision = 2; per-lot OTP version stamp |
| `efuse_xtal_wf_rfcal` | `88` (vs reset `00`) | WiFi RF calibration word programmed at MTK factory test |

### Undocumented blobs

**`eeprom_0xe0`** zeros → `11 1d 11 1d 1c 35 1c 35 1e 35 1e 35 17 19 17 19`

8 LE WORDs in 4 duplicate pairs: `(0x1D11, 0x1D11, 0x351C, 0x351C, 0x351E, 0x351E, 0x1917, 0x1917)`. Structure suggests a 4-channel-group table, two values per group (low/high bound or per-chain ceiling). Unconfirmed.

**`eeprom_0xf8`** `00 00` → `0a 00`

16-bit LE value = 10. Forwarded to the MCU at probe; purpose unknown.

**`eeprom_0x12e`** `00 00` → `77 00`

16-bit LE value = 119 (`0x77`). byte[0] forwarded to MCU; byte[1] used by the host driver only. Purpose unknown.

**`eeprom_0x130`** zeros → `11 1d 11 1d 15 7f 15 7f 17 7f 17 7f 10 3b 10 3b`

8 WORDs: `(0x1D11, 0x1D11, 0x7F15, 0x7F15, 0x7F17, 0x7F17, 0x3B10, 0x3B10)`. First pair matches `eeprom_0xe0`; `0x7F` bytes in the remaining pairs suggest saturation markers. Likely a second channel-group power table for a different rate class or bandwidth.

**`eeprom_0x144`** `00 00` → `11 00`

16-bit LE value = 17 (`0x11`). Undocumented; host-driver only (MCU=**N**).

---

## Bodybytes WiFi configuration profile

### Antenna

The bodybytes board uses the **Antenova Serica SR4W035** — a 2.4 GHz SMD chip antenna.

### RF path

**WF0\_RFION/P\_1/2** connects to the SR4W035; **WF1\_RFION/P is not routed** — 2T2R is impossible regardless of EEPROM settings. NIC\_CONFG\_0 = `11 34` (1T1R). TX1 registers are forwarded to the MCU via `req_fields[]` but are irrelevant with the chain gated off; reset values serve as neutral placeholders.

### Register values

`[board:bodybytes]` uses reset values for all TX power and channel-offset registers — no bodybytes RF measurements exist yet. Only the silicon-variant TSSI codes (`TX0/1_PA_TSSI_MSB = ca`) are carried from VoCore2.

**Fields identical to VoCore2 — rationale for keeping them:**

| Register(s) | Value | Rationale |
|---|---|---|
| `NIC_CONFG_0` | `11 34` | 1T1R, WF0 only — matches bodybytes RF routing |
| `TX0_PA_TSSI_MSB`, `TX1_PA_TSSI_MSB` | `ca` | MT7628 A/N silicon variant code — die-level, not board-specific; reset `0xCC` is an uncalibrated placeholder |
| `TX_POWER_DELTA` | `82` | HT40 vs HT20 −1 dBm back-off — standard for any 2T2R/1T1R MT7628 |

**Fields that require bodybytes RF measurement before finalisation:**

| Register(s) | Current value | What to measure / update |
|---|---|---|
| `NIC_CONFG_1` | Reset (`00 00`, TSSI off) | Enable TSSI_COMP (`00 20`) once `TX0_POWER` is calibrated — closed-loop regulation against an uncalibrated target is worse than open-loop |
| `TX0_POWER` | Reset (`23`) | Set conducted TX power ceiling for the SR4W035 + matching circuit; measure at 54 Mbps and reduce until EVM passes and regulatory conducted limit is met |
| `TX0_PWR_OFST_L/M/H` | Reset (`00`) | Per-channel flatness; sweep CH1, CH6, CH11, CH14 and add per-range correction if any group deviates from mid-band by more than ±1 dB |
| `TX1_POWER`, `TX1_PWR_OFST_*` | Reset — WF1 unconnected, no measurement needed | |
| `TX_PWR_OFDM_*`, `TX_PWR_HT_MCS_*` | Reset (`c6` for all) | Per-rate power taper; measure EVM at each rate group and reduce toward baseline where EVM is marginal |
| `XTAL_TRIM2`, `XTAL_TRIM3` | Reset (EN=0) | Measure crystal frequency vs 40.000 MHz reference after eFuse XTAL_CAL is applied at first boot; set TRIM2 if error > ±20 ppm, TRIM3 for a second correction pass |

### Calibration procedure (once RF bench is available)

1. Flash the factory blob and verify association on CH6 (mid-band) — confirms the EEPROM structure is accepted by the driver.

2. Connect a power sensor to the matching-circuit test point and measure conducted TX power at 54 Mbps. `TX0_POWER` is the target in dBm at 54 Mbps (§ 2.15). Adjust `wifi_tx0_power` until the level meets the budget (regulatory EIRP − SR4W035 average gain − trace/matching loss). Confirm `wifi_tx0_pa_tssi_msb` ≠ `0xFF` — the driver treats `0xFF` as an invalid TSSI sentinel and silently disables TSSI feedback. Then set `wifi_nic_confg_1 = 00 20` to enable TSSI_COMP closed-loop regulation to this calibrated target.

3. Sweep CH1, CH6, CH11, CH14 and record power deviation from the CH6 reference. For any group outside ±1 dB, update the corresponding channel-offset register (`wifi_tx0_pwr_ofst_l/m/h`). Field encoding: `bit[7]=EN, bit[6]=INC (0=decrease, 1=increase), bits[5:0]=delta`; 1 step ≈ 0.5 dBm. Examples: `0x83`=−1.5 dB, `0x80`=0 dB, `0xC3`=+1.5 dB.

4. Measure EVM at each rate group (CCK, OFDM 6–54M, HT MCS). Reduce the corresponding `wifi_tx_pwr_*` register where EVM is marginal, working highest-rate first. Field encoding: `bit[7]=COMP_EN, bit[6]=INC (0=decrease), bits[5:0]=delta`; 1 step = 0.5 dBm relative to `TX0_POWER`. Examples: `0x82`=−1 dBm, `0xC2`=+1 dBm, `0xC3`=+1.5 dBm, `0xC0`=0 dBm.

5. Verify HT40 TX power on the primary channel at MCS=7. `TX_POWER_DELTA = 0x82` (`DELTA_EN=1, DELTA_INC=0, DELTA=2`) applies an automatic −1 dBm de-rating for 40 MHz vs 20 MHz; increase DELTA if more headroom is needed to meet the regulatory EIRP limit at HT40.

6. Measure crystal frequency deviation (skip if XO tolerance is within spec). If error >±20 ppm after eFuse XTAL_CAL applies, set `wifi_xtal_trim2`; use `wifi_xtal_trim3` for a second pass. Each step ≈1–2 ppm. The TSSI temperature-compensation step table (`STEP_NUM_*`, `0x00C6`–`0x00D6`) uses datasheet default values and does not require remeasurement unless TSSI_COMP is active and temperature-induced drift is observed at production extremes.
