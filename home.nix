{
  vars,
  pkgs,
  ...
}:
{
  home.username = vars.username;
  home.homeDirectory = vars.homeDirectory;
  home.stateVersion = "26.05";

  home.packages = with pkgs; [
    bat
    bottom
    devbox
    devenv
    fd
    gdu
    gh
    jq
    imagemagick
    kitty
    lazygit
    luarocks
    mermaid-cli
    nil
    nixd
    nixfmt
    ripgrep
    shellcheck
    shfmt
    tealdeer
    tmux
    trash-cli
    tree
    tree-sitter
    zed-editor
  ];

  programs = {
    home-manager.enable = true;

    librewolf.enable = true;

    eza = {
      enable = true;
      enableFishIntegration = true;
      enableZshIntegration = true;
    };

    starship = {
      enable = true;
      enableFishIntegration = true;
      enableZshIntegration = true;
    };

    carapace = {
      enable = true;
      enableFishIntegration = true;
      enableZshIntegration = true;
    };

    fzf = {
      enable = true;
      enableFishIntegration = true;
      enableZshIntegration = true;
    };

    zoxide = {
      enable = true;
      enableFishIntegration = true;
      enableZshIntegration = true;
    };

    direnv = {
      enable = true;
      nix-direnv.enable = true;
      enableFishIntegration = true;
      enableZshIntegration = true;
    };
  };

  home.file = {
    ".config/kitty/kitty.conf" = {
      source = ./kitty.conf;
      force = true;
    };
    ".config/tmux/tmux.conf" = {
      source = ./tmux.conf;
      force = true;
    };
  };
}
