{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;

      mkPerSystem = system:
        let
          pkgs = import nixpkgs { inherit system; };
          crossPkgs = pkgs.pkgsCross.mipsel-linux-gnu;

          patchedOpenocd = pkgs.openocd.overrideAttrs (old: {
            src = pkgs.fetchFromGitHub {
              owner = "ProtopointLLC";
              repo = "bobybytes-openocd";
              rev = "8e04bc7b27087dcca7f3858534ed665bb1b9e92d";
              hash = "sha256-XemQSScTfyQJ1yl2unMCjgkYoiBlo3t8Jrv3dBhz2Uo=";
              fetchSubmodules = true;
            };

            nativeBuildInputs = (old.nativeBuildInputs or [ ])
              ++ [ pkgs.autoreconfHook ];
          });

          openwrtFHSEnv = pkgs.buildFHSEnv {
            name = "openwrt";

            profile = ''
              export AR=gcc-ar
              export RANLIB=gcc-ranlib
              export NM=gcc-nm
              export FAKEROOTDONTTRYCHOWN=1
              export NIX_CFLAGS_COMPILE="-I/usr/include"
              export NIX_LDFLAGS="-L/usr/lib"
              export NIX_HARDENING_ENABLE=""
              unset SOURCE_DATE_EPOCH
            '';

            targetPkgs = pkgs: with pkgs; [
              glibc
              gcc gnumake bison flex gawk patch
              diffutils findutils coreutils
              git rsync wget unzip bzip2 gzip
              perl
              (python3.withPackages (ps: with ps; [ setuptools ]))
              ncurses ncurses.dev
              openssl openssl.dev zlib zlib.dev xz
              gettext
              file which pkg-config swig dtc bash
              (lib.lowPrio gcc.cc)
            ];
          };

        in {
          devShells = {
            # U-Boot build + JTAG/OpenOCD.
            uboot = pkgs.mkShell {
              shellHook = ''
                export OPENOCD_SCRIPTS="$PWD/openocd"
                export CROSS_COMPILE=mipsel-unknown-linux-gnu-
                export ARCH=mips
                unset SOURCE_DATE_EPOCH
              '';

              buildInputs = with pkgs; [
                picocom flashrom
                patchedOpenocd
                inetutils
                crossPkgs.buildPackages.gcc
                crossPkgs.buildPackages.binutils
                crossPkgs.buildPackages.gdb
                gnumake bison flex bc dtc swig pkg-config
                openssl openssl.dev gnutls gnutls.dev
                ncurses ncurses.dev
                (python3.withPackages (ps: with ps; [
                  pyelftools pycryptodome setuptools
                  pyserial pyfdt
                ]))
              ];
            };

            # OpenWrt host build shell (interactive use).
            openwrt = openwrtFHSEnv.env;
          };

          packages = {
            openwrt = openwrtFHSEnv;
            openocd = patchedOpenocd;
          };
        };

      perSystem = forAllSystems mkPerSystem;

    in {
      devShells = nixpkgs.lib.mapAttrs (_system: s: s.devShells) perSystem;
      packages = nixpkgs.lib.mapAttrs (_system: s: s.packages) perSystem;
    };
}
