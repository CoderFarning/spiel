import arcade
from game import SurvivalGame  # type: ignore

def main():
    _game = SurvivalGame()
    arcade.run()


if __name__ == "__main__":
    main()