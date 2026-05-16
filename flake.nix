{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/549bd84d6279f9852cae6225e372cc67fb91a4c1";
  };

  outputs = { self, nixpkgs }:
    let
      pkgs = import nixpkgs {
        system = "x86_64-linux";
      };
      crossPkgs = pkgs.pkgsCross.mipsel-linux-gnu;
    in
    {
      devShells.x86_64-linux = {

        # U-Boot build + JTAG/OpenOCD.  Usage: nix develop .#uboot
        uboot = pkgs.mkShell {
          shellHook = ''
            export OPENOCD_SCRIPTS="$PWD/openocd-scripts/mt7628"
            export CROSS_COMPILE=mipsel-unknown-linux-gnu-
            export ARCH=mips
          '';

          buildInputs = with pkgs; [
            openocd
            crossPkgs.buildPackages.gcc
            crossPkgs.buildPackages.binutils
            gnumake bison flex bc dtc swig pkg-config
            openssl openssl.dev gnutls gnutls.dev
            ncurses ncurses.dev
            (python3.withPackages (ps: with ps; [
              pyelftools pycryptodome setuptools
            ]))
          ];
        };

        # OpenWRT host build shell.  Usage: nix develop .#openwrt
        # buildFHSEnv provides /bin/bash etc. that upstream scripts hard-code.
        # Do NOT set CROSS_COMPILE — OpenWRT builds its own MIPS toolchain.
        openwrt = (pkgs.buildFHSEnv {
          name = "openwrt";

          targetPkgs = pkgs: with pkgs; [
            gcc gnumake bison flex gawk patch
            diffutils findutils coreutils util-linux
            git rsync wget unzip bzip2 gzip
            perl
            (python3.withPackages (ps: with ps; [ setuptools ]))
            ncurses ncurses.dev
            openssl openssl.dev zlib zlib.dev
            gettext     # libintl.h needed by musl toolchain check
            file which pkg-config swig dtc bash
            gcc.cc      # gcc-ar / gcc-nm / gcc-ranlib for LTO host builds
          ];

          hardeningDisable = [ "all" ];

          profile = ''
            # FHS base sets AR=ar; override so Meson uses the LTO-aware archiver.
            # Name-only lets cross builds prepend TARGET_CROSS correctly.
            export AR=gcc-ar
            export RANLIB=gcc-ranlib
            export NM=gcc-nm
            # bwrap user namespace doesn't map uid 0 → fchownat returns EINVAL,
            # which fakeroot doesn't swallow (unlike EPERM). Skip the real chown;
            # ownership is tracked in fakeroot's db and ends up correct in images.
            export FAKEROOTDONTTRYCHOWN=1
          '';
        }).env;

      };

    };
}
