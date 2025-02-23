{ pkgs ? import <nixpkgs> {} }:
  pkgs.mkShell {
    # nativeBuildInputs is usually what you want -- tools you need to run
    nativeBuildInputs = with pkgs; [
      gnumake
      git

      python312
      # poetry
      uv
    ];
    hardeningDisable = [ "all" ];
}
