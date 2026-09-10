@echo off
cd /d "%~dp0"
python build_anki_deck.py -i example.json -s 13 --speed 0.85
pause