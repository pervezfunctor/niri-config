{
  description = "Home Manager flake configuration";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      nixpkgs,
      home-manager,
      ...
    }@inputs:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      vars = {
        username = builtins.getEnv "USER";
        homeDirectory = builtins.getEnv "HOME";
      };
    in
    {
      homeConfigurations = {
        "${vars.username}" = home-manager.lib.homeManagerConfiguration {
          inherit pkgs;
          modules = [
            ./dev.nix
            ./packages.nix
          ];
          extraSpecialArgs = { inherit inputs vars; };
        };
      };
    };
}
