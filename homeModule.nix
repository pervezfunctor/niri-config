{
  inputs,
  vars,
  homeImports,
  ...
}:
{
  home-manager = {
    useGlobalPkgs = true;
    useUserPackages = true;
    backupFileExtension = "backup";
    extraSpecialArgs = { inherit vars inputs; };

    users.${vars.username} = {
      imports = [ ./home.nix ] ++ homeImports;
    };
  };
}
