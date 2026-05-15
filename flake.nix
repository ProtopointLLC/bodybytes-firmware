{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/549bd84d6279f9852cae6225e372cc67fb91a4c1";
  };

  outputs = { self, nixpkgs }:
    let
      pkgs = import nixpkgs {
        system = "x86_64-linux";
      };
    in
    {
      devShell.x86_64-linux =
        pkgs.mkShell {
          shellHook = ''
            export OPENOCD_SCRIPTS=/home/christoph/Documents/GitHub/openocd-scripts/mt7628
          '';

          buildInputs = with pkgs; [
            openocd
          ];
        };
    };
}
