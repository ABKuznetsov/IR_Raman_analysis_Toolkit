#!/bin/zsh
cd "$(dirname "$0")"
export PYTHONPATH="Vibrational_Finder"
python3 -m vibrational_finder.apps.ftir_cli --experiment examples/observed_ftir.xy --library examples/library.csv
