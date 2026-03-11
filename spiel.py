import arcade
import math

# ---------------- SETTINGS ----------------
SCREEN_TITLE = "Survival Map"
MAP_WIDTH = 10000
MAP_HEIGHT = 10000

PLAYER_WIDTH = 300
PLAYER_HEIGHT = 168
PLAYER_SPEED = 15

SPAWN_INTERVAL = 2.0
WAVE_DURATION = 30

ENEMY_SPEED = 5
MINIMAP_SCALE = 0.05

SHOT_RADIUS = 500
MAX_SHOTS = 30
EXPLOSION_DURATION = 0.25
PORTAL_RADIUS = 140
PORTAL_COOLDOWN = 0.4
AMMO_COST = 2

# ---------------- ENEMY ----------------
class Enemy(arcade.Sprite):
    def __init__(self, image):
        super().__init__(image, scale=0.5)
        self.base_speed = ENEMY_SPEED
        self.is_dying = False
        self.death_timer = 0.0

# ---------------- GAME ----------------
class SurvivalGame(arcade.Window):

    def __init__(self):
        super().__init__(fullscreen=True, title=SCREEN_TITLE)
        arcade.set_background_color(arcade.color.DARK_GREEN)

        self.state = "menu"
        self.camera = arcade.Camera2D()
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

        self.player_health = 100
        self.shots_left = MAX_SHOTS
        self.energy = 100.0
        self.sprint_drain_acc = 0.0

        self.start_button = None
        self.wave_button = None
        self.shop_return_button = None
        self.shop_buy_one_button = None
        self.hit_sound = arcade.load_sound("getroffen.wav")
        self.bg_sound = arcade.load_sound("hintergrund.wav")
        self.bg_player = None
        try:
            self.info_sprite = arcade.Sprite("info.png", scale=1.0)
            self.info_sprite_list = arcade.SpriteList()
            self.info_sprite_list.append(self.info_sprite)
        except Exception:
            self.info_sprite = None
            self.info_sprite_list = None
        try:
            self.win_sound = arcade.load_sound("gewonnen.wav")
        except Exception:
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

        self.player = arcade.Sprite("spieler.png")
        self.player.width = PLAYER_WIDTH
        self.player.height = PLAYER_HEIGHT
        self.player.center_x = 0
        self.player.center_y = 0
        self.player_list.append(self.player)

        self.player_health = 100
        self.shots_left = MAX_SHOTS
        self.energy = 100.0
        self.sprint_drain_acc = 0.0
        self.portal_x = 0
        self.portal_y = MAP_HEIGHT // 2 - 220
        self.portal_sprite = arcade.Sprite("portal.png", scale=0.8)
        self.portal_sprite.center_x = self.portal_x
        self.portal_sprite.center_y = self.portal_y
        self.portal_list.append(self.portal_sprite)

        positions = [
            (-MAP_WIDTH//2, -MAP_HEIGHT//2),
            (MAP_WIDTH//2, -MAP_HEIGHT//2),
            (-MAP_WIDTH//2, MAP_HEIGHT//2),
            (MAP_WIDTH//2, MAP_HEIGHT//2)
        ]

        self.spawners = []
        for pos in positions:
            spawner = arcade.Sprite("spawner.png")
            spawner.center_x, spawner.center_y = pos
            self.spawner_list.append(spawner)
            self.spawners.append(spawner)

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

        if self.state == "game":
            if key == arcade.key.SPACE and self.shots_left > 0:
                self.radius_shot()
            if key == arcade.key.M:
                self.show_minimap = not self.show_minimap
        elif self.state == "info":
            if key == arcade.key.ESCAPE:
                self.state = "game"
        elif self.state == "shop":
            if key == arcade.key.ESCAPE:
                self.leave_shop()

    def on_key_release(self, key, modifiers):
        self.keys.discard(key)

    def on_mouse_press(self, x, y, button, modifiers):
        self.ensure_ui_rects()

        if self.state == "menu":
            bx, by, bw, bh = self.ui_rects["start_button"]
            if bx <= x <= bx + bw and by <= y <= by + bh:
                self.setup_game()
                self.state = "game"
                return

        elif self.state == "game":
            bx, by, bw, bh = self.ui_rects["info_button"]
            if bx <= x <= bx + bw and by <= y <= by + bh:
                self.state = "info"
                return

            bx, by, bw, bh = self.ui_rects["wave_button"]
            if bx <= x <= bx + bw and by <= y <= by + bh:
                if not self.wave_active:
                    if self.wave_started_once and self.wave_completed:
                        self.wave_number += 1
                    self.current_spawn_interval = max(0.4, SPAWN_INTERVAL - (self.wave_number - 1) * 0.2)
                    self.current_enemy_speed = ENEMY_SPEED + (self.wave_number - 1) * 0.8
                    self.wave_active = True
                    self.wave_started_once = True
                    self.wave_completed = False
                    self.wave_timer = 0
                    self.spawn_timer = 0
                    self.wave_message = ""
                    self.wave_message_timer = 0.0
                    self.spawn_cycles_done = 0
                    self.spawn_cycles_per_wave = 3 + self.wave_number
                    self.wave_kills = 0
                    self.wave_lives_lost = 0
                    self.wave_reward_coins = 0
                    self.start_bg()
                return

        elif self.state == "info":
            bx, by, bw, bh = self.ui_rects["info_back"]
            if bx <= x <= bx + bw and by <= y <= by + bh:
                self.state = "game"
                return

        elif self.state == "shop":
            bx, by, bw, bh = self.ui_rects["shop_leave"]
            if bx <= x <= bx + bw and by <= y <= by + bh:
                self.leave_shop()
                return

            bx, by, bw, bh = self.ui_rects["shop_buy_one"]
            if bx <= x <= bx + bw and by <= y <= by + bh:
                self.buy_ammo(1)
                return

        elif self.state == "gameover":
            self.state = "menu"
            self.stop_bg()

    # ---------------- RADIUS SHOT ----------------
    def radius_shot(self):
        enemies_to_kill = []
        for enemy in self.enemies:
            if enemy.is_dying:
                continue
            dist = arcade.get_distance_between_sprites(self.player, enemy)
            if dist <= SHOT_RADIUS:
                enemies_to_kill.append((dist, enemy))

        enemies_to_kill.sort(key=lambda item: item[0])
        hits = min(len(enemies_to_kill), self.shots_left)

        for _, enemy in enemies_to_kill[:hits]:
            enemy.texture = arcade.load_texture("explosion.png")
            enemy.is_dying = True
            enemy.death_timer = EXPLOSION_DURATION
            self.wave_kills += 1
            arcade.play_sound(self.hit_sound)
        self.shots_left -= hits

    def get_wave_button_rect(self):
        return (20, 20, 250, 50)

    def get_shop_leave_button_rect(self):
        text_obj = arcade.Text(self.shop_leave_label, 0, 0, arcade.color.WHITE, 26, anchor_x="center", anchor_y="center")
        bw = text_obj.content_width + 90
        bh = text_obj.content_height + 30
        bx = self.width / 2 - bw / 2
        by = 120
        return (bx, by, bw, bh)

    def get_shop_buy_one_button_rect(self):
        text_obj = arcade.Text(self.shop_buy_one_label, 0, 0, arcade.color.WHITE, 24, anchor_x="center", anchor_y="center")
        bw = text_obj.content_width + 60
        bh = text_obj.content_height + 26
        bx = self.width / 2 - bw / 2
        by = self.height - 400
        return (bx, by, bw, bh)


    def buy_ammo(self, amount):
        if amount <= 0:
            return
        cost = amount * AMMO_COST
        if self.total_coins < cost:
            return
        self.total_coins -= cost
        self.shots_left += amount

    def start_bg(self):
        if not self.bg_player:
            self.bg_player = arcade.play_sound(self.bg_sound, volume=0.25, loop=True)

    def stop_bg(self):
        if self.bg_player:
            self.bg_player.pause()
            self.bg_player = None

    def ensure_ui_rects(self):
        if self._ui_dirty or not self.ui_rects:
            self.update_ui_rects()

    def update_ui_rects(self):
        # Menu
        bw, bh = 300, 80
        bx = self.width // 2 - bw // 2
        by = self.height // 2 - bh // 2
        self.ui_rects["start_button"] = (bx, by, bw, bh)

        # Game
        self.ui_rects["wave_button"] = self.get_wave_button_rect()
        self.ui_rects["info_button"] = (self.width - 70, self.height - 70, 50, 50)

        # Info overlay
        self.ui_rects["info_back"] = (self.width / 2 - 160, 120, 320, 70)

        # Shop
        self.ui_rects["shop_buy_one"] = self.get_shop_buy_one_button_rect()
        self.ui_rects["shop_leave"] = self.get_shop_leave_button_rect()
        self._ui_dirty = False

    def on_resize(self, width, height):
        super().on_resize(width, height)
        self._ui_dirty = True

    def leave_shop(self):
        self.state = "game"
        self.portal_cooldown_timer = PORTAL_COOLDOWN
        self.player.center_x = 0
        self.player.center_y = 0

    def on_close(self):
        self.stop_bg()
        super().on_close()

    # ---------------- UPDATE ----------------
    def on_update(self, delta_time):

        if self.state != "game":
            return

        # Movement
        self.player.change_x = 0
        self.player.change_y = 0
        shift_down = arcade.key.LSHIFT in self.keys or arcade.key.RSHIFT in self.keys
        speed = PLAYER_SPEED + (8 if shift_down and self.energy > 0 else 0)

        if arcade.key.UP in self.keys:
            self.player.change_y = speed
        if arcade.key.DOWN in self.keys:
            self.player.change_y = -speed
        if arcade.key.LEFT in self.keys:
            self.player.change_x = -speed
        if arcade.key.RIGHT in self.keys:
            self.player.change_x = speed

        self.player.center_x += self.player.change_x
        self.player.center_y += self.player.change_y

        moving = self.player.change_x != 0 or self.player.change_y != 0
        if shift_down and moving and self.energy > 0:
            self.sprint_drain_acc += delta_time
            while self.sprint_drain_acc >= 2.0 and self.energy > 0:
                self.energy = max(0.0, self.energy - 1.0)
                self.sprint_drain_acc -= 2.0
        elif not shift_down:
            self.sprint_drain_acc = 0.0

        # Map Grenzen
        self.player.center_x = max(-MAP_WIDTH//2, min(MAP_WIDTH//2, self.player.center_x))
        self.player.center_y = max(-MAP_HEIGHT//2, min(MAP_HEIGHT//2, self.player.center_y))

        if self.portal_cooldown_timer > 0:
            self.portal_cooldown_timer -= delta_time
            if self.portal_cooldown_timer < 0:
                self.portal_cooldown_timer = 0.0

        if not self.wave_active and self.portal_cooldown_timer <= 0:
            portal_distance = math.hypot(self.player.center_x - self.portal_x, self.player.center_y - self.portal_y)
            if portal_distance <= PORTAL_RADIUS:
                self.state = "shop"
                return

        # Wave System
        if self.wave_message_timer > 0:
            self.wave_message_timer -= delta_time
            if self.wave_message_timer <= 0:
                self.wave_message = ""
                self.wave_message_timer = 0.0

        if self.wave_active:
            self.wave_timer += delta_time
            self.spawn_timer += delta_time

            if self.spawn_timer >= self.current_spawn_interval and self.spawn_cycles_done < self.spawn_cycles_per_wave:
                self.spawn_enemies()
                self.spawn_timer = 0
                self.spawn_cycles_done += 1

            alive_enemies = 0
            for enemy in self.enemies:
                if not enemy.is_dying:
                    alive_enemies += 1

            if self.spawn_cycles_done >= self.spawn_cycles_per_wave and alive_enemies == 0:
                self.wave_active = False
                self.stop_bg()
                self.wave_completed = True
                self.wave_message = "WELLE BESTANDEN"
                self.wave_message_timer = 3.0
                self.wave_reward_coins = self.wave_kills - self.wave_lives_lost + (self.wave_number * 10)
                self.total_coins += self.wave_reward_coins
                if self.win_sound:
                    arcade.play_sound(self.win_sound)

        # Enemy Update
        for enemy in self.enemies:
            if enemy.is_dying:
                enemy.death_timer -= delta_time
                if enemy.death_timer <= 0:
                    enemy.kill()
                continue

            dx = self.player.center_x - enemy.center_x
            dy = self.player.center_y - enemy.center_y
            dist = math.hypot(dx, dy)

            if dist > 0:
                enemy.center_x += (dx / dist) * enemy.base_speed
                enemy.center_y += (dy / dist) * enemy.base_speed

            enemy.center_x = max(-MAP_WIDTH//2, min(MAP_WIDTH//2, enemy.center_x))
            enemy.center_y = max(-MAP_HEIGHT//2, min(MAP_HEIGHT//2, enemy.center_y))

            if arcade.check_for_collision(enemy, self.player):
                enemy.kill()
                self.player_health -= 1  # nur 1 Schaden
                self.wave_kills += 1
                self.wave_lives_lost += 1

        if self.player_health <= 0:
            self.state = "gameover"

        self.camera.position = (self.player.center_x, self.player.center_y)

    # ---------------- SPAWN ----------------
    def spawn_enemies(self):
        images = ["gegner.png", "gegner2.png", "gegner3.png", "gegner4.png"]

        for i, spawner in enumerate(self.spawners):
            amount = 1 + (self.wave_number - 1) // 2
            for _ in range(amount):
                enemy = Enemy(images[i])
                enemy.base_speed = self.current_enemy_speed
                enemy.center_x = spawner.center_x
                enemy.center_y = spawner.center_y
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

            bx, by, bw, bh = self.ui_rects["start_button"]

            arcade.draw_lbwh_rectangle_filled(bx, by, bw, bh, arcade.color.GRAY)
            arcade.draw_text("START",
                             self.width//2, self.height//2,
                             arcade.color.WHITE, 30,
                             anchor_x="center", anchor_y="center")
            self.start_button = (bx, by, bw, bh)

        elif self.state == "game":

            with self.camera.activate():
                if not self.wave_active:
                    self.portal_list.draw()
                self.spawner_list.draw()
                self.enemies.draw()
                self.player_list.draw()

                if not self.wave_active:
                    arcade.draw_text("Shop im Portal",
                                     self.portal_x, self.portal_y - 190,
                                     arcade.color.WHITE, 22,
                                     anchor_x="center")

            # Wave Button
            bx, by, bw, bh = self.ui_rects["wave_button"]

            arcade.draw_lbwh_rectangle_filled(bx, by, bw, bh, arcade.color.GRAY)
            wave_button_text = "Welle starten" if not self.wave_started_once else "Neue Welle"
            arcade.draw_text(wave_button_text,
                             bx + bw/2, by + bh/2,
                             arcade.color.WHITE, 20,
                             anchor_x="center", anchor_y="center")
            # Anzeigen
            hud_left_x = 20
            hud_left_y = self.height - 40
            hud_left_gap = 55
            arcade.draw_text(f"❤️ Leben: {self.player_health}",
                             hud_left_x, hud_left_y,
                             arcade.color.WHITE, 20)
            arcade.draw_text(f"🔫 Schüsse: {self.shots_left}",
                             hud_left_x, hud_left_y - hud_left_gap,
                             arcade.color.WHITE, 20)
            arcade.draw_text(f"⚡ Energie: {int(self.energy)}%",
                             hud_left_x, hud_left_y - hud_left_gap * 2,
                             arcade.color.WHITE, 20)
            arcade.draw_text(f"🪙 Münzen: {self.total_coins}",
                             hud_left_x, hud_left_y - hud_left_gap * 3,
                             arcade.color.WHITE, 20)
            if self.wave_active:
                arcade.draw_text(f"WELLE {self.wave_number}",
                                 self.width - 80, self.height - 15,
                                 arcade.color.RED, 34,
                                 anchor_x="right", anchor_y="top")
            else:
                arcade.draw_text("Vorbereitung",
                                 self.width - 80, self.height - 15,
                                 arcade.color.GREEN, 34,
                                 anchor_x="right", anchor_y="top")

            bx, by, bw, bh = self.ui_rects["info_button"]
            if self.info_sprite:
                self.info_sprite.center_x = bx + bw / 2
                self.info_sprite.center_y = by + bh / 2
                # Force icon to fit the button rect.
                self.info_sprite.width = bw
                self.info_sprite.height = bh
                self.info_sprite_list.draw()
            else:
                # Fallback if info.png is missing.
                arcade.draw_circle_filled(bx + bw / 2, by + bh / 2, min(bw, bh) / 2, arcade.color.DARK_BLUE)
                arcade.draw_text("i", bx + bw / 2, by + bh / 2,
                                 arcade.color.WHITE, 28, anchor_x="center", anchor_y="center")

            if self.wave_message:
                arcade.draw_text(self.wave_message,
                                 self.width / 2, self.height - 90,
                                 arcade.color.GOLD, 30,
                                 anchor_x="center")
                arcade.draw_text(f"Du bekommst {self.wave_reward_coins} Münzen",
                                 self.width / 2, self.height - 125,
                                 arcade.color.YELLOW, 22,
                                 anchor_x="center")

            # MiniMap (M toggeln)
            if self.show_minimap:
                minimap_w = MAP_WIDTH * MINIMAP_SCALE
                minimap_h = MAP_HEIGHT * MINIMAP_SCALE
                minimap_x = self.width - minimap_w - 20
                minimap_y = 20

                arcade.draw_lbwh_rectangle_filled(minimap_x, minimap_y,
                                                  minimap_w, minimap_h,
                                                  arcade.color.DARK_SLATE_GRAY)

                px = minimap_x + (self.player.center_x + MAP_WIDTH/2) * MINIMAP_SCALE
                py = minimap_y + (self.player.center_y + MAP_HEIGHT/2) * MINIMAP_SCALE
                arcade.draw_circle_filled(px, py, 5, arcade.color.BLUE)

                for enemy in self.enemies:
                    ex = minimap_x + (enemy.center_x + MAP_WIDTH/2) * MINIMAP_SCALE
                    ey = minimap_y + (enemy.center_y + MAP_HEIGHT/2) * MINIMAP_SCALE
                    arcade.draw_circle_filled(ex, ey, 4, arcade.color.RED)

                for spawner in self.spawners:
                    sx = minimap_x + (spawner.center_x + MAP_WIDTH/2) * MINIMAP_SCALE
                    sy = minimap_y + (spawner.center_y + MAP_HEIGHT/2) * MINIMAP_SCALE
                    arcade.draw_circle_filled(sx, sy, 5, arcade.color.YELLOW)

                if not self.wave_active:
                    px2 = minimap_x + (self.portal_x + MAP_WIDTH/2) * MINIMAP_SCALE
                    py2 = minimap_y + (self.portal_y + MAP_HEIGHT/2) * MINIMAP_SCALE
                    arcade.draw_circle_filled(px2, py2, 5, arcade.color.DARK_BLUE)

        elif self.state == "info":
            arcade.draw_lbwh_rectangle_filled(0, 0, self.width, self.height, (0, 0, 0, 200))
            arcade.draw_text("INFO",
                             self.width / 2, self.height - 140,
                             arcade.color.WHITE, 60,
                             anchor_x="center")
            arcade.draw_text("Bewegung: Pfeiltasten",
                             self.width / 2, self.height - 230,
                             arcade.color.WHITE, 28,
                             anchor_x="center")
            arcade.draw_text("Schießen: Leertaste",
                             self.width / 2, self.height - 280,
                             arcade.color.WHITE, 28,
                             anchor_x="center")
            arcade.draw_text("Shift: schneller (+8) und kostet Energie",
                             self.width / 2, self.height - 330,
                             arcade.color.WHITE, 26,
                             anchor_x="center")
            arcade.draw_text("Karte: M",
                             self.width / 2, self.height - 380,
                             arcade.color.WHITE, 26,
                             anchor_x="center")

            bx, by, bw, bh = self.ui_rects["info_back"]
            arcade.draw_lbwh_rectangle_filled(bx, by, bw, bh, arcade.color.GRAY)
            arcade.draw_text("Zurück",
                             self.width / 2, by + bh / 2,
                             arcade.color.WHITE, 30,
                             anchor_x="center", anchor_y="center")

        elif self.state == "shop":
            arcade.draw_lbwh_rectangle_filled(0, 0, self.width, self.height, arcade.color.DARK_BLUE_GRAY)
            arcade.draw_text("SHOP",
                             self.width / 2, self.height - 120,
                             arcade.color.GOLD, 54,
                             anchor_x="center")
            arcade.draw_text(f"🪙 Münzen: {self.total_coins}",
                             self.width / 2, self.height - 190,
                             arcade.color.WHITE, 28,
                             anchor_x="center")
            arcade.draw_text("Willkommen im Portal-Shop",
                             self.width / 2, self.height - 260,
                             arcade.color.WHITE, 26,
                             anchor_x="center")
            bx, by, bw, bh = self.get_shop_buy_one_button_rect()
            bx, by, bw, bh = self.ui_rects["shop_buy_one"]
            can_buy_one = self.total_coins >= AMMO_COST
            one_color = arcade.color.DARK_SPRING_GREEN if can_buy_one else arcade.color.RED
            arcade.draw_lbwh_rectangle_filled(bx, by, bw, bh, one_color)
            arcade.draw_text(self.shop_buy_one_label,
                             self.width / 2, by + bh / 2,
                             arcade.color.WHITE, 24,
                             anchor_x="center", anchor_y="center")

            bx, by, bw, bh = self.ui_rects["shop_leave"]
            arcade.draw_lbwh_rectangle_filled(bx, by, bw, bh, arcade.color.GRAY)
            arcade.draw_text(self.shop_leave_label,
                             self.width / 2, by + bh / 2,
                             arcade.color.WHITE, 26,
                             anchor_x="center", anchor_y="center")

        elif self.state == "gameover":

            arcade.draw_text("GAME OVER",
                             self.width//2, self.height//2,
                             arcade.color.RED, 50,
                             anchor_x="center")

# ---------------- START ----------------
if __name__ == "__main__":
    game = SurvivalGame()
    arcade.run()
