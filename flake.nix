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
      devShell.x86_64-linux =
        pkgs.mkShell {
          shellHook = ''
            export OPENOCD_SCRIPTS="$PWD/openocd-scripts/mt7628"
            export CROSS_COMPILE=mipsel-unknown-linux-gnu-
            export ARCH=mips
            export KCPPFLAGS="-DCFG_SYS_NS16550_COM3=0xb0000e00"
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
    };
}
