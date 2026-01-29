{ pkgs, vars, ... }: {
  home.username = vars.username;
  home.homeDirectory = vars.homeDirectory;
  home.stateVersion = "25.11";

  nixpkgs.config.allowUnfree = true;
}
