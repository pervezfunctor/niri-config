{
  description = "NixOS flake configuration";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    dms = {
      url = "github:AvengeMedia/DankMaterialShell/stable";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      home-manager,
      ...
    }@inputs:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      vars = import ./vars.nix;

      niriModules = import ./niri.nix { inherit inputs pkgs; };

      mkOS =
        osModules: homeImports:
        nixpkgs.lib.nixosSystem {
          inherit system;
          specialArgs = { inherit inputs vars homeImports; };

          modules = osModules ++ [
            ./vm-config.nix
            ./core.nix
            home-manager.nixosModules.home-manager
            ./homeModule.nix
          ];
        };
    in
    {
      nixosConfigurations = {
        nixos =
          mkOS
            [
              niriModules.nixosModule
              ./configuration.nix
            ]
            [ niriModules.homeModule ];
      };

      packages.${system} = nixpkgs.lib.mapAttrs' (n: v: {
        name = "${n}-vm";
        value = v.config.system.build.vm;
      }) self.nixosConfigurations;
    };
}
