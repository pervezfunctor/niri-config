{pkgs, ...}: {
  home.packages = with pkgs; [
    devbox
    devenv
    nixd
    nixfmt
  ];
}
