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

        # Cached UI text metrics so buttons don't stutter from per-frame Text creation.
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

        # Spawner entfallen; Gegner werden zufällig am Kartenrand erzeugt
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

        if self.state == "settings":
            if key == arcade.key.ENTER or key == arcade.key.RETURN:
                if self.admin_input.strip() == "fauli!":
                    self.admin_message = ""
                    self.admin_message_timer = 0.0
                    self.settings_unlocked = True
                else:
                    self.admin_message = "Falscher Code"
                    self.admin_message_timer = 2.0
                return
            if not self.admin_focus:
                return
            if key == arcade.key.BACKSPACE:
                self.admin_input = self.admin_input[:-1]
                return
        if self.state == "menu":
            if key == arcade.key.ENTER or key == arcade.key.RETURN:
                if self.player_name.strip():
                    self.name_confirmed = True
                return
            if key == arcade.key.BACKSPACE:
                self.player_name = self.player_name[:-1]
                self.name_confirmed = False
                return
        if self.state == "game":
            if key == arcade.key.KEY_1:
                self.weapon_equipped = not self.weapon_equipped
                if self.weapon_equipped:
                    self.player.texture = self.player_texture_armed
                    self.player.scale = self.player_scale_armed
                else:
                    self.player.texture = self.player_texture_unarmed
                    self.player.scale = self.player_scale_unarmed
        elif self.state == "shop":
            if key == arcade.key.ESCAPE:
                self.leave_shop()

    def on_key_release(self, key, modifiers):
        self.keys.discard(key)

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float):
        self.mouse_x = x
        self.mouse_y = y
        self.ensure_ui_rects()

    def point_in_rect(self, x, y, rect, padding=44):
        bx, by, bw, bh = rect
        return (bx - padding) <= x <= (bx + bw + padding) and (by - padding) <= y <= (by + bh + padding)

    def point_on_sprite(self, x, y, sprite, padding=48):
        if sprite is None:
            return False
        left = sprite.center_x - sprite.width / 2 - padding
        right = sprite.center_x + sprite.width / 2 + padding
        bottom = sprite.center_y - sprite.height / 2 - padding
        top = sprite.center_y + sprite.height / 2 + padding
        return left <= x <= right and bottom <= y <= top

    def point_on_tisch(self, x, y):
        if self.isch_sprite is None:
            return False
        try:
            if self.isch_sprite.collides_with_point((x, y)):
                return True
        except Exception:
            pass

        # Fallback: an die sichtbare Schmiede angepasst, rechts leicht erweitert.
        half_w = self.isch_sprite.width * 0.40
        half_h = self.isch_sprite.height * 0.24
        center_x = self.isch_sprite.center_x + self.isch_sprite.width * 0.03
        center_y = self.isch_sprite.center_y - self.isch_sprite.height * 0.02
        return (center_x - half_w) <= x <= (center_x + half_w) and (center_y - half_h) <= y <= (center_y + half_h)

    def change_zoom(self, delta):
        return
        try:
            self.camera.zoom = self.camera_zoom
        except Exception:
            pass

    def get_weapon_upgrade_cost(self):
        costs = [150, 750, 7500, 10000]
        if 1 <= self.weapon_level <= len(costs):
            return costs[self.weapon_level - 1]
        return None

    def get_weapon_cooldown(self):
        if self.weapon_level == 1:
            return 0.5
        if self.weapon_level == 2:
            return 0.3
        if self.weapon_level == 3:
            return 0.01
        return 0.0

    def get_weapon_status_text(self):
        if self.weapon_level == 1:
            return "1 Schuss, 0.5s Cooldown"
        if self.weapon_level == 2:
            return "3 Schüsse, 0.3s Cooldown"
        if self.weapon_level == 3:
            return "1 Schuss, 0.01s Cooldown"
        if self.weapon_level == 4:
            return "3 Schüsse, kein Cooldown"
        return "3 Schüsse, halten für Dauerfeuer"

    def get_weapon_level_label(self):
        if self.weapon_level == 1:
            return "Pistole"
        if self.weapon_level == 2:
            return "Kampfflinte"
        if self.weapon_level == 3:
            return "AK-47"
        if self.weapon_level == 4:
            return "Minigun"
        return "Minigun"

    def get_next_weapon_name(self):
        if self.weapon_level == 1:
            return "Kampfflinte"
        if self.weapon_level == 2:
            return "AK-47"
        if self.weapon_level == 3:
            return "Minigun"
        return "Max Level"

    def _handle_click(self, x, y, button):
        self.ensure_ui_rects()
        self.mouse_x = x
        self.mouse_y = y

        if self.state == "menu":
            bx, by, bw, bh = self.ui_rects["start_button"]
            if self.point_in_rect(x, y, (bx, by, bw, bh)):
                if not self.name_confirmed:
                    return True
                self.setup_game()
                self.state = "game"
                self.start_prep()
                return True

        elif self.state == "game":
            bx, by, bw, bh = self.ui_rects["upgrade_panel_window"]
            weapon_cost = self.get_weapon_upgrade_cost()
            if self.point_in_rect(x, y, (bx, by, bw, bh)):
                if (not self.wave_active) and weapon_cost is not None and self.gems >= weapon_cost:
                    self.gems -= weapon_cost
                    self.weapon_level += 1
                    self.weapon_upgraded = self.weapon_level > 1
                return True

            if button == arcade.MOUSE_BUTTON_LEFT:
                self.fire_bullet(x, y)
                return True

        elif self.state == "settings":
            # Eingabefeld Fokus setzen
            ibx, iby, ibw, ibh = (self.width / 2 - 250, self.height - 300, 500, 60)
            if ibx <= x <= ibx + ibw and iby <= y <= iby + ibh:
                self.admin_focus = True
            else:
                self.admin_focus = False

            # Settings-Fenster deaktiviert – keine Interaktion
            return True

        elif self.state == "shop":
            bx, by, bw, bh = self.ui_rects["shop_leave"]
            if self.point_in_rect(x, y, (bx, by, bw, bh)):
                self.leave_shop()
                return True

            bx, by, bw, bh = self.ui_rects["shop_buy_one"]
            if self.point_in_rect(x, y, (bx, by, bw, bh)):
                self.buy_ammo(1)
                return True

            bx, by, bw, bh = self.ui_rects["shop_energy"]
            if self.point_in_rect(x, y, (bx, by, bw, bh)):
                self.buy_energy()
                return True

            bx, by, bw, bh = self.ui_rects["shop_auto"]
            if self.point_in_rect(x, y, (bx, by, bw, bh)):
                self.buy_auto_shot()
                return True

        elif self.state == "gameover":
            bx, by, bw, bh = self.ui_rects["gameover_restart"]
            if self.point_in_rect(x, y, (bx, by, bw, bh)):
                self.stop_bg()
                self.stop_shop_sound()
                self.stop_prep()
                self.setup_game()
                self.state = "game"
                self.start_prep()
                return True
            return True

        return False

    def on_mouse_press(self, x, y, button, modifiers):
        if button == arcade.MOUSE_BUTTON_LEFT:
            self.mouse_left_down = True
        return self._handle_click(x, y, button)

    def on_mouse_release(self, x, y, button, modifiers):
        # Klicks werden bewusst nur auf mouse_press verarbeitet,
        # damit niemals ein zweiter Ausloeser aus mouse_release entsteht.
        if button == arcade.MOUSE_BUTTON_LEFT:
            self.mouse_left_down = False
        self._pending_release_dedupe = None
        return True

    def on_text(self, text: str):
        if self.state == "settings" and self.admin_focus:
            if text and text.isprintable():
                self.admin_input += text
        if self.state == "menu":
            if self.name_confirmed:
                return
            if text and text.isprintable():
                if len(self.player_name) < 16:
                    self.player_name += text
                    self.name_confirmed = False

    # ---------------- RADIUS SHOT ----------------
    def radius_shot(self):
        # Radialschuss deaktiviert
        return

    def get_wave_button_rect(self):
        return (0, 0, 0, 0)  # Wave-Button deaktiviert/unsichtbar

    def get_shop_leave_button_rect(self):
        text_obj = arcade.Text(self.shop_leave_label, 0, 0, arcade.color.WHITE, 26, anchor_x="center", anchor_y="center")
        bw = text_obj.content_width + 140
        bh = text_obj.content_height + 50
        bx = self.width / 2 - bw / 2
        by = 120
        return (bx, by, bw, bh)

    def get_shop_buy_one_button_rect(self):
        text_obj = arcade.Text(self.shop_buy_one_label, 0, 0, arcade.color.WHITE, 24, anchor_x="center", anchor_y="center")
        bw = text_obj.content_width + 100
        bh = text_obj.content_height + 42
        bx = self.width / 2 - bw / 2
        by = self.height - 400
        return (bx, by, bw, bh)

    def get_shop_energy_button_rect(self):
        label = "⚡ Energie +5% auffüllen"
        text_obj = arcade.Text(label, 0, 0, arcade.color.WHITE, 24, anchor_x="center", anchor_y="center")
        bw = text_obj.content_width + 100
        bh = text_obj.content_height + 42
        bx = self.width / 2 - bw / 2
        by = self.height - 480
        return (bx, by, bw, bh)

    def get_shop_auto_button_rect(self):
        label = "🤖 Auto-Schuss  Preis: 100"
        text_obj = arcade.Text(label, 0, 0, arcade.color.WHITE, 24, anchor_x="center", anchor_y="center")
        bw = text_obj.content_width + 120
        bh = text_obj.content_height + 42
        bx = self.width / 2 - bw / 2
        by = self.height - 560
        return (bx, by, bw, bh)


    def buy_ammo(self, amount):
        if amount <= 0:
            return
        cost = amount * AMMO_COST
        if self.total_coins < cost:
            return
        self.total_coins -= cost
        self.shots_left += amount

    def buy_energy(self):
        missing = max(0, 100 - int(self.energy))
        if missing <= 0:
            self.cached_energy_cost = None
            return
        add_amount = min(5, missing)
        cost = add_amount * 5
        if self.total_coins < cost:
            return
        self.total_coins -= cost
        self.energy = min(100.0, self.energy + add_amount)
        self.cached_energy_cost = None
        self.compute_shop_rects()

    def buy_auto_shot(self):
        if self.auto_shot_owned or self.gems < 300:
            return
        self.gems -= 300
        self.auto_shot_owned = True
        self.auto_shot_waves_left = 2
        self.auto_shot_cooldown = 0.0

    def start_bg(self):
        return

    def stop_bg(self):
        self.bg_player = None

    def start_prep(self):
        self.wave_auto_timer = 5.0

    def stop_prep(self):
        self.prep_player = None

    def start_shop_sound(self):
        return

    def stop_shop_sound(self):
        self.shop_sound_player = None
        self.shop_enter_player = None

    def ensure_ui_rects(self):
        if self._ui_dirty or not self.ui_rects:
            self.update_ui_rects()

    @staticmethod
    def lerp_color(c1, c2, t: float):
        return (
            int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t),
        )

    @staticmethod
    def draw_scaled_rect(bx, by, bw, bh, color, level, scale_factor=0.08):
        e = SurvivalGame.ease(level)
        # zusätzliches sanftes Overshoot für lebendige Buttons
        overshoot = 0.02 * e
        scale = 1.0 + scale_factor * e + overshoot
        cx = bx + bw / 2
        cy = by + bh / 2
        dw = bw * scale
        dh = bh * scale
        arcade.draw_lbwh_rectangle_filled(cx - dw / 2, cy - dh / 2, dw, dh, color)

    @staticmethod
    def ease(level: float) -> float:
        # Smoothstep easing for softer animation
        return level * level * (3 - 2 * level)

    def is_hover(self, key: str, x: float = None, y: float = None) -> bool:
        if x is None:
            x = self.mouse_x
        if y is None:
            y = self.mouse_y
        rect = self.ui_rects.get(key)
        if not rect:
            return False
        bx, by, bw, bh = rect
        return bx <= x <= bx + bw and by <= y <= by + bh

    def update_ui_rects(self):
        # Menu
        bw, bh = 360, 100
        bx = self.width // 2 - bw // 2
        by = self.height // 2 - bh // 2
        self.ui_rects["start_button"] = (bx, by, bw, bh)

        # Game
        self.ui_rects["wave_button"] = self.get_wave_button_rect()
        self.ui_rects["prep_upgrade"] = (0, 0, 0, 0)
        self.ui_rects["info_button"] = (0, 0, 0, 0)
        panel_x = 20
        panel_y = self.height - 240
        panel_w = 340
        panel_h = 120
        box_h = 58
        inner_x = panel_x + 14
        inner_w = panel_w - 28
        weapon_box_y = panel_y + 16
        self.ui_rects["upgrade_panel_window"] = (panel_x, panel_y, panel_w, panel_h)
        self.ui_rects["upgrade_panel_weapon"] = (inner_x, weapon_box_y, inner_w, box_h)
        self.ui_rects["upgrade_panel_targeter"] = (0, 0, 0, 0)
        # Settings deaktiviert, aber KeyError vermeiden
        self.ui_rects["settings_button"] = (0, 0, 0, 0)
        self.ui_rects["upgrade_close"] = (0, 0, 0, 0)
        self.ui_rects["upgrade_buy"] = (0, 0, 0, 0)
        self.ui_rects["upgrade_targeter"] = (0, 0, 0, 0)
        # Haus-Upgrades-Schalter deaktiviert
        self.ui_rects["house_upgrades"] = (0, 0, 0, 0)

        self.ui_rects["info_back"] = (0, 0, 0, 0)
        self.ui_rects["settings_back"] = (self.width - 220, self.height - 90, 200, 60)
        self.ui_rects["gameover_restart"] = (self.width / 2 - 140, self.height / 2 - 120, 280, 80)
        # Admin-Buttons (Settings unlocked)
        center_x = self.width / 2
        base_y = self.height - 360
        bw = 420
        bh = 60
        self.ui_rects["settings_ammo"] = (center_x - bw/2, base_y, bw, bh)
        self.ui_rects["settings_health"] = (center_x - bw/2, base_y - 80, bw, bh)
        self.ui_rects["settings_energy"] = (center_x - bw/2, base_y - 160, bw, bh)
        self.ui_rects["settings_coins"] = (center_x - bw/2, base_y - 240, bw, bh)

        # Shop
        self.ui_rects["shop_buy_one"] = self.get_shop_buy_one_button_rect()
        self.ui_rects["shop_energy"] = self.get_shop_energy_button_rect()
        self.ui_rects["shop_auto"] = self.get_shop_auto_button_rect()
        self.ui_rects["shop_leave"] = self.get_shop_leave_button_rect()
        self.cached_energy_cost = None
        self._ui_dirty = False
        self.compute_shop_rects()

    def compute_shop_rects(self):
        # buy-one Button: statisch, nur anlegen falls noch nicht vorhanden
        if "shop_buy_one" not in self.ui_rects:
            txt = arcade.Text(self.shop_buy_one_label, 0, 0, arcade.color.WHITE, 24, anchor_x="center", anchor_y="center")
            bw = txt.content_width + 100
            bh = txt.content_height + 42
            bx = self.width / 2 - bw / 2
            by = self.height - 400
            self.ui_rects["shop_buy_one"] = (bx, by, bw, bh)

        missing_energy = max(0, 100 - int(self.energy))
        energy_cost = min(5, missing_energy) * 5
        if self.cached_energy_cost != energy_cost or "shop_energy" not in self.ui_rects:
            energy_label = f"⚡ Energie +5%   Preis: {energy_cost}"
            txt2 = arcade.Text(energy_label, 0, 0, arcade.color.WHITE, 24, anchor_x="center", anchor_y="center")
            bw2 = txt2.content_width + 100
            bh2 = txt2.content_height + 42
            bx2 = self.width / 2 - bw2 / 2
            by2 = self.height - 480
            self.ui_rects["shop_energy"] = (bx2, by2, bw2, bh2)
            self.cached_energy_cost = energy_cost

        # leave Button bleibt unverändert

    def draw_cached_text(self, key, text, x, y, color, size, anchor_x="left", anchor_y="baseline"):
        sig = (size, anchor_x, anchor_y)
        cached = self.text_cache.get(key)
        if cached is None or cached["sig"] != sig:
            obj = arcade.Text(text, x, y, color, size, anchor_x=anchor_x, anchor_y=anchor_y)
            self.text_cache[key] = {"sig": sig, "obj": obj}
        else:
            obj = cached["obj"]
            obj.text = text
            obj.x = x
            obj.y = y
            obj.color = color
        obj.draw()

    def update_hover_levels(self, delta_time: float):
        active_keys = []
        if self.state == "menu":
            if self.name_confirmed:
                active_keys = ["start_button"]
        elif self.state == "game":
            active_keys = ["wave_button"]
            active_keys.extend(["upgrade_panel_window"])
        elif self.state == "settings":
            active_keys = []
        elif self.state == "shop":
            active_keys = ["shop_buy_one", "shop_energy", "shop_leave"]
            if not self.auto_shot_owned:
                active_keys.append("shop_auto")
        elif self.state == "gameover":
            active_keys = ["gameover_restart"]

        # Physikalisch geglättetes Hover (Feder-Dämpfer)
        k = 4200.0     # noch direkter für Klick-/Hover-Reaktion
        d = 240.0      # stabil genug ohne Flattern
        for key in active_keys:
            target = 1.0 if self.is_hover(key) else 0.0
            x = self.hover_level.get(key, 0.0)
            v = self.hover_velocity.get(key, 0.0)
            # x'' = k*(target - x) - d*v
            a = k * (target - x) - d * v
            v += a * delta_time
            x += v * delta_time
            # clamp and reset small values
            if x < 0.0:
                x = 0.0
                v = 0.0
            elif x > 1.0:
                x = 1.0
                v = 0.0
            self.hover_level[key] = x
            self.hover_velocity[key] = v

        # Auto-Schuss Cooldown
        if self.auto_shot_cooldown > 0:
            self.auto_shot_cooldown -= delta_time
            if self.auto_shot_cooldown < 0:
                self.auto_shot_cooldown = 0.0
        if self.weapon_shot_cooldown > 0:
            self.weapon_shot_cooldown -= delta_time
            if self.weapon_shot_cooldown < 0:
                self.weapon_shot_cooldown = 0.0
        if self.weapon_hold_timer > 0:
            self.weapon_hold_timer -= delta_time
            if self.weapon_hold_timer < 0:
                self.weapon_hold_timer = 0.0
    def on_resize(self, width, height):
        super().on_resize(width, height)
        self._ui_dirty = True

    def leave_shop(self):
        self.state = "game"
        self.portal_cooldown_timer = PORTAL_COOLDOWN
        self.player.center_x = 0
        self.player.center_y = 0
        self.stop_shop_sound()
        # Shop-Eintritts-Sound ist einmalig, muss nicht gestoppt werden; falls geloopt wird, hier stoppen
        # (Arcade play_sound returns player, hier nicht gespeichert, daher kein expliziter Stop nötig)
        self.cached_energy_cost = None
        if not self.wave_active:
            self.start_prep()

    def screen_to_world(self, x, y):
        cx, cy = self.camera.position
        dx = (x - self.width / 2) / max(self.camera_zoom, 1e-6)
        dy = (y - self.height / 2) / max(self.camera_zoom, 1e-6)
        wx = dx + cx
        wy = dy + cy
        return wx, wy

    def start_wave(self):
        if self.wave_active:
            return
        if self.wave_started_once and self.wave_completed:
            self.wave_number += 1
        self.current_spawn_interval = 1.0
        self.current_enemy_speed = max(90, ENEMY_SPEED * 0.22 + (self.wave_number - 1) * 12)
        self.wave_active = True
        self.wave_started_once = True
        self.wave_completed = False
        self.wave_timer = 0
        self.spawn_timer = 0
        self.wave_message = ""
        self.wave_message_timer = 0.0
        self.spawn_cycles_done = 0
        self.spawn_cycles_per_wave = 0
        self.wave_spawn_goal = 5 + (self.wave_number - 1) * 2
        self.wave_spawned_total = 0
        self.wave_kills = 0
        self.wave_lives_lost = 0
        self.wave_reward_coins = 0
        self.stop_prep()
        self.start_bg()
        self.wave_auto_timer = 5.0
        if self.auto_shot_owned and self.auto_shot_waves_left <= 0:
            self.auto_shot_owned = False

    def fire_bullet_towards(self, target_x, target_y, apply_cooldown=True):
        if not self.weapon_equipped:
            return False
        if apply_cooldown and self.weapon_shot_cooldown > 0:
            return False
        dx = target_x - self.player.center_x
        dy = target_y - self.player.center_y
        dist = math.hypot(dx, dy)
        if dist == 0:
            return False
        dir_x = dx / dist
        dir_y = dy / dist
        # Schuss startet ~5mm rechts vom linken Rand (~19px) und ~1.5cm unterhalb des oberen Spielerrands (~57px)
        start_x = self.player.center_x - self.player.width / 2 + 30
        start_y = self.player.center_y + self.player.height / 2 - 57

        bullet_speed = ((170 + (100/60)) + 50 + 100 + 300 + 120)

        def spawn_single_bullet(local_dir_x, local_dir_y):
            bullet = arcade.SpriteCircle(5.5, arcade.color.ORANGE_PEEL,
                                         center_x=start_x,
                                         center_y=start_y)
            bullet.alpha = 255
            bullet.change_x = local_dir_x * bullet_speed
            bullet.change_y = local_dir_y * bullet_speed
            bullet.life_time = 1e9  # quasi unendlich
            self.bullet_list.append(bullet)

        if self.weapon_level in (1, 3):
            spawn_single_bullet(dir_x, dir_y)
            if apply_cooldown:
                self.weapon_shot_cooldown = self.get_weapon_cooldown()
            return True

        spread_angle = 0.12
        base_angle = math.atan2(dir_y, dir_x)
        for offset in (-spread_angle, 0.0, spread_angle):
            angle = base_angle + offset
            spawn_single_bullet(math.cos(angle), math.sin(angle))

        if apply_cooldown:
            cooldown = self.get_weapon_cooldown()
            if cooldown > 0:
                self.weapon_shot_cooldown = cooldown
        return True

    def fire_bullet(self, screen_x, screen_y):
        wx, wy = self.screen_to_world(screen_x, screen_y)
        return self.fire_bullet_towards(wx, wy, apply_cooldown=True)

    def on_close(self):
        self.stop_bg()
        self.stop_shop_sound()
        self.stop_prep()
        super().on_close()

    # ---------------- UPDATE ----------------
    def on_update(self, delta_time):

        if self.admin_message_timer > 0:
            self.admin_message_timer -= delta_time
            if self.admin_message_timer <= 0:
                self.admin_message = ""

        # Caret blink
        if self.admin_focus:
            self.caret_timer += delta_time
            if self.caret_timer >= 0.5:
                self.caret_timer = 0.0
                self.caret_visible = not self.caret_visible
        else:
            self.caret_visible = True
            self.caret_timer = 0.0

        self.update_hover_levels(delta_time)

        if self.state != "game":
            return

        if self.player_damage_cooldown > 0:
            self.player_damage_cooldown -= delta_time
            if self.player_damage_cooldown < 0:
                self.player_damage_cooldown = 0.0

        # Auto-Schuss auslösen, falls gekauft
        if self.auto_shot_owned and self.wave_active and self.auto_shot_cooldown <= 0:
            target_enemy = None
            target_dist = None
            for enemy in self.enemies:
                if enemy.is_dying or enemy.is_spawning:
                    continue
                dist = arcade.get_distance_between_sprites(self.player, enemy)
                if dist <= SHOT_RADIUS and (target_dist is None or dist < target_dist):
                    target_dist = dist
                    target_enemy = enemy
            if target_enemy is not None:
                self.fire_bullet_towards(target_enemy.center_x, target_enemy.center_y, apply_cooldown=False)
                self.auto_shot_cooldown = 0.4

        if self.mouse_left_down and self.weapon_hold_timer <= 0:
            if self.fire_bullet(self.mouse_x, self.mouse_y):
                self.weapon_hold_timer = 0.02
            else:
                self.weapon_hold_timer = 0.02

        # Auto-Start nach Vorbereitung
        if not self.wave_active:
            self.wave_auto_timer -= delta_time
            if self.wave_auto_timer <= 0:
                self.start_wave()
        else:
            self.wave_auto_timer = 5.0

        # Bullets bewegen und Lebensdauer prüfen
        for bullet in list(self.bullet_list):
            bullet.center_x += bullet.change_x * delta_time
            bullet.center_y += bullet.change_y * delta_time
            bullet.life_time -= delta_time
                # Kugeln außerhalb der Arena entfernen
            if (bullet.center_x < -MAP_WIDTH / 2 or
                bullet.center_x > MAP_WIDTH / 2 or
                bullet.center_y < -MAP_HEIGHT / 2 or
                bullet.center_y > MAP_HEIGHT / 2):
                bullet.kill()
                continue
            if bullet.life_time <= 0:
                bullet.kill()
                continue
            hits = arcade.check_for_collision_with_list(bullet, self.enemies)
            for enemy in hits:
                if enemy.is_dying or enemy.is_spawning:
                    continue
                enemy.kill()
                bullet.kill()
                self.wave_kills += 1
                self.gems += 10
                break

        self.prev_player_pos = (self.player.center_x, self.player.center_y)
        self.player.change_x = 0
        self.player.change_y = 0
        speed = PLAYER_SPEED

        move_x = 0
        move_y = 0
        if arcade.key.A in self.keys:
            move_x -= 1
        if arcade.key.D in self.keys:
            move_x += 1
        if arcade.key.W in self.keys:
            move_y += 1
        if arcade.key.S in self.keys:
            move_y -= 1

        if move_x != 0 or move_y != 0:
            length = math.hypot(move_x, move_y)
            self.player.change_x = (move_x / length) * speed
            self.player.change_y = (move_y / length) * speed

        self.player.center_x += self.player.change_x * delta_time
        self.player.center_y += self.player.change_y * delta_time

        moving = self.player.change_x != 0 or self.player.change_y != 0
        self.sprint_drain_acc = 0.0

        energy_int = int(self.energy)
        if energy_int != self.last_energy_int:
            self.last_energy_int = energy_int
            self.cached_energy_cost = None

        # Keine Fades mehr: nichts zu tun

        # Map Grenzen
        self.player.center_x = max(-MAP_WIDTH//2, min(MAP_WIDTH//2, self.player.center_x))
        self.player.center_y = max(-MAP_HEIGHT//2, min(MAP_HEIGHT//2, self.player.center_y))

        if self.portal_cooldown_timer > 0:
            self.portal_cooldown_timer -= delta_time
            if self.portal_cooldown_timer < 0:
                self.portal_cooldown_timer = 0.0

        if not self.wave_active and self.portal_cooldown_timer <= 0:
            pass

        # Wave System
        if self.wave_message_timer > 0:
            self.wave_message_timer -= delta_time
            if self.wave_message_timer <= 0:
                self.wave_message = ""
                self.wave_message_timer = 0.0

        if self.wave_active:
            self.wave_timer += delta_time
            self.spawn_timer += delta_time

            if self.spawn_timer >= self.current_spawn_interval and self.wave_spawned_total < self.wave_spawn_goal:
                self.spawn_enemies()
                self.spawn_timer = 0
                self.wave_spawned_total += 1

            alive_enemies = 0
            for enemy in self.enemies:
                if not enemy.is_dying:
                    alive_enemies += 1

            if self.wave_spawned_total >= self.wave_spawn_goal and alive_enemies == 0:
                self.wave_active = False
                self.stop_bg()
                if self.state == "game":
                    self.start_prep()
                self.player_health = self.player_health_max
                self.player_damage_cooldown = 0.0
                self.wave_completed = True
                self.wave_message = "WELLE BESTANDEN"
                self.wave_message_timer = 3.0
                self.wave_reward_coins = self.wave_kills - self.wave_lives_lost + (self.wave_number * 10)
                self.total_coins += self.wave_reward_coins
                if self.auto_shot_owned and self.auto_shot_waves_left > 0:
                    self.auto_shot_waves_left -= 1
                    if self.auto_shot_waves_left <= 0:
                        self.auto_shot_owned = False

        # Enemy Update
        for enemy in self.enemies:
            if enemy.is_spawning:
                enemy.spawn_timer -= delta_time
                if enemy.spawn_timer <= 0:
                    enemy.is_spawning = False
                    enemy.texture = self.enemy_texture
                    enemy.scale = 0.5
                continue
            if enemy.is_dying:
                enemy.death_timer -= delta_time
                if enemy.death_timer <= 0:
                    enemy.kill()
                continue

            target_x = self.player.center_x
            target_y = self.player.center_y
            dx = target_x - enemy.center_x
            dy = target_y - enemy.center_y
            dist = math.hypot(dx, dy)

            if dist > 0:
                enemy.center_x += (dx / dist) * enemy.base_speed * delta_time
                enemy.center_y += (dy / dist) * enemy.base_speed * delta_time

            enemy.center_x = max(-MAP_WIDTH//2, min(MAP_WIDTH//2, enemy.center_x))
            enemy.center_y = max(-MAP_HEIGHT//2, min(MAP_HEIGHT//2, enemy.center_y))

            if arcade.check_for_collision(enemy, self.player) and self.player_damage_cooldown <= 0:
                self.player_health = max(0, self.player_health - 10)
                self.wave_lives_lost += 1
                self.player_damage_cooldown = 0.35

        if self.player_health <= 0:
            self.state = "gameover"

        self.camera.position = (self.player.center_x, self.player.center_y)

    # ---------------- SPAWN ----------------
    def spawn_enemies(self):
        image = str(IMG_DIR / "gegner.png")
        amount = 1
        for _ in range(amount):
            enemy = Enemy(str(IMG_DIR / "loch.png"))
            enemy.scale = 0.28
            enemy.base_speed = self.current_enemy_speed
            enemy.is_spawning = True
            enemy.spawn_timer = SPAWN_PREVIEW_DURATION
            for _attempt in range(24):
                spawn_x = random.uniform(-MAP_WIDTH / 2, MAP_WIDTH / 2)
                spawn_y = random.uniform(-MAP_HEIGHT / 2, MAP_HEIGHT / 2)
                if math.hypot(spawn_x - self.player.center_x, spawn_y - self.player.center_y) >= 420:
                    enemy.center_x = spawn_x
                    enemy.center_y = spawn_y
                    break
            else:
                enemy.center_x = random.uniform(-MAP_WIDTH / 2, MAP_WIDTH / 2)
                enemy.center_y = random.uniform(-MAP_HEIGHT / 2, MAP_HEIGHT / 2)
            self.enemies.append(enemy)

    # ---------------- DRAW ----------------
    def on_draw(self):
        self.clear()
        self.ensure_ui_rects()

        if self.state == "menu":

            arcade.draw_text("SURVIVAL MAP",
                             self.width/2, self.height/2+150,
                             arcade.color.WHITE, 60,
                             anchor_x="center")
            caret = "|" if self.caret_visible else ""
            bx, by, bw, bh = self.ui_rects["start_button"]

            start_ready = self.name_confirmed
            if start_ready:
                level = self.ease(self.hover_level.get("start_button", 0.0))
                start_color = self.lerp_color(arcade.color.GRAY, arcade.color.LIGHT_GRAY, level)
                self.draw_scaled_rect(bx, by, bw, bh, start_color, level, scale_factor=0.28)
                arcade.draw_text("START",
                                 self.width//2, self.height//2,
                                 arcade.color.WHITE, 30,
                                 anchor_x="center", anchor_y="center")
                self.start_button = (bx, by, bw, bh)
            else:
                arcade.draw_text("Name eingeben und mit Enter bestätigen",
                                 self.width//2, self.height//2,
                                 arcade.color.LIGHT_GRAY, 24,
                                 anchor_x="center", anchor_y="center")
                self.start_button = None
            # Name-Feld unter START (nur solange nicht bestätigt)
            if not self.name_confirmed:
                field_w = 520
                field_h = 60
                field_x = self.width/2 - field_w/2
                field_y = self.height/2 - 200
                arcade.draw_text("Name:", field_x, field_y + field_h + 10, arcade.color.WHITE, 24)
                arcade.draw_lbwh_rectangle_outline(field_x, field_y, field_w, field_h, arcade.color.WHITE, border_width=3)
                caret = "|" if self.caret_visible else ""
                arcade.draw_text(self.player_name + caret,
                                 field_x + 10, field_y + field_h/2,
                                 arcade.color.WHITE, 26,
                                 anchor_y="center")

        elif self.state == "game":

            with self.camera.activate():
                # Welten-Barriere (rot)
                arcade.draw_lbwh_rectangle_outline(-MAP_WIDTH/2, -MAP_HEIGHT/2, MAP_WIDTH, MAP_HEIGHT,
                                                   arcade.color.RED, border_width=6)
                self.decor_list.draw()
                self.enemies.draw()
                for bullet in self.bullet_list:
                    arcade.draw_circle_filled(bullet.center_x, bullet.center_y, 5.5, arcade.color.ORANGE_PEEL)
                self.player_list.draw()
                arcade.draw_text(self.player_name,
                                 self.player.center_x,
                                 self.player.center_y + self.player.height/2 + 20,
                                 arcade.color.BLACK, 18,
                                 anchor_x="center")
                # Markiere Gegner im Radius
                for enemy in self.enemies:
                    if enemy.is_dying:
                        continue
                    dist = arcade.get_distance_between_sprites(self.player, enemy)
                    if dist <= SHOT_RADIUS:
                        pass

            # Wave Button
            # Anzeigen
            hud_left_x = 20
            hud_left_y = self.height - 40
            name_text = self.player_name if self.player_name else "Spieler"
            health_ratio = 0 if self.player_health_max <= 0 else self.player_health / self.player_health_max
            arcade.draw_text("Leben",
                             hud_left_x, hud_left_y + 20,
                             arcade.color.WHITE, 18)
            arcade.draw_lbwh_rectangle_filled(hud_left_x, hud_left_y - 6, 220, 22, arcade.color.DARK_RED)
            arcade.draw_lbwh_rectangle_filled(hud_left_x, hud_left_y - 6, 220 * health_ratio, 22, arcade.color.SPRING_GREEN)
            arcade.draw_lbwh_rectangle_outline(hud_left_x, hud_left_y - 6, 220, 22, arcade.color.WHITE, 2)
            arcade.draw_text(f"{int(self.player_health)}/{self.player_health_max}",
                             hud_left_x + 110, hud_left_y + 5,
                             arcade.color.WHITE, 14,
                             anchor_x="center", anchor_y="center")
            arcade.draw_text(f"Name: {name_text}",
                             hud_left_x, hud_left_y - 36,
                             arcade.color.WHITE, 20)
            panel_x = 20
            panel_y = self.height - 240
            panel_w = 340
            panel_h = 120
            box_h = 58
            inner_x = panel_x + 14
            inner_w = panel_w - 28
            arcade.draw_lbwh_rectangle_filled(panel_x, panel_y, panel_w, panel_h, (10, 12, 14, 185))
            arcade.draw_lbwh_rectangle_outline(panel_x, panel_y, panel_w, panel_h, arcade.color.LIGHT_GRAY, 2)
            arcade.draw_text("UPGRADES",
                             panel_x + 16, panel_y + panel_h - 34,
                             arcade.color.GOLD, 22)
            weapon_box_y = panel_y + 16

            arcade.draw_lbwh_rectangle_filled(inner_x, weapon_box_y, inner_w, box_h, (34, 28, 24, 220))
            arcade.draw_lbwh_rectangle_outline(inner_x, weapon_box_y, inner_w, box_h,
                                               arcade.color.GOLD, 2)
            next_weapon_name = self.get_next_weapon_name()
            next_cost = self.get_weapon_upgrade_cost()
            arcade.draw_text(next_weapon_name,
                             inner_x + 14, weapon_box_y + box_h - 22,
                             arcade.color.WHITE, 16)
            if next_cost is None:
                next_weapon_cost_text = "Kein weiteres Upgrade"
                next_weapon_cost_color = arcade.color.GOLD
            else:
                next_weapon_cost_text = f"{next_cost} Gems"
                next_weapon_cost_color = arcade.color.SPRING_GREEN if self.gems >= next_cost else arcade.color.LIGHT_GRAY
            arcade.draw_text(next_weapon_cost_text,
                             inner_x + 14, weapon_box_y + 12,
                             next_weapon_cost_color, 15)
            arcade.draw_text(f"💎 Gems: {int(self.gems)}",
                             20, 165,
                             arcade.color.GOLD, 20)
            # Wave-Button ausgeblendet
            # Waffen-Slot unten links
            slot_w, slot_h = 120, 120
            slot_x, slot_y = 20, 20
            slot_color = arcade.color.GOLD if self.weapon_equipped else arcade.color.GRAY
            arcade.draw_lbwh_rectangle_outline(slot_x, slot_y, slot_w, slot_h, slot_color, border_width=4)
            arcade.draw_text("1", slot_x + slot_w/2, slot_y + slot_h - 22, arcade.color.WHITE, 22, anchor_x="center")
            if self.pistol_texture:
                self.pistol_icon_sprite.center_x = slot_x + slot_w/2
                self.pistol_icon_sprite.center_y = slot_y + slot_h/2
                self.pistol_icon_list.draw()
            if self.wave_active:
                arcade.draw_text(f"WELLE {self.wave_number}",
                                 self.width - 10, self.height - 15,
                                 arcade.color.RED, 34,
                                 anchor_x="right", anchor_y="top")
            else:
                prep_secs = max(0, math.ceil(self.wave_auto_timer))
                arcade.draw_text(f"Vorbereitung {prep_secs}s",
                                 self.width - 10, self.height - 15,
                                 arcade.color.GREEN, 34,
                                 anchor_x="right", anchor_y="top")

            if self.wave_message:
                arcade.draw_text(self.wave_message,
                                 self.width / 2, self.height - 90,
                                 arcade.color.GOLD, 30,
                                 anchor_x="center")
                # Keine Münz-Anzeige mehr

        elif self.state == "settings":
            arcade.draw_lbwh_rectangle_filled(0, 0, self.width, self.height, (0, 0, 0, 220))
            arcade.draw_text("Einstellungen",
                             self.width / 2, self.height - 120,
                             arcade.color.WHITE, 58,
                             anchor_x="center")
            if not self.settings_unlocked:
                arcade.draw_text("Gebe den Admin-Code ein:",
                                 self.width / 2, self.height - 220,
                                 arcade.color.WHITE, 28,
                                 anchor_x="center")
                arcade.draw_lbwh_rectangle_outline(self.width / 2 - 250, self.height - 300, 500, 60, arcade.color.WHITE, 3)
                caret = "|" if (self.admin_focus and self.caret_visible) else ""
                arcade.draw_text(self.admin_input + caret,
                                 self.width / 2 - 240, self.height - 280,
                                 arcade.color.WHITE, 26,
                                 anchor_x="left", anchor_y="center")
                if self.admin_message:
                    arcade.draw_text(self.admin_message,
                                     self.width / 2, self.height - 360,
                                     arcade.color.RED, 24,
                                     anchor_x="center")
            else:
                arcade.draw_lbwh_rectangle_outline(self.width / 2 - 320, self.height / 2 - 240, 640, 480, arcade.color.WHITE, 3)
                # Buttons
                bx, by, bw, bh = self.ui_rects["settings_ammo"]
                lvl_ammo = self.ease(self.hover_level.get("settings_ammo", 0.0))
                color_ammo = self.lerp_color(arcade.color.DARK_SPRING_GREEN, arcade.color.SPRING_GREEN, lvl_ammo)
                self.draw_scaled_rect(bx, by, bw, bh, color_ammo, lvl_ammo, scale_factor=0.12)
                arcade.draw_text("Unendlich Schüsse", bx + bw/2, by + bh/2,
                                 arcade.color.WHITE, 26, anchor_x="center", anchor_y="center")

                bx, by, bw, bh = self.ui_rects["settings_health"]
                lvl_hp = self.ease(self.hover_level.get("settings_health", 0.0))
                color_hp = self.lerp_color(arcade.color.DARK_SPRING_GREEN, arcade.color.SPRING_GREEN, lvl_hp)
                self.draw_scaled_rect(bx, by, bw, bh, color_hp, lvl_hp, scale_factor=0.13)
                arcade.draw_text("Unendlich Leben", bx + bw/2, by + bh/2,
                                 arcade.color.WHITE, 26, anchor_x="center", anchor_y="center")

                bx, by, bw, bh = self.ui_rects["settings_energy"]
                lvl_en = self.ease(self.hover_level.get("settings_energy", 0.0))
                color_en = self.lerp_color(arcade.color.DARK_SPRING_GREEN, arcade.color.SPRING_GREEN, lvl_en)
                self.draw_scaled_rect(bx, by, bw, bh, color_en, lvl_en, scale_factor=0.13)
                arcade.draw_text("Energie auffüllen", bx + bw/2, by + bh/2,
                                 arcade.color.WHITE, 26, anchor_x="center", anchor_y="center")

                bx, by, bw, bh = self.ui_rects["settings_coins"]
                lvl_co = self.ease(self.hover_level.get("settings_coins", 0.0))
                color_co = self.lerp_color(arcade.color.DARK_SPRING_GREEN, arcade.color.SPRING_GREEN, lvl_co)
                self.draw_scaled_rect(bx, by, bw, bh, color_co, lvl_co, scale_factor=0.13)
                arcade.draw_text("Unendlich Münzen", bx + bw/2, by + bh/2,
                                 arcade.color.WHITE, 26, anchor_x="center", anchor_y="center")

            bx, by, bw, bh = self.ui_rects["settings_back"]
            back_level = self.ease(self.hover_level.get("settings_back", 0.0))
            leave_color = self.lerp_color(arcade.color.GRAY, arcade.color.LIGHT_GRAY, back_level)
            self.draw_scaled_rect(bx, by, bw, bh, leave_color, back_level, scale_factor=0.15)
            arcade.draw_text("Abbruch",
                             bx + bw / 2, by + bh / 2,
                             arcade.color.WHITE, 26,
                             anchor_x="center", anchor_y="center")
            if self.admin_message:
                arcade.draw_text(self.admin_message,
                                 self.width / 2, self.height - 360,
                                 arcade.color.RED, 24,
                                 anchor_x="center")

        elif self.state == "shop":
            self.state = "game"
            return

        elif self.state == "gameover":

            self.draw_cached_text("gameover_title", "GAME OVER",
                                  self.width//2, self.height//2 + 40,
                                  arcade.color.RED, 50,
                                  anchor_x="center")
            bx, by, bw, bh = self.ui_rects["gameover_restart"]
            restart_level = self.ease(self.hover_level.get("gameover_restart", 0.0))
            restart_color = self.lerp_color(arcade.color.GRAY, arcade.color.LIGHT_GRAY, restart_level)
            self.draw_scaled_rect(bx, by, bw, bh, restart_color, restart_level, scale_factor=0.15)
            self.draw_cached_text("gameover_restart_label", "Restart",
                                  bx + bw / 2, by + bh / 2,
                                  arcade.color.WHITE, 30,
                                  anchor_x="center", anchor_y="center")
