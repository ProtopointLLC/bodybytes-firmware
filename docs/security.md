# Security Model

Bodybytes is an owner-controlled embedded platform. Its security model intentionally differs from a locked consumer appliance: the manufacturer provides a recoverable baseline, while the device owner controls operational credentials, software images, and persistent-data policy.

For implementation details, see [openwrt.md](openwrt.md), [uboot.md](uboot.md), and [flashing.md](flashing.md).

## 1 - Security principles

### Owner controls the device

The owner is permitted to build and install modified software images. Bodybytes therefore does **not** enforce a manufacturer-controlled secure-boot or firmware-signing chain.

Unsigned firmware is intentional. A user who replaces the supplied firmware is exercising an intended capability, not bypassing a security control.

The supplied bootloader still performs structural and bounds checks when loading images; these checks protect against malformed or corrupt images, not against intentionally installed third-party software. See [uboot.md](uboot.md).

### Owner controls operational secrets

Firmware and manufacturing use documented default credentials for a deterministic commissioning state; see [§4 - Credential model](#4---credential-model) for why these are public values, not secrets.

The manufacturer does not generate, receive, escrow, or retain the customer's operational passwords or encryption keys — see [§3 - Manufacturer](#3---party-responsibilities) for the full division of responsibility. Credential diversification is a required customer provisioning step before operational use.

### Owner controls persistent-data policy

The eMMC `data` partition is provisioned separately from the normal firmware update path and uses ordinary, unencrypted ext4 by default. See [§5 - Firmware and update policy](#5---firmware-and-update-policy) for why updates never recreate it, and [§6 - Data confidentiality](#6---data-confidentiality) for what an owner enabling encryption is responsible for.

### Recovery remains available

The platform favors recoverability over vendor lock-in: a NOR-resident recovery image remains independent of the normal eMMC installation, and failed normal boots or a physical trigger fall back to it. See [§2 - Recovery](#recovery) for what the privileged recovery environment can do.

## 2 - Trust boundaries

### Manufacturing and initial flashing

The manufacturer is responsible for producing and flashing the documented baseline firmware and board-specific data.

SPI NOR contains boot/recovery state and WiFi calibration/factory data. The normal operating system resides on eMMC. The normal OpenWrt image exposes all NOR partitions read-only, reducing the chance that a compromised or misconfigured normal system accidentally damages its boot/recovery state.

The normal path for manufacturing NOR programming is JTAG using `scripts/flash_nor_images.py`. See [flashing.md](flashing.md).

Manufacturing credentials and documented firmware defaults are commissioning values only — see [§4 - Commissioning defaults](#commissioning-defaults).

### Customer provisioning

Delivery transfers responsibility for operational authentication to the customer.

A device is **not provisioned for operational use** until the customer has changed the applicable default credentials and verified access using the new credentials.

The customer is responsible for keeping those credentials secure and for retaining whatever recovery information their own configuration requires.

The manufacturer is not expected to know customer-selected operational credentials.

### Normal operation

The normal firmware operates primarily as a standalone WiFi AP. Access to services is therefore bounded first by membership of the device's WLAN.

The supplied WLAN uses WPA2/WPA3 mixed SAE. Once the customer has diversified the WLAN key, access to services such as `/public` must be understood in that context: `/public` is intentionally unauthenticated at the application layer, but is normally reachable only after joining the device network.

`/public` is intentionally read-write without a dufs login. `/protected` requires a dufs login. Samba exposes the data share read-write. These are product behaviors, not substitutes for WLAN access control. See [README.md](../README.md) and [openwrt.md](openwrt.md).

If Travelmate is configured, the uplink is treated as WAN rather than extending the trusted LAN boundary to the upstream network. See [openwrt.md](openwrt.md).

### Normal-system root

Root access to the normal OpenWrt installation grants full control over that installation and the accessible eMMC data.

It does not, by default, grant a normal process write access to SPI NOR. All NOR partitions are marked read-only and the normal image does not include the `kmod-mtd-rw` provisioning escape hatch.

This is a damage-containment boundary, not a cryptographic trust boundary. A sufficiently capable owner with physical access is intentionally able to replace software.

### Recovery

Recovery is a privileged maintenance environment selected through physical interaction at boot. It is designed to remain usable when the normal eMMC installation is broken.

Recovery uses documented fixed recovery credentials, kept intentionally distinct from customer secrets — see [§4 - Recovery credentials](#recovery-credentials). The recovery security boundary is therefore physical: the ability to reboot the device, activate its recovery trigger, and access the recovery WLAN.

Recovery includes `bodybytes-provision` and `kmod-mtd-rw`. These permit deliberate changes to MAC/branding/NOR state and eMMC repartitioning. They must be treated as administrative/destructive capabilities.

See [openwrt.md](openwrt.md#spi-nor-flash---spi0) and [flashing.md](flashing.md).

### JTAG and direct hardware access

JTAG/manufacturing access is outside the normal software security boundary. A party with suitable physical access and equipment can inspect or replace low-level firmware.

This is consistent with the owner-control model. Bodybytes does not claim that manufacturer firmware remains authoritative against an owner or attacker with unrestricted physical hardware access.

## 3 - Party responsibilities

### Manufacturer

The manufacturer is responsible for:

- flashing the intended baseline firmware and board-specific data;
- verifying the manufacturing flash operation according to the documented flashing process;
- supplying a functional NOR recovery environment;
- maintaining separation between normal eMMC firmware and the NOR recovery path;
- documenting default commissioning credentials;
- documenting the requirement for customer credential diversification;
- identifying the firmware/source revision associated with released builds;
- documenting known material firmware limitations and recovery procedures;
- not representing default commissioning credentials as customer-specific secrets.

The manufacturer is **not** responsible for:

- choosing or retaining customer operational passwords;
- retaining recovery copies of customer passwords;
- generating or retaining customer data-encryption keys;
- guaranteeing confidentiality of a customer-created encrypted volume when its keys are lost or disclosed;
- preserving manufacturer firmware after an owner deliberately installs another software image;
- guaranteeing the security properties of owner-modified firmware or packages.

### Customer / device owner

Before operational use, the customer is responsible for:

- changing all applicable documented commissioning credentials;
- selecting sufficiently strong operational credentials;
- verifying that the new credentials work and that the documented defaults no longer provide normal operational access;
- securely retaining credentials required for their intended use;
- deciding whether the supplied unencrypted data partition meets their confidentiality requirements;
- implementing and managing storage encryption if required;
- understanding that `/public` is intentionally writable without an additional dufs login by clients that can reach the service;
- reviewing any additional services or packages they install;
- accepting responsibility for the behavior and security of self-built or third-party firmware images.

When modifying firmware, partitioning, boot configuration, or NOR state, the owner is also responsible for maintaining a viable recovery path appropriate to their changes.

### Firmware contributors

Contributors should preserve the documented boundaries unless a change explicitly revises the security model.

In particular, changes should not silently:

- make SPI NOR writable from the normal image;
- add provisioning-only tooling to the normal image;
- recreate or format the `data` partition during ordinary firmware upgrade;
- introduce manufacturer custody of customer operational secrets;
- require manufacturer authorization to boot owner-built firmware;
- expose LAN administration services through a configured WAN/uplink interface;
- change default or recovery credentials without updating the provisioning documentation.

## 4 - Credential model

### Commissioning defaults

Documented default credentials exist so a newly flashed device has a known initial state.

They are public information and must be assumed known to anyone who can read the repository or product documentation.

They provide convenience during manufacturing and commissioning only.

See [README.md](../README.md) and [openwrt.md](openwrt.md) for the currently configured defaults.

### Operational credentials

Operational credentials are selected by the customer after delivery.

The manufacturer should neither require disclosure of these credentials nor request them during ordinary support. If troubleshooting requires temporary access, credential handling should be agreed explicitly with the customer and the customer should rotate any credential disclosed for that purpose afterward.

### Recovery credentials

Recovery credentials are intentionally distinct from customer operational secrets. Their purpose is deterministic access to the physical recovery environment.

They should not be reused as operational WLAN, root, Samba, dufs, or other customer credentials.

## 5 - Firmware and update policy

Bodybytes does not require manufacturer signatures on bootable software — see [§1 - Owner controls the device](#owner-controls-the-device) for what the supplied structural/bounds checks do and do not protect against.

Normal sysupgrade updates the firmware partitions while preserving the separate `data` partition; firmware updates never recreate it. See [flashing.md](flashing.md) and [openwrt.md](openwrt.md#2---sysupgrade).

## 6 - Data confidentiality

The supplied `data` partition is not encrypted by default — see [§1 - Owner controls persistent-data policy](#owner-controls-persistent-data-policy) for how it is provisioned and preserved across updates.

This means the default firmware does not claim confidentiality of stored data against unrestricted physical storage access or a party that obtains sufficient system privileges. An owner may replace the supplied filesystem with an encrypted design instead.

If the owner enables encryption, the owner assumes responsibility for:

- selecting the encryption technology and configuration;
- generating keys or passphrases;
- secure key storage;
- backup and recovery;
- ensuring the chosen boot/mount integration continues to work after firmware changes;
- accepting permanent data loss if required keys become unavailable.

## 7 - Service exposure

The supplied firmware provides local administration and file-sharing services; see [README.md](../README.md) for the current service summary and [§2 - Normal operation](#normal-operation) for the WLAN trust boundary and the per-path dufs/Samba access model.

Samba and dufs currently write shared data with root ownership to avoid cross-writer ownership inconsistencies. This increases the consequence of a vulnerability in those services and should be treated as a defense-in-depth consideration when adding or exposing additional services.

Owners who substantially change firewall rules, Travelmate/uplink behavior, service bind addresses, or network topology are responsible for reassessing which services become reachable from untrusted networks.

## 8 - TLS

The supplied firmware generates device-local TLS material on first boot rather than shipping a universal TLS private key.

TLS protects traffic to the device after the client has established trust in the device certificate. Users remain responsible for verifying that they are trusting the intended device.

See [README.md](../README.md) and [openwrt.md](openwrt.md) for certificate and service configuration details.

## 9 - Provisioning checklists

### Manufacturer / flashing checklist

- [ ] Record the hardware/unit identifier used for manufacturing traceability.
- [ ] Record the exact `bodybytes-firmware` revision used.
- [ ] Record the pinned U-Boot and OpenWrt submodule revisions.
- [ ] Build using the documented environment in [building.md](building.md).
- [ ] Flash NOR using the documented procedure in [flashing.md](flashing.md).
- [ ] Confirm flash verification completes successfully.
- [ ] Confirm the expected MAC/factory data is present.
- [ ] Confirm the expected `branding` value is present.
- [ ] Confirm NOR recovery boots.
- [ ] Provision/format eMMC using the documented first-install procedure.
- [ ] Install the intended baseline OpenWrt image.
- [ ] Confirm normal eMMC boot succeeds.
- [ ] Confirm the device WLAN is visible and accepts the documented commissioning credentials.
- [ ] Confirm LuCI is reachable.
- [ ] Confirm the data partition is mounted.
- [ ] Confirm expected Samba/dufs functionality.
- [ ] Confirm a reboot returns to the normal system.
- [ ] Deliver the device with an explicit notice that commissioning credentials are public defaults and must be changed before operational use.
- [ ] Do **not** choose or retain the customer's operational credentials.

### Customer / mandatory pre-use checklist

A device should not be considered commissioned until this checklist is complete.

- [ ] Connect directly to the Bodybytes WLAN using the documented commissioning credentials.
- [ ] Change the normal root/admin password.
- [ ] Change the normal WLAN key.
- [ ] Change the default dufs `/protected` credentials.
- [ ] Change any other enabled service credential that still uses a documented commissioning default.
- [ ] Reconnect using the new WLAN credentials.
- [ ] Verify administrative login using the new root/admin credential.
- [ ] Verify the documented commissioning credentials no longer grant normal operational access where they were required to be changed.
- [ ] Verify the intended dufs access policy: `/public` is intentionally read-write without an application login; `/protected` requires the newly selected credentials.
- [ ] Decide whether the default unencrypted `data` filesystem (mounted at `/mnt/data`) is acceptable for the intended data.
- [ ] If encryption is required, configure it **before storing sensitive data** and establish the owner's own key backup/recovery procedure.
- [ ] Store operational credentials and any encryption recovery material according to the owner's security requirements.
- [ ] Confirm the owner understands how to enter recovery mode and that recovery uses documented recovery credentials rather than the customer's normal credentials.
- [ ] Confirm the owner understands that installing custom firmware may change or remove the security and recovery properties described in this document.

### Optional owner hardening checklist

- [ ] Remove or disable services that are not required.
- [ ] Review `/public` availability if anonymous application-level write access is not desired.
- [ ] Review firewall rules after enabling or modifying Travelmate/uplink connectivity.
- [ ] Use unique credentials rather than reusing credentials from other systems.
- [ ] Configure encrypted persistent storage if physical data confidentiality is required.
- [ ] Keep a known-good firmware/recovery build and its source revision available before experimenting with custom images.
- [ ] Review installed third-party packages and custom services for network exposure and privilege level.
- [ ] Re-run relevant security checks after substantial firmware, partition, firewall, or service changes.

### Firmware update checklist

- [ ] Back up data that cannot be replaced.
- [ ] Record the currently running firmware revision/configuration.
- [ ] Confirm the update image is intended for Bodybytes.
- [ ] Follow the currently documented update procedure in [flashing.md](flashing.md).
- [ ] Do not repartition or format `data` as part of a routine firmware update.
- [ ] After reboot, verify normal boot completed successfully.
- [ ] Verify WLAN and administrative access.
- [ ] Verify the data partition remains mounted and expected data is present.
- [ ] Verify file-sharing services required by the owner.
- [ ] Verify any owner-added encryption/mount integration still functions.
- [ ] If normal boot fails repeatedly, use the documented NOR recovery path.

### Recovery / reprovisioning checklist

Recovery operations can destroy data or modify boot-critical state.

- [ ] Determine whether existing data must be backed up before making destructive changes.
- [ ] Enter recovery using the documented physical recovery procedure.
- [ ] Confirm that the device is actually running the recovery profile before using provisioning commands.
- [ ] Use `bodybytes-provision` only for the intended operation.
- [ ] Treat `format-emmc` as destructive; verify the target and backup status before confirmation.
- [ ] Treat NOR modification as boot-critical; follow [flashing.md](flashing.md) and [openwrt.md](openwrt.md#spi-nor-flash---spi0).
- [ ] After reprovisioning, boot the normal image and verify basic operation.
- [ ] Repeat the **Customer / mandatory pre-use checklist** whenever reprovisioning restores documented commissioning defaults.
- [ ] Restore owner-managed encrypted storage only using the owner's own key/recovery procedure.

## 10 - Decommissioning and transfer

Before transferring a device to another owner, the current owner should remove personal data and operational credentials.

Because customer secrets are not held by the manufacturer, the manufacturer cannot reliably recover or revoke credentials chosen by a previous owner.

A receiving owner should treat a transferred device as untrusted until it has been reprovisioned to a known state and the mandatory customer provisioning checklist has been completed with new credentials.

If encrypted storage was used, key destruction may make the encrypted contents inaccessible, but owners should choose a sanitization method appropriate to their own threat model.

## 11 - Out of scope / non-claims

This document describes the firmware security model.

It does not by itself make claims about:

- biological or surgical safety;
- implant procedure safety;
- battery or thermal safety;
- regulatory or medical-device status;
- confidentiality against invasive hardware forensics;
- security properties of owner-modified firmware;
- availability of data when owner-managed encryption keys are lost;
- protection against an adversary with unrestricted physical access and sufficient hardware-debugging capability.

Those concerns require separate product, hardware, operational, or regulatory analysis.
