# shell.nix
{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = [
    (pkgs.python311.withPackages (ps: [
      ps.websocket-client
    ]))
  ];

  shellHook = ''
    echo "🐚 OD-11 raw WebSocket env ready (websocket-client)."
    echo "Run: python od11_ws.py --help"
  '';
}


