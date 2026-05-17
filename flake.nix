{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
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
        uboot = pkgs.mkShell {
          shellHook = ''
            export OPENOCD_SCRIPTS="$PWD/openocd-scripts/mt7628"
            export CROSS_COMPILE=mipsel-unknown-linux-gnu-
            export ARCH=mips
          '';

          buildInputs = with pkgs; [
            openocd
            inetutils
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

        # OpenWRT host build shell.
        openwrt = (pkgs.buildFHSEnv {
          name = "openwrt";

          targetPkgs = pkgs: with pkgs; [
            gcc gnumake bison flex gawk patch
            diffutils findutils coreutils util-linux
            git rsync wget unzip bzip2 gzip
            perl
            (python3.withPackages (ps: with ps; [ setuptools ]))
            ncurses ncurses.dev
            openssl openssl.dev zlib zlib.dev xz
            gettext
            file which pkg-config swig dtc bash
            (lib.lowPrio gcc.cc)
          ];

          profile = ''
            export AR=gcc-ar
            export RANLIB=gcc-ranlib
            export NM=gcc-nm
            export FAKEROOTDONTTRYCHOWN=1
            export NIX_CFLAGS_COMPILE="-I/usr/include"
            export NIX_LDFLAGS="-L/usr/lib"
            export NIX_HARDENING_ENABLE=""
          '';
        }).env;

      };

    };
}
