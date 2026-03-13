import arcade
from constants import ENEMY_SPEED


class Enemy(arcade.Sprite):
    def __init__(self, image: str):
        super().__init__(image, scale=0.5)
        self.base_speed = ENEMY_SPEED
        self.is_dying = False
        self.death_timer = 0.0
