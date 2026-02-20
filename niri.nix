{ pkgs, ... }:
{
  nixosModule = {
    programs.niri = {
      enable = true;
      useNautilus = true;
    };

    environment.systemPackages = with pkgs; [
      fuzzel
      swayidle
    ];
  };

  homeModule = {
    home.file = {
      ".config/niri/config.kdl" = {
        source = ./config.kdl;
        force = true;
      };
    };
  };
}
