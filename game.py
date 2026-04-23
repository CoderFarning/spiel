from pathlib import Path

import arcade
import math
import random
import time

# ---------------- SETTINGS ----------------
SCREEN_TITLE = "Survival Map"
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
MAP_WIDTH = 3600
MAP_HEIGHT = 3600
ASSET_BASE = Path(__file__).resolve().parent
IMG_DIR = ASSET_BASE
SOUND_DIR = ASSET_BASE

PLAYER_WIDTH = 180
PLAYER_HEIGHT = 240
PLAYER_SPEED = 145 + (100 / 60) + 50 + 100 + 300 + 120

SPAWN_INTERVAL = 3.0
WAVE_DURATION = 30

ENEMY_SPEED = 95 + (100 / 60) + 50 + 100 + 300 + 120
MINIMAP_SCALE = 0.05

SHOT_RADIUS = 500
MAX_SHOTS = 30.0
PORTAL_RADIUS = 140
PORTAL_COOLDOWN = 0.4
AMMO_COST = 2
SPAWN_PREVIEW_DURATION = 1.0


class Enemy(arcade.Sprite):
    def __init__(self, image: str):
        super().__init__(image, scale=0.5)
        self.base_speed = ENEMY_SPEED
        self.is_dying = False
        self.death_timer = 0.0
        self.is_spawning = False
        self.spawn_timer = 0.0

class SurvivalGame(arcade.Window):

    def __init__(self):
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE, fullscreen=True, resizable=False)
        # Noch direktere Eingabe ohne in unvernünftige Lastbereiche zu gehen.
        self.set_update_rate(1/960)
        arcade.set_background_color(arcade.color.DARK_GREEN)

        self.state = "menu"
        self.camera = arcade.Camera2D()
        self.camera_zoom = 0.30
        try:
            self.camera.zoom = self.camera_zoom
        except Exception:
            pass
        self.keys = set()

        self.wave_active = False
        self.wave_timer = 0
        self.spawn_timer = 0
        self.wave_number = 1
        self.current_spawn_interval = SPAWN_INTERVAL
        self.current_enemy_speed = ENEMY_SPEED
        self.wave_completed = False
        self.wave_started_once = False
        self.spawn_cycles_per_wave = 0
        self.spawn_cycles_done = 0
        self.wave_spawn_goal = 0
        self.wave_spawned_total = 0
        self.show_minimap = False
        self.wave_message = ""
        self.wave_message_timer = 0.0
        self.controls_hint_timer = 0.0
        self.wave_kills = 0
        self.wave_lives_lost = 0
        self.wave_reward_coins = 0
        self.total_coins = 0
        self.portal_cooldown_timer = 0.0
        self.ui_rects = {}
        self.gems = 0
        self.mouse_x = 0
        self.mouse_y = 0
        self._pending_release_dedupe = None
        self.admin_focus = False
        self.admin_message = ""
        self.admin_message_timer = 0.0
        self.caret_timer = 0.0
        self.caret_visible = True
        self.settings_unlocked = False
        self.hover_level = {}
        self.hover_velocity = {}
        self.text_cache = {}
        self.auto_shot_owned = False
        self.auto_shot_cooldown = 0.0
        self.auto_shot_waves_left = 0
        self.weapon_shot_cooldown = 0.0
        self.weapon_hold_timer = 0.0
        self.mouse_left_down = False
        self.weapon_level = 1
        self.wave_auto_timer = 5.0
        self.player_health_max = 200
        self.player_damage_cooldown = 0.0
        self.player_name = ""
        self.name_confirmed = False
        self.bullet_list = arcade.SpriteList()
        self.bullet_texture = None  # wird nicht mehr benutzt
        self.pistol_texture = arcade.load_texture(str(IMG_DIR / "pistole.png"))
        self.enemy_texture = arcade.load_texture(str(IMG_DIR / "gegner.png"))
        self.spawn_hole_texture = arcade.load_texture(str(IMG_DIR / "loch.png"))
        self.player_texture_armed = arcade.load_texture(str(IMG_DIR / "spieler.png"))
        self.player_texture_unarmed = arcade.load_texture(str(IMG_DIR / "spielerB.png"))
        self.player_scale_armed = 0.4
        self.player_scale_unarmed = 0.4
        self.pistol_icon_sprite = arcade.Sprite(str(IMG_DIR / "pistole.png"), scale=0.6)
        self.pistol_icon_list = arcade.SpriteList()
        self.pistol_icon_list.append(self.pistol_icon_sprite)
        self.upgrade_icon_sprite = arcade.Sprite(str(IMG_DIR / "pistole.png"), scale=0.7)
        self.upgrade_icon_list = arcade.SpriteList()
        self.upgrade_icon_list.append(self.upgrade_icon_sprite)
        self.weapon_equipped = False  # Start: Waffe abgerüstet
        self.wave_auto_timer = 5.0
        self.house_upgrades_on = False

        self.player_health = self.player_health_max
        self.shots_left = float("inf")
        self.energy = 100.0
        self.sprint_drain_acc = 0.0
        self.last_energy_int = int(self.energy)

        self.start_button = None
        self.wave_button = None
        self.shop_return_button = None
        self.shop_buy_one_button = None
        self.hit_sound = None
        self.bg_sound = None
        self.bg_player = None
        self.prep_sound = None
        self.prep_player = None

        self.shop_sound = None
        self.shop_enter_sound = None
        self.shop_enter_player = None
        self.shop_sound_player = None
        self.bg_player = None
        self.cached_energy_cost = None
        self.info_sprite = None
        self.info_sprite_list = None
        self.settings_sprite = None
        self.settings_sprite_list = None
        self.win_sound = None

        self.shop_buy_one_label = f"🔫 Kaufe 1   Preis: {AMMO_COST} 🪙"
        self.shop_leave_label = "Verlassen"
        self._ui_dirty = True
        self.update_ui_rects()

        self.setup_game()

    # ---------------- SETUP ----------------
    def setup_game(self):
        self.player_list = arcade.SpriteList()
        self.enemies = arcade.SpriteList()
        self.spawner_list = arcade.SpriteList()
        self.portal_list = arcade.SpriteList()
        self.decor_list = arcade.SpriteList()

        self.house_sprite = None

        self.weapon_equipped = False
        self.player = arcade.Sprite(str(IMG_DIR / "spielerB.png"), scale=self.player_scale_unarmed)
        self.player.center_x = 0
        self.player.center_y = 0
        self.player_list.append(self.player)
        self.prev_player_pos = (self.player.center_x, self.player.center_y)
        self.isch_sprite = None
        self.weapon_level = 1
        self.weapon_upgraded = False
        self.weapon_shot_cooldown = 0.0
        self.weapon_hold_timer = 0.0
        self.mouse_left_down = False

        self.player_health = self.player_health_max
        self.player_damage_cooldown = 0.0
        self.shots_left = float("inf")
        self.energy = 100.0
        self.sprint_drain_acc = 0.0
        self.last_energy_int = int(self.energy)
        self.portal_x = 0
        self.portal_y = MAP_HEIGHT // 2 - 220
        self.portal_sprite = None  # portal.png entfernt

        self.spawners = []
        self.house_health_max = 0
        self.house_health = 0
        self.house_destroyed = True

        self.wave_active = False
        self.wave_timer = 0
        self.spawn_timer = 0
        self.wave_number = 1
        self.current_spawn_interval = SPAWN_INTERVAL
        self.current_enemy_speed = ENEMY_SPEED
        self.wave_completed = False
        self.wave_started_once = False
        self.spawn_cycles_per_wave = 0
        self.spawn_cycles_done = 0
        self.wave_spawn_goal = 0
        self.wave_spawned_total = 0
        self.show_minimap = False
        self.wave_message = ""
        self.wave_message_timer = 0.0
        self.controls_hint_timer = 0.0
        self.wave_kills = 0
        self.wave_lives_lost = 0
        self.wave_reward_coins = 0
        self.total_coins = 0
        self.portal_cooldown_timer = 0.0
        self.ui_rects = {}

    # ---------------- INPUT ----------------
    def on_key_press(self, key, modifiers):
        self.keys.add(key)

    def on_key_release(self, key, modifiers):
        self.keys.discard(key)

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float):
        self.mouse_x = x
        self.mouse_y = y

    def on_mouse_press(self, x, y, button, modifiers):
        self.mouse_left_down = True

    def on_mouse_release(self, x, y, button, modifiers):
        self.mouse_left_down = False
        return True

    # ---------------- UPDATE ----------------
    def on_update(self, delta_time):

        if self.state != "game":
            return

        # ---------------- BULLET UPDATE ----------------
        for bullet in list(self.bullet_list):
            bullet.center_x += bullet.change_x * delta_time
            bullet.center_y += bullet.change_y * delta_time

            # >>> HIER EINGEFÜGT: Kugeln außerhalb der Arena löschen <<<
            if (
                bullet.center_x < -MAP_WIDTH / 2 or
                bullet.center_x > MAP_WIDTH / 2 or
                bullet.center_y < -MAP_HEIGHT / 2 or
                bullet.center_y > MAP_HEIGHT / 2
            ):
                bullet.kill()
                continue
            # >>> ENDE EINFÜGUNG <<<

            bullet.life_time -= delta_time
            if bullet.life_time <= 0:
                bullet.kill()
                continue

            hits = arcade.check_for_collision_with_list(bullet, self.enemies)
            for enemy in hits:
                enemy.kill()
                bullet.kill()
                break