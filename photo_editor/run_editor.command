#!/bin/zsh
cd "${0:A:h}"
open "http://127.0.0.1:8765"
exec python3 app.py
