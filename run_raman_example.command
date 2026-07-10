#!/bin/zsh
cd "$(dirname "$0")"
export PYTHONPATH="Vibrational_Finder"
python3 -m vibrational_finder.apps.raman_cli --experiment examples/observed_raman.xy --library examples/library.csv
