# Component Versions

Bodybytes depends on a handful of pinned upstream trees - some forked with bodybytes-specific patches, some pinned as-is. This page has two halves: **Current versions** is the single place that records what's pinned *right now* - update it, and only it, whenever a pin moves. Everything after that is a generic procedure for moving a pin; it deliberately contains no version numbers or commit hashes of its own, so it doesn't go stale between updates.

## Current versions

| Component | Repo | Branch | Pinned via | Current pin | Pinned on |
|-----------|------|--------|------------|-------------|-----------|
| OpenWrt | [`ProtopointLLC/bodybytes-openwrt`](https://github.com/ProtopointLLC/bodybytes-openwrt) | `bodybytes` | `.gitmodules` + commit recorded in this repo's git tree (`git submodule status`) | upstream tag [`v25.12.4`](https://github.com/openwrt/openwrt/releases/tag/v25.12.4) | 2026-05-14 |
| U-Boot | [`ProtopointLLC/bodybytes-u-boot`](https://github.com/ProtopointLLC/bodybytes-u-boot) | `bodybytes` | `.gitmodules` + commit recorded in this repo's git tree | upstream tag [`v2026.04`](https://source.denx.de/u-boot/u-boot/-/tags/v2026.04) | 2026-04-06 |
| `bodybytes-packages` | [`ProtopointLLC/bodybytes-packages`](https://github.com/ProtopointLLC/bodybytes-packages) | `bodybytes` | `src-git` pin in [`openwrt/feeds.conf.default`](../openwrt/feeds.conf.default) | commit `84b68e2b5` (forked from upstream `openwrt-25.12` @ `f91b06b3f`) | 2026-05-13 |
| `bodybytes-luci` | [`ProtopointLLC/bodybytes-luci`](https://github.com/ProtopointLLC/bodybytes-luci) | `bodybytes` | `src-git` pin in [`openwrt/feeds.conf.default`](../openwrt/feeds.conf.default) | commit `e4c4a79c6` (forked from upstream `openwrt-25.12` @ `e9ebca759`) | 2026-05-13 |
| `immortalwrt_luci` | [`immortalwrt/luci`](https://github.com/immortalwrt/luci) (upstream, no bodybytes fork) | `openwrt-25.12` | `src-git` pin in [`openwrt/feeds.conf.default`](../openwrt/feeds.conf.default) | commit `c48d3f0f2` | 2026-05-16 |

Each fork carries a small, specific diff on top of its pin:

- **OpenWrt** - the `ramips`/`mt76x8` board files (DTS, image build rules, kernel config, `bodybytes-common`/`bodybytes-provision` packages, and `feeds.conf.default` itself). See [openwrt.md - Board files](openwrt.md#1---board-files) for the full list.
- **U-Boot** - the entire `board/bodybytes/bodybytes` tree, `configs/bodybytes_defconfig`, `include/configs/bodybytes.h`, and the MT7628 `mtk-sd.c` driver fix - this fork carries many bodybytes-specific commits, not a single patch. See [uboot.md - Board files](uboot.md#board-files).
- **`bodybytes-packages`** - one commit adding travelmate's `trm_oneshot`/`trm_ifdown_disable` UCI options.
- **`bodybytes-luci`** - one commit replacing `luci-app-travelmate`'s disruptive scan button with a manual "Add Uplink" flow.
- **`immortalwrt_luci`** - no bodybytes diff at all. It isn't a bodybytes fork - the pin points straight at upstream `immortalwrt/luci`, and exists solely so `./scripts/feeds install -p immortalwrt_luci luci-app-dufs` (see [building.md - Feeds](building.md#feeds)) can cherry-pick that one package, which isn't in the main `luci` feed. Everything else this feed carries is deliberately never installed.

All three feed rows are pinned to a specific commit, not a branch tip, for a reason - see [§How the feed pins work](#how-the-feed-pins-work) below.

Upstream has kept moving on every one of these branches since the fork points above; none of that later history has been merged into any of the forks.

---

## How the feed pins work

`u-boot` and `openwrt` are real git submodules: `.gitmodules` names the fork URL/branch, and the pinned commit lives in this repo's own git tree (`git submodule status` shows it).

`bodybytes-packages`/`bodybytes-luci` are pinned one layer deeper, *inside* the OpenWrt tree, via [`openwrt/feeds.conf.default`](../openwrt/feeds.conf.default)'s `src-git <name> <url>^<commit>` syntax:

```
src-git packages          <bodybytes-packages url>^<commit>
src-git luci               <bodybytes-luci url>^<commit>
src-git immortalwrt_luci   <immortalwrt/luci url>^<commit>
```

(See the Current versions table above for today's actual URLs and commits.) The `^<commit>` suffix is a hard pin - `./scripts/feeds update -a` (see [building.md - Feeds](building.md#feeds)) checks out exactly that commit, regardless of what any upstream branch has moved to since. There is no automation keeping this file's pins in sync with anything; bumping a feed always means hand-editing the commit hash here and re-running `feeds update`.

**Why fork from a stock-OpenWrt-named commit, not the feed branch tip:** `bodybytes-packages` and `bodybytes-luci` are long-lived OpenWrt feeds that keep one branch per release (e.g. `openwrt-18.06` … `openwrt-25.12`). Stock OpenWrt's *own* `feeds.conf.default`, at any given OpenWrt tag, pins `packages`/`luci` to one specific commit on the matching release branch - that commit is what's actually been built and tested against that OpenWrt version, not just "whatever's newest on the branch today." Forking from that exact commit (`git show <openwrt tag>:feeds.conf.default`) keeps all the pieces in lockstep; forking from the branch tip, or from `master`, would risk package/LuCI changes untested against this OpenWrt release.

**`immortalwrt_luci` is pinned for a different reason, with the same remedy.** It isn't forked at all - `feeds.conf.default` points straight at `immortalwrt/luci`, which is itself a downstream distro of OpenWrt/LuCI with its own matching `openwrt-25.12`-style release branches. The one package pulled from it (`luci-app-dufs`) is a LuCI app, so it's built against whatever LuCI core JS/view/ACL API that commit of `immortalwrt/luci` assumes - picking a commit far from the `bodybytes-luci` pin risks an API mismatch even though no bodybytes code touches this feed. The fix is the same shape as above: pick a commit on `immortalwrt/luci`'s own release branch matching the current OpenWrt release, close in time to the `bodybytes-luci` pin, rather than leaving an old commit in place or jumping to that branch's current tip blindly.

---

## Before rebasing any fork: snapshot its `bodybytes` branch

Every runbook below rewrites a fork's `bodybytes` branch history and force-pushes it. Before doing that to **any** fork we maintain - `bodybytes-openwrt`, `bodybytes-u-boot`, `bodybytes-packages`, `bodybytes-luci` - push a plain copy of its current `bodybytes` branch tip under a name that records the version it was forked from:

```sh
git push origin bodybytes:bodybytes-$OLD
```

(`$OLD` is the tag that fork is currently pinned to - e.g. the OpenWrt tag for `bodybytes-openwrt`/`bodybytes-packages`/`bodybytes-luci`, the U-Boot tag for `bodybytes-u-boot`.) This is a real branch, not a tag, pushed to the same `origin` the real `bodybytes` branch lives on - once the rebase below force-pushes over `bodybytes`, this copy is the only thing that still points at the pre-update state. It costs nothing to keep around, so don't delete old ones.

`immortalwrt_luci` doesn't need this - bodybytes never force-pushes it (it isn't a fork we maintain; see [§How the feed pins work](#how-the-feed-pins-work) above), so there's no history of ours to lose.

---

## Updating OpenWrt (and its feed pins)

A rebase update has to move pins in dependency order: **OpenWrt core → (read OpenWrt's own feed pins at the new tag) → `bodybytes-packages` → `bodybytes-luci` → a compatible `immortalwrt_luci` commit → this repo's submodule pointer and feed pins.** Throughout, `$OLD` is the tag currently recorded in the Current versions table, `$NEW` is the tag you're moving to.

### 1 - Snapshot `bodybytes-openwrt`, `bodybytes-packages`, and `bodybytes-luci`

Push a `bodybytes-$OLD` backup branch in each of the three forks you're about to rewrite, per [§Before rebasing any fork](#before-rebasing-any-fork-snapshot-its-bodybytes-branch) above, before doing anything else.

### 2 - Rebase `bodybytes-openwrt`

```sh
cd bodybytes-openwrt
git fetch https://git.openwrt.org/openwrt/openwrt.git $NEW
git checkout bodybytes
git rebase --onto FETCH_HEAD $OLD
```

The bodybytes-side diff being replayed is the board-file list in [openwrt.md §1](openwrt.md#1---board-files). A point release rarely touches any of those files, so this is usually conflict-free; a feature release is more likely to touch shared infrastructure (kernel config layout, image build rules) that the board files hook into. Resolve any conflicts, then re-run `make defconfig` and a build before going further - a clean rebase doesn't guarantee the result still builds.

### 3 - Read the new feed pins from stock OpenWrt

Don't read the feed branch tip - read the exact commit the new tag itself pins, the same way the existing forks were created (see [§How the feed pins work](#how-the-feed-pins-work) above):

```sh
git show $NEW:feeds.conf.default | grep -E 'packages|luci'
```

That gives the new rebase target for each of steps 4 and 5.

### 4 - Rebase `bodybytes-packages` onto its new pin

`$OLD_PIN` is the commit already recorded in the Current versions table for this fork (the one stock OpenWrt pinned at `$OLD`); `$NEW_PIN` is the `packages` line from step 3's output:

```sh
cd bodybytes-packages
git fetch origin openwrt-25.12   # or whichever release branch matches $NEW
git checkout bodybytes
git rebase --onto $NEW_PIN $OLD_PIN
```

This fork normally carries very few bodybytes-specific commits (currently just one - see Current versions), so the rebase is usually small and clean.

### 5 - Rebase `bodybytes-luci` onto its new pin

Same shape as step 4, substituting the `luci` line from step 3's output and `bodybytes-luci`'s own Current-versions pin for `$NEW_PIN`/`$OLD_PIN`. LuCI rebases are more likely to conflict than packages: the one bodybytes commit here touches a travelmate view file that upstream also edits fairly often. Resolve any conflict by hand, re-checking the result still matches the behavior documented in [openwrt.md - Board profiles](openwrt.md#board-profiles) (the "Add Uplink" button, not the stock "Scan" button), then continue the rebase.

### 6 - Pick a new, compatible `immortalwrt_luci` commit

This one isn't a rebase - there's no bodybytes commit on top to replay (see [§How the feed pins work](#how-the-feed-pins-work) above), and it isn't a fork we maintain, so it got no backup branch in step 1 either. Pick a commit on `immortalwrt/luci`'s own release branch matching `$NEW` (e.g. its `openwrt-25.12`-style branch), as close in time as practical to the commit `bodybytes-luci` just landed on in step 5, so the two LuCI trees' core APIs stay close enough for `luci-app-dufs` to build cleanly against the rebased `bodybytes-luci`. There's no automated "latest compatible commit" query for this - eyeball the branch's commit dates/log on GitHub, or just try the branch tip and fall back if `feeds install` or the build fails.

### 7 - Push the rebased forks

`bodybytes-packages`, `bodybytes-luci`, and `bodybytes-openwrt` all just got their `bodybytes` branch history rewritten, so this is a force-push (nothing to push for `immortalwrt_luci` - it's an upstream repo, not a fork):

```sh
git push --force-with-lease origin bodybytes   # in each of bodybytes-packages, bodybytes-luci, bodybytes-openwrt
```

Check for anything else (open PRs, other checkouts) depending on the old branch tips first - `--force-with-lease` only protects against *this* push racing a push you haven't seen, not against breaking someone else's in-progress work.

### 8 - Re-pin the feeds inside `bodybytes-openwrt`

Update [`feeds.conf.default`](../openwrt/feeds.conf.default) in the already-rebased `bodybytes-openwrt` tree: `packages` and `luci` to the **new HEAD of each fork's `bodybytes` branch** (the commit produced by steps 4/5 - not the stock-OpenWrt pin from step 3; the fork still carries its own commit on top of that), and `immortalwrt_luci` to the commit picked in step 6. Commit this on `bodybytes-openwrt`'s `bodybytes` branch and push it too.

Then re-run the single-package feed install from [building.md - Feeds](building.md#feeds) (`./scripts/feeds install -p immortalwrt_luci luci-app-dufs`) against the new pin to confirm it still resolves and builds before moving on.

### 9 - Bump the submodule pointer in this repo

```sh
cd bodybytes-firmware
cd openwrt && git checkout bodybytes && git pull && cd ..
git add openwrt
git commit -m "openwrt: update to $NEW"
```

Then run `./scripts/feeds update -a` inside `openwrt/` (see [building.md - Feeds](building.md#feeds)) to actually check out the newly-pinned feed commits, and rebuild.

### 10 - Update the Current versions table, and everything else that quotes the old tag

Update this page's **Current versions** table first - it's the record of truth the rest of this step checks against. Then grep the rest of the project for the *old* tag string and fix every hit:

```sh
grep -rn "$OLD" --include="*.md" .
```

As of this writing that turns up:

| File | What's there |
|------|--------------|
| [`README.md`](../README.md) | Component table row naming the OpenWrt tag |
| [`docs/building.md`](building.md) | Example build-output filenames, in both the `make` output listing and the image table |
| [`docs/vocore2.md`](vocore2.md) | `SYSUPGRADE=` example path in the eMMC-from-PC install section |
| [`docs/flashing.md`](flashing.md) | The recovery-image partition-map entry, and the LuCI sysupgrade filename in the first-install walkthrough |

New files may add new hits over time - the grep, not this table, is the authority.

Two places that look like they'd need an edit but **don't**:

- [`openwrt/include/version.mk`](../openwrt/include/version.mk) - `VERSION_NUMBER` is hardcoded upstream to match whatever tag is checked out; it travels automatically with the submodule bump in step 9.
- [`bodybytes.config`](../bodybytes.config) - has no `CONFIG_VERSION_NUMBER` override, so nothing to touch there either.

One more thing worth a second look, not a guaranteed edit: [`target/linux/ramips/mt76x8/config-6.12`](../openwrt/target/linux/ramips/mt76x8/config-6.12) is named after the kernel patch version (`KERNEL_PATCHVER` in `target/linux/ramips/Makefile`), not the OpenWrt release. A point release won't normally bump it, but a feature release might - if `target/linux/ramips/Makefile` points at a different `config-*` file after the core rebase (step 2), the bodybytes kernel-config patch has to move with it; see [openwrt.md §1](openwrt.md#1---board-files).

---

## Updating U-Boot

A U-Boot bump is a single-repo rebase - no feed pins to chase, since U-Boot has no equivalent of `bodybytes-packages`/`bodybytes-luci`. As above, `$OLD`/`$NEW` are the tags from (and replacing the one in) the Current versions table.

### 1 - Snapshot `bodybytes-u-boot`

Push a `bodybytes-$OLD` backup branch, per [§Before rebasing any fork](#before-rebasing-any-fork-snapshot-its-bodybytes-branch) above, before doing anything else.

### 2 - Rebase `bodybytes-u-boot`

```sh
cd bodybytes-u-boot
git fetch https://source.denx.de/u-boot/u-boot.git $NEW
git checkout bodybytes
git rebase --onto FETCH_HEAD $OLD
```

This replays every bodybytes-specific commit (see [uboot.md - Board files](uboot.md#board-files), or the summary in Current versions above) onto the new tag, one commit at a time. This fork carries many more commits than either feed fork (it *is* the board-support branch, not a one-patch fork), so expect more opportunities for a conflict partway through; resolve each in turn with the usual `git rebase --continue` loop.

After the rebase, re-run `make bodybytes_defconfig && make -j$(nproc)` (see [building.md](building.md#u-boot)) before pushing - a clean rebase doesn't guarantee the result still builds, and a Kconfig symbol renamed upstream between tags would otherwise only surface as a silent default change.

### 3 - Push the rebased fork

```sh
git push --force-with-lease origin bodybytes
```

Same caveat as the OpenWrt runbook: check for anything else depending on the old branch tip before force-pushing.

### 4 - Bump the submodule pointer in this repo

```sh
cd bodybytes-firmware
cd u-boot && git checkout bodybytes && git pull && cd ..
git add u-boot
git commit -m "u-boot: update to $NEW"
```

### 5 - Update the Current versions table, and everything else that quotes the old tag

Same pattern as the OpenWrt runbook: update the **Current versions** table first, then grep for the old tag:

```sh
grep -rn "$OLD" --include="*.md" .
```

As of this writing that turns up:

| File | What's there |
|------|--------------|
| [`README.md`](../README.md) | Component table row naming the U-Boot tag |
| [`docs/uboot.md`](uboot.md) | Opening line naming the submodule's tag |

U-Boot's binary output filenames ([`u-boot.bin`](../u-boot/u-boot.bin), [`u-boot-with-spl.bin`](../u-boot/u-boot-with-spl.bin), etc. - see [building.md - Output](building.md#output)) don't carry the version in their name, unlike OpenWrt's image filenames, so there's nothing to update there.
