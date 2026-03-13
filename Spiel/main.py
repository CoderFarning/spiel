import sys
from pathlib import Path

import arcade

# Ordner "geheim" ins Modul-Suchpfad aufnehmen
BASE_DIR = Path(__file__).resolve().parent.parent
GEHEIM_DIR = BASE_DIR / "geheim"
if str(GEHEIM_DIR) not in sys.path:
    sys.path.insert(0, str(GEHEIM_DIR))

from game import SurvivalGame # type: ignore

def main():
    _game = SurvivalGame()
    arcade.run()


if __name__ == "__main__":
    main()