{ inputs, pkgs, ... }:
{
  nixosModule = {
    programs.niri = {
      enable = true;
      useNautilus = true;
    };

    environment.systemPackages = with pkgs; [
      fuzzel
      swayidle
      power-profiles-daemon
      cups-pk-helper
    ];

  };

  homeModule = {
    imports = [ inputs.dms.homeModules.dank-material-shell ];

    programs.dank-material-shell = {
      enable = true;
      systemd = {
        enable = false;
        restartIfChanged = true;
      };
    };

    home.pointerCursor = {
      enable = true;
      package = pkgs.bibata-cursors;
      name = "Bibata-Modern-Ice";
      size = 24;
    };

    home.file = {
      ".config/niri/config.kdl" = {
        source = ./config.kdl;
        force = true;
      };
    };
  };
}
