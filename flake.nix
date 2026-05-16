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

        # U-Boot build + JTAG/OpenOCD.
        # Sets CROSS_COMPILE and ARCH for the MIPS toolchain.
        # Usage: nix develop .#uboot
        uboot = pkgs.mkShell {
          shellHook = ''
            export OPENOCD_SCRIPTS="$PWD/openocd-scripts/mt7628"
            export CROSS_COMPILE=mipsel-unknown-linux-gnu-
            export ARCH=mips
          '';

          buildInputs = with pkgs; [
            # OpenOCD — JTAG interface
            openocd

            # Cross toolchain (mipsel-unknown-linux-gnu-gcc / -ld / ...)
            crossPkgs.buildPackages.gcc
            crossPkgs.buildPackages.binutils

            # U-Boot build tools
            gnumake
            bison
            flex
            bc
            dtc
            swig
            pkg-config

            # Crypto / signing (FIT images use CONFIG_FIT=y)
            openssl
            openssl.dev
            gnutls
            gnutls.dev

            # menuconfig TUI
            ncurses
            ncurses.dev

            # Python + libraries used by U-Boot host scripts
            (python3.withPackages (ps: with ps; [
              pyelftools
              pycryptodome
              setuptools
            ]))
          ];
        };

        # OpenWRT shell: host build tools only.
        # Do NOT set CROSS_COMPILE — OpenWRT builds its own MIPS toolchain.
        # Usage: nix develop .#openwrt
        openwrt = pkgs.mkShell {
          buildInputs = with pkgs; [
            # Core build tools
            gcc
            gnumake
            bison
            flex
            gawk
            patch
            diffutils   # diff, cmp
            findutils   # find, xargs
            coreutils   # cp, seq, realpath, stat, install, …
            util-linux  # getopt with --long support

            # Source management
            git
            rsync

            # Download / archive
            wget
            unzip
            bzip2
            gzip

            # Scripting
            perl        # core modules (Data::Dumper, FindBin, …) are bundled
            (python3.withPackages (ps: with ps; [
              setuptools
            ]))

            # menuconfig TUI
            ncurses
            ncurses.dev

            # Library headers used by host-tool builds
            openssl
            openssl.dev
            zlib
            zlib.dev
            gettext     # libintl.h (musl-based toolchain check)

            # Misc utilities OpenWRT checks for
            file
            which
            pkg-config
            swig
            dtc
          ];
        };

      };

    };
}
