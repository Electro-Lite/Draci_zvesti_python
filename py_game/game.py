import threading
from pathlib import Path

import pygame

from py_game.menu.main_menu import MainMenu
from py_game.assets import AssetCache
from py_game.audio import AudioFeedback
from py_game.battle_presentation import local_battle_display_strategy
from py_game.settings import SettingsStore
from py_game.theme import MANA_COLORS, PALETTE
from py_game.training_service import TrainingService
from py_game.ui.layout import LayoutMetrics, RectSpec
from py_game.ui.widgets import DragController
from py_game.network.gameplay import (
    HostMatchChannel,
    RemoteChoiceStrategy,
    network_display_strategy,
    serialize_game_state,
)
from py_game.network.protocol import MessageType

from core.game_loop         import run as run_game
from choice_strategies.choice_strategy_human_pygame import (
    PASS_SELECTION,
    ChoiceType,
    PygameChoiceStrategy,
)
from py_game.match_setup import ControllerKind, ControllerSpec, create_player
from utils.database_utils import DBUtil
from core.board import Board
from core.player import Player

class Game():
    BATTLE_FRAME_SECONDS = 0.65 * 3
    BACKGROUND_OVERLAY_OPACITY = 255
    BACKGROUND_MANA_BASE_STRENGTH = 0.18
    MENU_BACKGROUND_PATH = (
        Path(__file__).resolve().parent
        / "resources"
        / "transparent_background.png"
    )
    MATCH_BACKGROUND_PATH = (
        Path(__file__).resolve().parent
        / "resources"
        / "mana_background.png"
    )

    def __init__(self):
        pygame.init()
        self.settings_store = SettingsStore()
        self.settings = self.settings_store.load()
        self.palette = PALETTE
        self.assets = AssetCache()
        self.audio = AudioFeedback(self.settings.master_volume)
        self.UP_KEY, self.DOWN_KEY, self.LEFT_KEY, self.RIGHT_KEY = False, False, False, False
        self.START_KEY, self.BACK_KEY = False, False
        self.PASS_KEY = False
        self.USE_ABILITY_KEY = False
        self.SKIP_ABILITY_KEY = False
        self.running, self.playing      = True, False
        self.DISPLAY_W, self.DISPLAY_H = self.settings.width, self.settings.height
        self.BLACK = self.palette.background
        self.WHITE = self.palette.text
        self.ORANGE = self.palette.accent
        self.DARK_GREY = self.palette.panel
        self.layout = LayoutMetrics.from_size(self.DISPLAY_W, self.DISPLAY_H)
        self.TEXT_SMALL = self.layout.font_small
        self.TEXT_NORMAL = self.layout.font_normal
        self.TEXT_LARGE = self.layout.font_large
        self.events = []
        self.mouse_position = (0, 0)
        self.mouse_clicked = False
        self.mouse_right_clicked = False
        self.mouse_released = False
        self.mouse_wheel = 0
        self.drag = DragController()
        self.hand_card_rects = []
        self.board_slot_rects = []
        self.action_rects = {}
        self.pending_drop_position = None
        self.interaction_message = ""
        self.inspected_card_view = None
        self._card_model_cache = {}
        self.training_service = TrainingService()
        self._quit_prompt_open = False
        self.battle_continue_event = threading.Event()

        self.p1_deck_id = None
        self.p2_deck_id = None
        self.p1_controller = ControllerSpec(ControllerKind.HUMAN)
        self.p2_controller = ControllerSpec(ControllerKind.RANDOM_AI)
        self.selected_card      = None
        self.selected_position  = None
        self.binary_choice = False
        self.previous_choice_type = None
        self.changing_player    = False
        self.changing_to_battle = False
        self.previous_game_state = None

        flags = pygame.FULLSCREEN if self.settings.fullscreen else pygame.RESIZABLE
        self.window = pygame.display.set_mode(
            (self.DISPLAY_W, self.DISPLAY_H),
            flags,
        )
        self.display = pygame.Surface((self.DISPLAY_W, self.DISPLAY_H))
        pygame.display.set_caption("Draci zvesti")
        self.font_name      = pygame.font.get_default_font()
        self.clock = pygame.time.Clock()
        self.logic_error = None
        self.game_result = None
    
        self.curr_menu      = MainMenu(self)

    def check_events(self):
        self.events = pygame.event.get()
        self.mouse_position = pygame.mouse.get_pos()
        self.mouse_clicked = False
        self.mouse_right_clicked = False
        self.mouse_released = False
        self.mouse_wheel = 0
        for event in self.events:
            if event.type == pygame.QUIT:
                if not self._quit_prompt_open:
                    self.request_quit()
            elif event.type == pygame.VIDEORESIZE and not self.settings.fullscreen:
                self.resize(event.w, event.h, persist=True)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.mouse_clicked = True
                self.mouse_position = event.pos
                self.audio.play_click()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                self.mouse_right_clicked = True
                self.mouse_position = event.pos
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.mouse_released = True
                self.mouse_position = event.pos
            elif event.type == pygame.MOUSEWHEEL:
                self.mouse_wheel += event.y
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.START_KEY      = True
                    self.audio.play_click()
                elif event.key == pygame.K_ESCAPE:
                    self.BACK_KEY       = True
                elif event.key == pygame.K_p:
                    self.PASS_KEY = True
                elif event.key in (pygame.K_a, pygame.K_y):
                    self.USE_ABILITY_KEY = True
                elif event.key in (pygame.K_s, pygame.K_n):
                    self.SKIP_ABILITY_KEY = True
                elif event.key == pygame.K_DOWN:
                    self.DOWN_KEY       = True
                elif event.key == pygame.K_UP:
                    self.UP_KEY         = True
                elif event.key == pygame.K_LEFT:
                    self.LEFT_KEY       = True
                elif event.key == pygame.K_RIGHT:
                    self.RIGHT_KEY      = True

    def request_quit(self):
        """Confirm and stop training owned by this UI before closing Pygame."""
        running_jobs = self.training_service.owned_running_jobs()
        if running_jobs:
            self._quit_prompt_open = True
            try:
                labels = ", ".join(job.job_id for job in running_jobs[:2])
                if len(running_jobs) > 2:
                    labels += f" and {len(running_jobs) - 2} more"
                menu = self.curr_menu
                confirmed = bool(
                    menu
                    and menu.confirm_action(
                        "Training is still running",
                        (
                            labels,
                            "Quitting will stop the UI-owned training process.",
                            "Saved generations and artifacts will remain available.",
                        ),
                        confirm_label="Stop and quit",
                    )
                )
            finally:
                self._quit_prompt_open = False
            if not confirmed:
                self.reset_keys()
                return False
            self.training_service.stop_owned_jobs()
        self.running, self.playing = False, False
        if self.curr_menu is not None:
            self.curr_menu.run_display = False
        return True

    def resize(self, width: int, height: int, *, persist: bool = False):
        metrics = LayoutMetrics.from_size(width, height)
        self.DISPLAY_W, self.DISPLAY_H = metrics.width, metrics.height
        self.layout = metrics
        self.TEXT_SMALL = metrics.font_small
        self.TEXT_NORMAL = metrics.font_normal
        self.TEXT_LARGE = metrics.font_large
        flags = pygame.FULLSCREEN if self.settings.fullscreen else pygame.RESIZABLE
        self.window = pygame.display.set_mode(
            (self.DISPLAY_W, self.DISPLAY_H),
            flags,
        )
        self.display = pygame.Surface((self.DISPLAY_W, self.DISPLAY_H))
        self.assets.clear_scaled()
        if persist:
            self.settings.width = self.DISPLAY_W
            self.settings.height = self.DISPLAY_H
            self.settings_store.save(self.settings)

    def apply_settings(self):
        self.settings.validate()
        self.resize(self.settings.width, self.settings.height)
        if pygame.mixer.get_init():
            volume = self.settings.master_volume / 100
            pygame.mixer.music.set_volume(volume)
            for index in range(pygame.mixer.get_num_channels()):
                pygame.mixer.Channel(index).set_volume(volume)
        self.audio.set_volume(self.settings.master_volume)
        self.settings_store.save(self.settings)

    def reset_keys(self):
        self.UP_KEY, self.DOWN_KEY    = False, False
        self.LEFT_KEY, self.RIGHT_KEY = False, False
        self.START_KEY, self.BACK_KEY = False, False
        self.PASS_KEY = False
        self.USE_ABILITY_KEY = False
        self.SKIP_ABILITY_KEY = False
        self.mouse_clicked = False
        self.mouse_right_clicked = False
        self.mouse_released = False
        self.mouse_wheel = 0

    @staticmethod
    def _mix_color(base, tint, strength):
        return tuple(
            round(base_channel + (tint_channel - base_channel) * strength)
            for base_channel, tint_channel in zip(base, tint)
        )

    def draw_background(self, active_mana=None, *, match=False):
        """Draw the shared color base and responsive decorative overlay."""
        mana_key = str(getattr(active_mana, "name", active_mana or "")).upper()
        mana_color = MANA_COLORS.get(mana_key)
        background = (
            self._mix_color(
                self.palette.background,
                mana_color,
                self.BACKGROUND_MANA_BASE_STRENGTH,
            )
            if mana_color
            else self.palette.background
        )
        self.display.fill(background)
        size = (self.DISPLAY_W, self.DISPLAY_H)
        background_path = (
            self.MATCH_BACKGROUND_PATH if match else self.MENU_BACKGROUND_PATH
        )
        overlay = (
            self.assets.tinted_cover(
                background_path,
                size,
                mana_color,
            )
            if mana_color
            else self.assets.cover(background_path, size)
        )
        overlay.set_alpha(self.BACKGROUND_OVERLAY_OPACITY)
        self.display.blit(overlay, (0, 0))

    def navigate_hand(self, player):
        cards = player.hand.cards
        if self.selected_card == None and len(cards)>0 :
            self.selected_card = cards[0]
        if self.LEFT_KEY:
            try:
                pos = cards.index(self.selected_card)
                pos = (pos - 1) if pos > 0 else len(cards) - 1
                self.selected_card = cards[pos]
            except ValueError:
                self.selected_card = cards[len(cards)-1] if len(cards)>0 else None
        elif self.RIGHT_KEY:
            try:
                pos = cards.index(self.selected_card)
                pos = (pos + 1) % len(cards)
                self.selected_card = cards[pos]
            except ValueError:
                self.selected_card = cards[0] if len(cards)>0 else None
    
    def navigate_board(self, allowed_positions=None):
        empty_positions = (
            list(allowed_positions)
            if allowed_positions is not None
            else [
                index
                for index, card in enumerate(self.board.positions)
                if card is None
            ]
        )
        if self.selected_position == None and len(empty_positions)>0 :
            self.selected_position = empty_positions[0]
        if self.LEFT_KEY:
            try:
                pos_index = empty_positions.index(self.selected_position)
                self.selected_position  = empty_positions[pos_index - 1] if pos_index > 0 else empty_positions[len(empty_positions) - 1]
            except ValueError:
                self.selected_position = empty_positions[len(empty_positions)-1] if len(empty_positions)>0 else None
        elif self.RIGHT_KEY:
            try:
                pos_index = (empty_positions.index(self.selected_position) + 1) % len(empty_positions)
                self.selected_position = empty_positions[pos_index]
            except ValueError:
                self.selected_position = empty_positions[0] if len(empty_positions)>0 else None

    def handle_choice(self):
        player = self.board.player_on_turn
        if player is None or not isinstance(
            player.choice_strategy,
            PygameChoiceStrategy,
        ):
            self.selected_card = None
            self.selected_position = None
            return

        strategy = player.choice_strategy
        choice_type = strategy.waiting_for
        self._sync_choice_defaults(choice_type)
        if choice_type in (ChoiceType.CARD, ChoiceType.PLAY_OR_PASS):
            self.navigate_hand(player)
            self.selected_position = None
            if choice_type == ChoiceType.PLAY_OR_PASS and self.PASS_KEY:
                strategy.set_choice(ChoiceType.PLAY_OR_PASS, PASS_SELECTION)
            elif self.START_KEY and self.selected_card is not None:
                strategy.set_choice(choice_type, self.selected_card)
        elif choice_type == ChoiceType.POSITION:
            self.selected_card = None
            self.navigate_board()
            if self.START_KEY and self.selected_position is not None:
                strategy.set_choice(ChoiceType.POSITION, self.selected_position)
        elif choice_type == ChoiceType.PASS:
            self.selected_card = None
            self.selected_position = None
            if self.LEFT_KEY or self.RIGHT_KEY:
                self.binary_choice = not self.binary_choice
            if self.PASS_KEY:
                strategy.set_choice(ChoiceType.PASS, True)
            elif self.START_KEY:
                strategy.set_choice(ChoiceType.PASS, self.binary_choice)
        elif choice_type == ChoiceType.USE_ABILITY:
            self.selected_card = None
            self.selected_position = None
            if self.LEFT_KEY or self.RIGHT_KEY:
                self.binary_choice = not self.binary_choice
            if self.USE_ABILITY_KEY:
                strategy.set_choice(ChoiceType.USE_ABILITY, True)
            elif self.SKIP_ABILITY_KEY:
                strategy.set_choice(ChoiceType.USE_ABILITY, False)
            elif self.START_KEY:
                strategy.set_choice(ChoiceType.USE_ABILITY, self.binary_choice)
        elif choice_type == ChoiceType.TARGET:
            self.selected_card = None
            legal_targets = strategy.legal_targets()
            self.navigate_board(legal_targets)
            if self.START_KEY and self.selected_position in legal_targets:
                strategy.set_choice(ChoiceType.TARGET, self.selected_position)
        else:
            self.selected_card = None
            self.selected_position = None

    def _sync_choice_defaults(self, choice_type):
        """Set an intuitive default whenever a new interaction prompt opens."""
        key = getattr(choice_type, "name", str(choice_type or "")).lower()
        if key == self.previous_choice_type:
            return
        self.previous_choice_type = key
        if key == "use_ability":
            self.binary_choice = True
        elif key == "pass":
            self.binary_choice = False



            
             
    def _card_image_path(self, card_view):
        card_id = str((card_view or {}).get("id", ""))
        if not card_id:
            return None
        if card_id not in self._card_model_cache:
            try:
                self._card_model_cache[card_id] = DBUtil().load_card(card_id)
            except (RuntimeError, ValueError):
                self._card_model_cache[card_id] = None
        card = self._card_model_cache[card_id]
        return getattr(card, "image", None) if card else None

    def _draw_card_stat_circle(self, center, value, radius):
        pygame.draw.circle(self.display, (249, 246, 237), center, radius)
        pygame.draw.circle(self.display, (48, 48, 55), center, radius, max(1, radius // 6))
        label = str(max(0, int(value)))
        font_size = max(9, round(radius * 1.5))
        font = pygame.font.Font(self.font_name, font_size)
        rendered = font.render(label, True, (24, 27, 32))
        while rendered.get_width() > radius * 2 - 2 and font_size > 8:
            font_size -= 1
            font = pygame.font.Font(self.font_name, font_size)
            rendered = font.render(label, True, (24, 27, 32))
        self.display.blit(rendered, rendered.get_rect(center=center))

    def _draw_card_stats_on_art(self, card_view, rect):
        """Cover the printed ATK/HP numerals without covering the card text/art."""
        radius = max(7, min(round(rect.width * 0.076), round(rect.height * 0.064)))
        top = rect.y + max(radius + 1, round(rect.height * 0.060))
        inset = max(radius + 1, round(rect.width * 0.098))
        self._draw_card_stat_circle((rect.x + inset, top), card_view.get("dmg", 0), radius)
        self._draw_card_stat_circle((rect.right - inset, top), card_view.get("hp", 0), radius)

    def _draw_active_mana_marker(self, card_view, rect, active_mana):
        bonus = card_view.get("mana_bonus") or {}
        if (
            not active_mana
            or card_view.get("color") != active_mana
            or not (bonus.get("dmg", 0) or bonus.get("hp", 0))
        ):
            return
        color = MANA_COLORS.get(active_mana)
        if color is None:
            return
        radius = max(5, min(10, rect.width // 15))
        center = (rect.centerx, rect.y + radius + 3)
        pygame.draw.circle(self.display, self.palette.text, center, radius + 2)
        pygame.draw.circle(self.display, color, center, radius)
        self.draw_text("+", max(10, radius * 2), center[0], center[1], self.palette.text)

    def _draw_owner_marker(self, rect, player_id):
        radius = max(6, min(9, rect.width // 14))
        center = (rect.centerx, rect.bottom + radius + 2)
        pygame.draw.circle(self.display, self.palette.background, center, radius + 2)
        pygame.draw.circle(self.display, self.palette.accent, center, radius)
        self.draw_text(str(player_id), max(9, radius + 3), center[0], center[1], self.palette.background)

    @staticmethod
    def _marked_board_owner(state, mark_current_player):
        local = state.get("local") or {}
        opponent = state.get("opponent") or {}
        if mark_current_player:
            if state.get("game_state") == "BATTLE":
                return None, None
            side = state.get("turn")
            player = local if side == "local" else opponent if side == "opponent" else {}
            return side, player.get("id")
        if local.get("id") == 1:
            return "local", 1
        if opponent.get("id") == 1:
            return "opponent", 1
        return None, None

    def _draw_card_view(self, card_view, rect, *, selected=False, legal=False, hidden=False, active_mana=None):
        border = self.palette.accent if selected else self.palette.success if legal else self.palette.border
        pygame.draw.rect(self.display, self.palette.panel_alt, rect, border_radius=6)
        pygame.draw.rect(self.display, border, rect, 3 if (selected or legal) else 1, border_radius=6)
        if hidden:
            image = self.assets.image(
                Path(__file__).resolve().parent / "resources" / "card_background.png",
                rect.size,
            )
            self.display.blit(image, rect)
            pygame.draw.rect(self.display, border, rect, 2, border_radius=6)
            return
        if not card_view:
            return
        image_path = self._card_image_path(card_view)
        image = self.assets.image(image_path, rect.size)
        self.display.blit(image, rect)
        if not image_path:
            self.draw_text_left(
                card_view.get("name", card_view.get("id", "Card")),
                max(10, min(self.TEXT_SMALL, rect.width // 7)),
                rect.x + 4,
                rect.centery,
                max_width=rect.width - 8,
            )
        self._draw_card_stats_on_art(card_view, rect)
        self._draw_active_mana_marker(card_view, rect, active_mana)
        pygame.draw.rect(self.display, border, rect, 3 if (selected or legal) else 1, border_radius=6)

    def _choice_prompt(self, choice_type):
        return {
            "pass": "Play a card or pass for this round",
            "play_or_pass": "Choose a card to play, or pass the round",
            "card": "Choose a card from your hand",
            "position": "Choose an open board position",
            "use_ability": "Use this card's active ability?",
            "target": "Choose a legal ability target",
        }.get(choice_type, "Waiting for the other player")

    def _draw_card_tooltip(self, card_view, anchor):
        if not card_view or not self.settings.show_tooltips:
            return
        metrics = self.layout
        panel_width = min(max(390, self.DISPLAY_W * 3 // 5), self.DISPLAY_W - metrics.margin * 2)
        panel_height = min(max(300, self.DISPLAY_H * 3 // 5), self.DISPLAY_H - metrics.margin * 4)
        image_height = panel_height - metrics.margin * 2
        image_width = min(panel_width // 2, round(image_height * 5 / 7))
        x = metrics.margin if anchor[0] > self.DISPLAY_W // 2 else self.DISPLAY_W - metrics.margin - panel_width
        y = max(metrics.margin, (self.DISPLAY_H - panel_height) // 2)
        rect = pygame.Rect(x, y, panel_width, panel_height)
        shade = pygame.Surface(rect.size, pygame.SRCALPHA)
        shade.fill((*self.palette.panel[:3], 247))
        self.display.blit(shade, rect)
        pygame.draw.rect(self.display, self.palette.accent, rect, 3, border_radius=12)

        image_rect = pygame.Rect(
            rect.x + metrics.margin,
            rect.y + metrics.margin,
            image_width,
            image_height,
        )
        image = self.assets.image(self._card_image_path(card_view), image_rect.size)
        self.display.blit(image, image_rect)
        self._draw_card_stats_on_art(card_view, image_rect)
        pygame.draw.rect(self.display, self.palette.border, image_rect, 2, border_radius=8)

        text_x = image_rect.right + metrics.margin
        text_width = rect.right - metrics.margin - text_x
        name = str(card_view.get("name", card_view.get("id", "Card")))
        self.draw_text_left(name, metrics.font_normal, text_x, rect.y + metrics.margin + metrics.font_normal // 2, self.palette.accent, text_width)
        self.draw_text_left(
            f"ATK {card_view.get('dmg', 0)}  •  HP {card_view.get('hp', 0)}",
            metrics.font_small,
            text_x,
            rect.y + metrics.margin + metrics.font_normal + metrics.gap,
            self.palette.text,
            text_width,
        )
        ability_name = str(card_view.get("ability_name", "")).strip()
        ability_description = str(card_view.get("ability_description", "")).strip()
        text_y = rect.y + metrics.margin + metrics.font_normal + metrics.font_small + metrics.gap * 3
        if ability_name:
            self.draw_text_left(
                ability_name,
                metrics.font_small,
                text_x,
                text_y,
                self.palette.success,
                text_width,
            )
            text_y += metrics.font_small + metrics.gap
        if ability_description:
            self._draw_wrapped_card_text(
                ability_description,
                metrics.font_small,
                text_x,
                text_y,
                text_width,
                max_lines=max(3, (rect.bottom - metrics.margin - text_y) // max(1, metrics.font_small)),
            )
        self.draw_text_left(
            "Right-click elsewhere to close",
            max(10, metrics.font_small - 2),
            text_x,
            rect.bottom - metrics.margin,
            self.palette.muted,
            text_width,
        )

    def _draw_wrapped_card_text(self, text, size, x, y, max_width, max_lines=8):
        font = pygame.font.Font(self.font_name, int(size))
        words = str(text).split()
        lines = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and font.size(candidate)[0] > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        for index, line in enumerate(lines[:max_lines]):
            self.draw_text_left(line, size, x, y + index * font.get_linesize(), self.palette.text, max_width)

    def draw_match_state(
        self,
        state,
        choice_type=None,
        *,
        notice="",
        return_destination="menu",
        battle_continue_owner="local",
        mark_current_player=False,
    ):
        """Draw local or LAN state using one responsive board layout."""
        metrics = self.layout
        self._sync_choice_defaults(choice_type)
        self.draw_background(state.get("mana"), match=True)
        self.hand_card_rects = []
        self.board_slot_rects = []
        self.action_rects = {}

        header_h = metrics.target_height + metrics.gap
        header = pygame.Rect(0, 0, self.DISPLAY_W, header_h)
        pygame.draw.rect(self.display, self.palette.panel, header)
        score = f"You {state.get('local', {}).get('score', 0)}  —  {state.get('opponent', {}).get('score', 0)} Rival"
        self.draw_text_left(score, metrics.font_normal, metrics.margin, header.centery)
        battle_event = state.get("battle") or {}
        prompt = (
            "Dragon battle • "
            + str(battle_event.get("phase", "battle")).replace("_", " ").title()
            if state.get("game_state") == "BATTLE"
            else self.interaction_message or self._choice_prompt(choice_type)
        )
        self.draw_text(
            prompt,
            metrics.font_normal,
            self.DISPLAY_W // 2,
            header.centery,
            self.palette.danger
            if self.interaction_message
            else self.palette.accent
            if choice_type
            else self.palette.text,
        )
        status = f"Round {state.get('round', 0)}  •  Mana {state.get('mana') or '—'}"
        font = pygame.font.Font(self.font_name, metrics.font_small)
        status_surface = font.render(status, True, self.palette.muted)
        self.display.blit(status_surface, status_surface.get_rect(midright=(self.DISPLAY_W - metrics.margin, header.centery)))

        footer_h = metrics.target_height + metrics.gap
        body = pygame.Rect(
            metrics.margin,
            header.bottom + metrics.gap,
            self.DISPLAY_W - metrics.margin * 2,
            self.DISPLAY_H - header_h - footer_h - metrics.gap * 2,
        )
        zone_gap = metrics.gap
        usable_zone_height = body.height - zone_gap * 2
        if state.get("game_state") == "BATTLE":
            opponent_height = max(1, round(usable_zone_height * 0.28))
            board_height = max(1, round(usable_zone_height * 0.48))
            hand_height = max(1, usable_zone_height - opponent_height - board_height)
        else:
            opponent_height = max(1, usable_zone_height // 3)
            board_height = opponent_height
            hand_height = max(1, usable_zone_height - opponent_height - board_height)
        opponent_zone = pygame.Rect(body.x, body.y, body.width, opponent_height)
        board_zone = pygame.Rect(
            body.x,
            opponent_zone.bottom + zone_gap,
            body.width,
            board_height,
        )
        hand_zone = pygame.Rect(
            body.x,
            board_zone.bottom + zone_gap,
            body.width,
            hand_height,
        )

        self.draw_text_left(
            f"Rival hand: {state.get('opponent', {}).get('hand_count', 0)}  •  deck: {state.get('opponent', {}).get('deck_count', 0)}",
            metrics.font_small,
            opponent_zone.x,
            opponent_zone.y + metrics.font_small // 2,
            self.palette.muted,
        )
        opponent_cards = min(12, int(state.get("opponent", {}).get("hand_count", 0)))
        opponent_card_area = pygame.Rect(
            opponent_zone.x,
            opponent_zone.y + metrics.font_small + 3,
            opponent_zone.width,
            max(1, opponent_zone.height - metrics.font_small - 3),
        )
        if opponent_cards:
            card_w, card_h, gap = metrics.card_size(
                RectSpec(opponent_card_area.x, opponent_card_area.y, opponent_card_area.width, opponent_card_area.height),
                opponent_cards,
                minimum_width=22,
            )
            total_w = card_w * opponent_cards + gap * (opponent_cards - 1)
            start_x = opponent_card_area.centerx - total_w // 2
            for index in range(opponent_cards):
                rect = pygame.Rect(start_x + index * (card_w + gap), opponent_card_area.y, card_w, card_h)
                self._draw_card_view(None, rect, hidden=True)

        self.draw_text_left(
            f"Board  •  dragon deck: {state.get('dragon_deck_count', 0)}  •  Right-click card details",
            metrics.font_small,
            board_zone.x,
            board_zone.y + metrics.font_small // 2,
            self.palette.muted,
        )
        marker_band = max(15, metrics.gap + 3)
        board_area = RectSpec(
            board_zone.x,
            board_zone.y + metrics.font_small + 3,
            board_zone.width,
            max(1, board_zone.height - metrics.font_small - 3 - marker_band),
        )
        card_w, card_h, gap = metrics.card_size(board_area, 6, minimum_width=32)
        total_w = card_w * 6 + gap * 5
        start_x = board_area.x + (board_area.width - total_w) // 2
        legal_indices = set()
        if choice_type in ("position", "target"):
            legal_indices = set(getattr(self, "current_legal_indices", []))
        marked_side, marked_player_id = self._marked_board_owner(state, mark_current_player)
        hovered_card = None
        for index, card in enumerate((state.get("board") or [None] * 6)[:6]):
            rect = pygame.Rect(start_x + index * (card_w + gap), board_area.y, card_w, card_h)
            self.board_slot_rects.append(rect)
            drag_legal = (
                self.drag.start is not None
                and f"slot:{index}" in self.drag.valid_targets
            )
            self._draw_card_view(
                card,
                rect,
                selected=self.selected_position == index,
                legal=index in legal_indices or drag_legal,
                active_mana=state.get("mana"),
            )
            if card and card.get("owner") == marked_side and marked_player_id is not None:
                self._draw_owner_marker(rect, marked_player_id)
            active_battle_slot = (
                state.get("game_state") == "BATTLE"
                and battle_event.get("slot") == index
            )
            if active_battle_slot:
                battle_border = (
                    self.palette.danger
                    if battle_event.get("phase") in ("impact", "card_defeated", "stalemate")
                    else self.palette.accent
                )
                pygame.draw.rect(
                    self.display,
                    battle_border,
                    rect,
                    4,
                    border_radius=7,
                )
            if card and rect.collidepoint(self.mouse_position):
                hovered_card = card
            self.draw_text(str(index + 1), max(10, metrics.font_small - 2), rect.centerx, rect.y + 8, self.palette.muted)

        if state.get("game_state") == "BATTLE" and state.get("dragon"):
            self._draw_dragon_board_path(state)

        local = state.get("local", {})
        self.draw_text_left(
            f"Your hand  •  deck: {local.get('deck_count', 0)}  •  graveyard: {local.get('graveyard_count', 0)}  •  Right-click card details",
            metrics.font_small,
            hand_zone.x,
            hand_zone.y + metrics.font_small // 2,
            self.palette.muted,
        )
        hand = local.get("hand") or []
        hand_area = RectSpec(
            hand_zone.x,
            hand_zone.y + metrics.font_small + 3,
            hand_zone.width,
            max(1, hand_zone.height - metrics.font_small - 3),
        )
        if hand:
            card_w, card_h, gap = metrics.card_size(hand_area, len(hand), minimum_width=30)
            total_w = card_w * len(hand) + gap * (len(hand) - 1)
            start_x = hand_area.x + (hand_area.width - total_w) // 2
            for index, card in enumerate(hand):
                rect = pygame.Rect(start_x + index * (card_w + gap), hand_area.y, card_w, card_h)
                self.hand_card_rects.append(rect)
                selected = getattr(self, "selected_card_index", None) == index
                self._draw_card_view(
                    card,
                    rect,
                    selected=selected,
                    legal=choice_type in ("card", "play_or_pass"),
                )
                if rect.collidepoint(self.mouse_position):
                    hovered_card = card

        footer = pygame.Rect(0, self.DISPLAY_H - footer_h, self.DISPLAY_W, footer_h)
        pygame.draw.rect(self.display, self.palette.panel, footer)
        action_labels = []
        if choice_type == "pass":
            action_labels = [("play", "Play card · Enter"), ("pass", "Pass round · P")]
        elif choice_type == "play_or_pass":
            action_labels = [
                ("confirm_card", "Play selected · Enter"),
                ("pass", "Pass round · P"),
            ]
        elif choice_type == "card":
            action_labels = [("confirm_card", "Play selected · Enter")]
        elif choice_type == "use_ability":
            action_labels = [("skip_ability", "Skip · S"), ("use_ability", "Use ability · Enter / A")]
        if action_labels:
            button_w = min(250, (self.DISPLAY_W - metrics.margin * 2) // len(action_labels) - metrics.gap)
            total = button_w * len(action_labels) + metrics.gap * (len(action_labels) - 1)
            x = (self.DISPLAY_W - total) // 2
            for key, label in action_labels:
                rect = pygame.Rect(x, footer.y + metrics.gap // 2, button_w, metrics.target_height)
                self.action_rects[key] = rect
                hovered = rect.collidepoint(self.mouse_position)
                selected_action = (
                    choice_type == "use_ability"
                    and (
                        (key == "use_ability" and self.binary_choice)
                        or (key == "skip_ability" and not self.binary_choice)
                    )
                )
                pygame.draw.rect(
                    self.display,
                    self.palette.selected
                    if selected_action
                    else self.palette.hover
                    if hovered
                    else self.palette.panel_alt,
                    rect,
                    border_radius=8,
                )
                pygame.draw.rect(self.display, self.palette.border, rect, 2, border_radius=8)
                self.draw_text(label, metrics.font_small, rect.centerx, rect.centery)
                x += button_w + metrics.gap
        else:
            keyboard_hint = {
                "position": "Left / Right choose an open slot  •  Enter places the card",
                "target": "Left / Right choose a target  •  Enter confirms",
            }.get(choice_type)
            self.draw_text(
                "Battle resolving step by step • watch the board values"
                if state.get("game_state") == "BATTLE"
                else keyboard_hint or notice or "Waiting for the other player",
                metrics.font_small,
                footer.centerx,
                footer.centery,
                self.palette.muted,
            )

        if state.get("game_state") == "BATTLE" and battle_event.get("phase") in (
            "dragon_defeated",
            "dragon_survived",
        ):
            pygame.draw.rect(self.display, self.palette.panel, footer)
            self.draw_text(
                "Enter / Space to continue"
                if battle_continue_owner == "local"
                else "Waiting for the host to continue",
                metrics.font_normal,
                footer.centerx,
                footer.centery,
                self.palette.accent,
            )

        if self.drag.dragging and self.drag.position is not None:
            pygame.draw.circle(self.display, self.palette.accent, self.drag.position, max(8, metrics.gap), 3)

        if state.get("winner") is not None or state.get("status") == "finished":
            overlay = pygame.Surface((self.DISPLAY_W, self.DISPLAY_H), pygame.SRCALPHA)
            overlay.fill((5, 8, 12, 210))
            self.display.blit(overlay, (0, 0))
            winner = state.get("winner")
            title = "Victory" if winner == "local" else "Defeat" if winner == "opponent" else "Draw"
            self.draw_text(title, metrics.font_large, self.DISPLAY_W // 2, self.DISPLAY_H // 2 - metrics.gap, self.palette.accent)
            self.draw_text(
                f"Press Enter or click to return to the {return_destination}",
                metrics.font_normal,
                self.DISPLAY_W // 2,
                self.DISPLAY_H // 2 + metrics.font_large,
            )
        elif state.get("game_state") == "BATTLE" and state.get("dragon"):
            self._draw_battle_presentation(state, opponent_zone)
        else:
            if self.mouse_right_clicked:
                self.inspected_card_view = hovered_card
            if self.inspected_card_view is not None:
                self._draw_card_tooltip(self.inspected_card_view, self.mouse_position)

    def _draw_dragon_board_path(self, state):
        """Place the dragon on its current board slot so combat reads spatially."""
        if not self.board_slot_rects:
            return
        event = state.get("battle") or {}
        slot = event.get("slot")
        if not isinstance(slot, int) or not 0 <= slot < len(self.board_slot_rects):
            slot = -1
        first = self.board_slot_rects[0]
        track_y = first.y + max(16, first.height // 7)
        entrance = (max(self.layout.margin, first.x - max(18, first.width // 4)), track_y)
        points = [entrance] + [
            (rect.centerx, track_y)
            for rect in self.board_slot_rects[: max(0, slot + 1)]
        ]
        if len(points) > 1:
            pygame.draw.lines(self.display, self.palette.danger, False, points, 3)
            for point in points[:-1]:
                pygame.draw.circle(self.display, self.palette.panel, point, 4)
                pygame.draw.circle(self.display, self.palette.danger, point, 4, 1)
        center = points[-1]
        radius = max(14, min(25, first.width // 5))
        pygame.draw.circle(self.display, self.palette.panel, center, radius + 4)
        pygame.draw.circle(self.display, self.palette.danger, center, radius)
        pygame.draw.circle(self.display, self.palette.text, center, radius, 2)
        self.draw_text("DRG", max(9, self.layout.font_small - 3), center[0], center[1], self.palette.text)
        if slot >= 0:
            self.draw_text(
                f"→ {slot + 1}",
                max(9, self.layout.font_small - 3),
                center[0],
                center[1] + radius + max(8, self.layout.gap // 2),
                self.palette.danger,
            )

    def _draw_battle_health(self, rect, card, color):
        hp = int((card or {}).get("hp", 0))
        maximum = max(1, int((card or {}).get("max_hp", max(1, hp))))
        ratio = max(0.0, min(1.0, hp / maximum))
        pygame.draw.rect(self.display, self.palette.disabled, rect, border_radius=6)
        if ratio:
            fill = rect.copy()
            fill.width = max(2, round(rect.width * ratio))
            pygame.draw.rect(self.display, color, fill, border_radius=6)
        pygame.draw.rect(self.display, self.palette.border, rect, 1, border_radius=6)
        self.draw_text(
            f"HP {max(0, hp)} / {maximum}",
            max(11, self.layout.font_small - 2),
            rect.centerx,
            rect.centery,
        )

    def _draw_battle_presentation(self, state, opponent_zone):
        """Render a compact combat HUD while keeping the whole board visible."""
        metrics = self.layout
        panel = opponent_zone.copy()
        pygame.draw.rect(self.display, self.palette.panel, panel, border_radius=18)
        pygame.draw.rect(self.display, self.palette.accent, panel, 2, border_radius=18)

        event = state.get("battle") or {}
        phase = str(event.get("phase", "reveal"))
        titles = {
            "reveal": "DRAGON AWAKENS",
            "dragon_ability": "DRAGON POWER",
            "versus": "CHALLENGER ENTERS",
            "impact": "CLASH",
            "stalemate": "DRAGON ADVANCES",
            "card_defeated": "CARD ELIMINATED",
            "dragon_defeated": "DRAGON DEFEATED",
            "dragon_survived": "DRAGON SURVIVES",
        }
        title_color = (
            self.palette.success
            if phase == "dragon_defeated"
            else self.palette.danger
            if phase in ("impact", "card_defeated", "dragon_survived")
            else self.palette.accent
        )
        dragon = state.get("dragon") or {}
        challenger = event.get("card")
        card_h = max(1, panel.height - metrics.gap * 2)
        card_w = max(1, round(card_h * 5 / 7))
        card_y = panel.y + metrics.gap
        dragon_rect = pygame.Rect(
            panel.x + metrics.gap,
            card_y,
            card_w,
            card_h,
        )
        challenger_rect = pygame.Rect(
            panel.right - metrics.gap - card_w,
            card_y,
            card_w,
            card_h,
        )
        self._draw_card_view(dragon, dragon_rect, selected=True)
        if challenger:
            self._draw_card_view(challenger, challenger_rect, selected=True, active_mana=state.get("mana"))
        else:
            pygame.draw.rect(
                self.display,
                self.palette.board_slot,
                challenger_rect,
                border_radius=10,
            )
            pygame.draw.rect(
                self.display,
                self.palette.border,
                challenger_rect,
                2,
                border_radius=10,
            )
            self.draw_text(
                "Waiting",
                max(10, metrics.font_small - 2),
                challenger_rect.centerx,
                challenger_rect.centery,
                self.palette.muted,
            )

        center_left = dragon_rect.right + metrics.gap
        center_right = challenger_rect.x - metrics.gap
        center_width = max(1, center_right - center_left)
        self.draw_text(
            titles.get(phase, "DRAGON BATTLE"),
            metrics.font_normal,
            center_left + center_width // 2,
            panel.y + metrics.gap + metrics.font_normal // 2,
            title_color,
        )
        point_for = event.get("point_for")
        if phase == "dragon_defeated" and point_for in ("local", "opponent"):
            award_text = "POINT FOR YOU" if point_for == "local" else "POINT FOR RIVAL"
            award_color = self.palette.success if point_for == "local" else self.palette.danger
            award = pygame.Rect(
                center_left + metrics.gap,
                panel.y + metrics.gap + metrics.font_normal,
                max(1, center_width - metrics.gap * 2),
                max(22, metrics.target_height // 2),
            )
            pygame.draw.rect(self.display, award_color, award, border_radius=7)
            self.draw_text(award_text, max(10, metrics.font_small - 1), award.centerx, award.centery, self.palette.background)
        if not point_for:
            message = str(event.get("message") or "The battle is unfolding")
            self.draw_text(
                message,
                max(11, metrics.font_small - 1),
                center_left + center_width // 2,
                panel.y + metrics.gap + metrics.font_normal + metrics.font_small,
                self.palette.text,
            )

        bar_width = max(1, center_width - metrics.gap * 2)
        bar_height = max(14, metrics.target_height // 3)
        first_bar_y = panel.bottom - metrics.gap * 2 - bar_height * 2
        self._draw_battle_health(
            pygame.Rect(center_left + metrics.gap, first_bar_y, bar_width, bar_height),
            dragon,
            self.palette.danger,
        )
        if challenger:
            self._draw_battle_health(
                pygame.Rect(
                    center_left + metrics.gap,
                    first_bar_y + bar_height + metrics.gap,
                    bar_width,
                    bar_height,
                ),
                challenger,
                self.palette.success,
            )

    def _local_choice_type(self):
        player = getattr(self, "board", None) and self.board.player_on_turn
        if not player or not isinstance(player.choice_strategy, PygameChoiceStrategy):
            return None
        mapping = {
            ChoiceType.PASS: "pass",
            ChoiceType.CARD: "card",
            ChoiceType.POSITION: "position",
            ChoiceType.USE_ABILITY: "use_ability",
            ChoiceType.TARGET: "target",
            ChoiceType.PLAY_OR_PASS: "play_or_pass",
        }
        return mapping.get(player.choice_strategy.waiting_for)

    def draw_responsive_game(self):
        state = serialize_game_state(self.board, self.p1, self.p2)
        choice_type = self._local_choice_type()
        strategy = getattr(getattr(self.board, "player_on_turn", None), "choice_strategy", None)
        self.current_legal_indices = (
            strategy.legal_targets()
            if choice_type == "target" and isinstance(strategy, PygameChoiceStrategy)
            else [index for index, card in enumerate(self.board.positions) if card is None]
            if choice_type == "position"
            else []
        )
        if self.selected_card is not None:
            try:
                self.selected_card_index = self.p1.hand.cards.index(self.selected_card)
            except ValueError:
                self.selected_card_index = None
        else:
            self.selected_card_index = None
        hotseat = (
            getattr(getattr(self, "p1_controller", None), "kind", None) == ControllerKind.HUMAN
            and getattr(getattr(self, "p2_controller", None), "kind", None) == ControllerKind.HUMAN
        )
        self.draw_match_state(
            state,
            choice_type,
            notice="Escape opens leave confirmation",
            mark_current_player=hotseat,
        )

    def _clear_hotseat_private_state(self):
        """Discard interaction state that could reveal or act on the next hand."""
        self.selected_card = None
        self.selected_card_index = None
        self.selected_position = None
        self.pending_drop_position = None
        self.binary_choice = False
        self.previous_choice_type = None
        self.interaction_message = ""
        self.inspected_card_view = None
        self.hand_card_rects = []
        self.board_slot_rects = []
        self.action_rects = {}
        self.current_legal_indices = []
        self.drag.cancel()

    def _hotseat_ready_rect(self):
        metrics = self.layout
        width = min(420, self.DISPLAY_W - metrics.margin * 4)
        return pygame.Rect(
            (self.DISPLAY_W - width) // 2,
            min(
                self.DISPLAY_H - metrics.margin - metrics.target_height,
                self.DISPLAY_H * 2 // 3,
            ),
            width,
            metrics.target_height,
        )

    def _hotseat_handoff_confirmed(self):
        return bool(
            self.START_KEY
            or (
                self.mouse_clicked
                and self._hotseat_ready_rect().collidepoint(self.mouse_position)
            )
        )

    def draw_hotseat_handoff(self, player_id):
        """Draw an opaque privacy screen without serializing either player's hand."""
        metrics = self.layout
        self.draw_background()
        self.hand_card_rects = []
        self.board_slot_rects = []
        self.action_rects = {}

        panel_spec = metrics.centered_panel(0.78, 0.68)
        panel = pygame.Rect(
            panel_spec.x,
            panel_spec.y,
            panel_spec.width,
            panel_spec.height,
        )
        pygame.draw.rect(self.display, self.palette.panel, panel, border_radius=14)
        pygame.draw.rect(
            self.display, self.palette.accent, panel, 3, border_radius=14
        )

        lock_center = (
            panel.centerx,
            panel.y + max(metrics.margin * 2, panel.height // 5),
        )
        lock_size = max(18, min(38, panel.height // 12))
        shackle = pygame.Rect(
            lock_center[0] - lock_size // 2,
            lock_center[1] - lock_size,
            lock_size,
            lock_size,
        )
        pygame.draw.arc(
            self.display,
            self.palette.accent,
            shackle,
            0,
            3.14159,
            max(3, lock_size // 7),
        )
        body = pygame.Rect(
            lock_center[0] - lock_size * 3 // 4,
            lock_center[1] - lock_size // 3,
            lock_size * 3 // 2,
            lock_size,
        )
        pygame.draw.rect(
            self.display, self.palette.accent, body, border_radius=6
        )

        title_y = lock_center[1] + lock_size + metrics.gap
        self.draw_text(
            "Pass the device",
            metrics.font_large,
            panel.centerx,
            title_y,
            self.palette.text,
        )
        self.draw_text(
            f"Player {player_id}'s turn",
            metrics.font_normal,
            panel.centerx,
            title_y + metrics.font_large,
            self.palette.accent,
        )
        self.draw_text(
            "The board and both hands are hidden during the handoff.",
            metrics.font_small,
            panel.centerx,
            title_y + metrics.font_large + metrics.font_normal * 2,
            self.palette.muted,
        )

        ready = self._hotseat_ready_rect()
        hovered = ready.collidepoint(self.mouse_position)
        pygame.draw.rect(
            self.display,
            self.palette.hover if hovered else self.palette.selected,
            ready,
            border_radius=9,
        )
        pygame.draw.rect(
            self.display, self.palette.border, ready, 2, border_radius=9
        )
        self.draw_text(
            "I have the device · Enter",
            metrics.font_normal,
            ready.centerx,
            ready.centery,
        )
        self.draw_text(
            "Escape opens the leave-match confirmation",
            max(9, metrics.font_small - 2),
            panel.centerx,
            panel.bottom - metrics.margin,
            self.palette.muted,
        )

    def _draw_local_match_frame(self):
        if self.logic_error:
            self.draw_background()
            self.draw_notice_overlay(
                "Match could not continue",
                f"{self.logic_error}  •  Enter or click to return",
            )
        elif self.changing_player:
            self.draw_hotseat_handoff(self.p1.id)
        else:
            self.draw_responsive_game()

    def _handle_local_mouse_choice(self):
        player = getattr(self, "board", None) and self.board.player_on_turn
        if not player or not isinstance(player.choice_strategy, PygameChoiceStrategy):
            return
        strategy = player.choice_strategy
        choice_type = self._local_choice_type()
        if choice_type == "position" and self.pending_drop_position is not None:
            position = self.pending_drop_position
            # The renderer's legal-index cache can be one frame behind the
            # logic thread. The board itself is authoritative for placement.
            if 0 <= position < len(self.board.positions) and self.board.positions[position] is None:
                if strategy.set_choice(ChoiceType.POSITION, position):
                    self.pending_drop_position = None
                    self.interaction_message = "Card placed"
                return
            self.pending_drop_position = None
            self.interaction_message = "That board slot is no longer available"

        for event in self.events:
            if (
                event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
                and choice_type in ("card", "play_or_pass")
            ):
                for index, rect in enumerate(self.hand_card_rects):
                    if rect.collidepoint(event.pos) and index < len(player.hand.cards):
                        self.selected_card = player.hand.cards[index]
                        self.selected_card_index = index
                        self.drag.begin(
                            f"card:{index}",
                            event.pos,
                            {f"slot:{slot}" for slot in range(6) if self.board.positions[slot] is None},
                        )
                        self.interaction_message = ""
                        break
            elif event.type == pygame.MOUSEMOTION and self.drag.start is not None:
                self.drag.move(event.pos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.drag.start is not None:
                target = next(
                    (f"slot:{index}" for index, rect in enumerate(self.board_slot_rects) if rect.collidepoint(event.pos)),
                    None,
                )
                was_dragging = self.drag.dragging
                result = self.drag.release(target)
                if result and self.selected_card is not None:
                    # Store the drop first. set_choice wakes the game-logic
                    # thread, which can ask for POSITION immediately.
                    position = int(result[1].split(":", 1)[1])
                    self.pending_drop_position = position
                    accepted = strategy.set_choice(
                        ChoiceType.PLAY_OR_PASS
                        if choice_type == "play_or_pass"
                        else ChoiceType.CARD,
                        self.selected_card,
                    )
                    if accepted:
                        self.interaction_message = "Card committed — placing it on the board"
                    else:
                        self.pending_drop_position = None
                elif was_dragging:
                    self.interaction_message = "Drop on a highlighted empty board slot"

        if not self.mouse_clicked:
            return
        if choice_type == "pass":
            if self.action_rects.get("play", pygame.Rect(0, 0, 0, 0)).collidepoint(self.mouse_position):
                strategy.set_choice(ChoiceType.PASS, False)
            elif self.action_rects.get("pass", pygame.Rect(0, 0, 0, 0)).collidepoint(self.mouse_position):
                strategy.set_choice(ChoiceType.PASS, True)
        elif choice_type in ("card", "play_or_pass"):
            if self.action_rects.get("confirm_card", pygame.Rect(0, 0, 0, 0)).collidepoint(self.mouse_position) and self.selected_card is not None:
                strategy.set_choice(
                    ChoiceType.PLAY_OR_PASS
                    if choice_type == "play_or_pass"
                    else ChoiceType.CARD,
                    self.selected_card,
                )
            elif (
                choice_type == "play_or_pass"
                and self.action_rects.get("pass", pygame.Rect(0, 0, 0, 0)).collidepoint(self.mouse_position)
            ):
                strategy.set_choice(ChoiceType.PLAY_OR_PASS, PASS_SELECTION)
        elif choice_type in ("position", "target"):
            for index, rect in enumerate(self.board_slot_rects):
                if rect.collidepoint(self.mouse_position) and index in self.current_legal_indices:
                    enum_type = ChoiceType.POSITION if choice_type == "position" else ChoiceType.TARGET
                    strategy.set_choice(enum_type, index)
                    break
        elif choice_type == "use_ability":
            if self.action_rects.get("skip_ability", pygame.Rect(0, 0, 0, 0)).collidepoint(self.mouse_position):
                strategy.set_choice(ChoiceType.USE_ABILITY, False)
            elif self.action_rects.get("use_ability", pygame.Rect(0, 0, 0, 0)).collidepoint(self.mouse_position):
                strategy.set_choice(ChoiceType.USE_ABILITY, True)

    def game_loop(self):
        deck_1 = DBUtil().load_deck(self.p1_deck_id)
        deck_2 = DBUtil().load_deck(self.p2_deck_id)
        try:
            logic_p1 = create_player(1, deck_1, self.p1_controller)
            logic_p2 = create_player(2, deck_2, self.p2_controller)
        except ValueError as error:
            self.logic_error = str(error)
            self.playing = False
            return

        for player in (logic_p1, logic_p2):
            if hasattr(player.choice_strategy, "delay_seconds"):
                player.choice_strategy.delay_seconds = self.settings.ai_delay_ms / 1000

        self.p1 = logic_p1
        self.p2 = logic_p2
        self.board = Board()
        self.logic_error = None
        self.game_result = None
        self.changing_player = False
        self.changing_to_battle = False
        self.previous_game_state = None
        self.interaction_message = ""
        self.battle_continue_event.clear()

        def run_logic():
            try:
                self.game_result = run_game(
                    logic_p1,
                    logic_p2,
                    local_battle_display_strategy(
                        self.BATTLE_FRAME_SECONDS,
                        lambda: not self.playing or not self.running,
                        self.battle_continue_event.is_set,
                        self.battle_continue_event.clear,
                    ),
                    self.board,
                )
            except SystemExit:
                self.board.game_running = False
            except Exception as error:
                self.logic_error = f"{type(error).__name__}: {error}"
                self.board.game_running = False

        logic_thread = threading.Thread(
            target=run_logic,
            daemon=True,
        )
        logic_thread.start()
        human_players = [
            player
            for player in (logic_p1, logic_p2)
            if isinstance(player.choice_strategy, PygameChoiceStrategy)
        ]
        if len(human_players) == 1:
            self.p1 = human_players[0]
            self.p2 = logic_p2 if self.p1 is logic_p1 else logic_p1
        previous_turn = None

        while self.playing and self.running:
            self.check_events()
            if (
                self.START_KEY
                and (self.board.battle_event or {}).get("phase")
                in ("dragon_defeated", "dragon_survived")
            ):
                self.battle_continue_event.set()
            current_turn = self.board.player_on_turn
            if current_turn is not None and current_turn is not previous_turn:
                if len(human_players) == 2:
                    self.p1 = current_turn
                    self.p2 = logic_p2 if current_turn is logic_p1 else logic_p1
                    if previous_turn is not None:
                        self.changing_player = True
                        self._clear_hotseat_private_state()
                previous_turn = current_turn

            if self.previous_game_state != self.board.game_state:
                self.previous_game_state = self.board.game_state
            elif self.changing_player:
                if self._hotseat_handoff_confirmed():
                    self.changing_player = False
                elif self.BACK_KEY:
                    if self.confirm_dialog("Leave the active match?"):
                        self._leave_match(logic_thread, (logic_p1, logic_p2))
                        return
            elif self.BACK_KEY:
                if self.confirm_dialog("Leave the active match?"):
                    self._leave_match(logic_thread, (logic_p1, logic_p2))
                    return
            elif not self.board.game_running and (self.START_KEY or self.mouse_clicked):
                self._leave_match(logic_thread, (logic_p1, logic_p2))
                return
            else:
                self._handle_local_mouse_choice()
                self.handle_choice()
            self._draw_local_match_frame()
            self.window.blit(self.display, (0,0))
            pygame.display.update()
            self.reset_keys()
            self.clock.tick(60)

        for player in (logic_p1, logic_p2):
            if hasattr(player.choice_strategy, "exit_thread"):
                player.choice_strategy.exit_thread()
        logic_thread.join(timeout=1.0)

    def _leave_match(self, logic_thread, players):
        self.playing = False
        for player in players:
            if hasattr(player.choice_strategy, "exit_thread"):
                player.choice_strategy.exit_thread()
        logic_thread.join(timeout=1.0)

    def lan_host_game_loop(self, host, lobby, payload):
        deck_1 = DBUtil().load_deck(payload["host_deck_id"])
        deck_2 = DBUtil().load_deck(payload["guest_deck_id"])
        logic_p1 = Player(1, deck_1, PygameChoiceStrategy)
        logic_p2 = Player(2, deck_2, RemoteChoiceStrategy)
        self.p1, self.p2 = logic_p1, logic_p2
        self.board = Board()
        self.logic_error = None
        self.game_result = None
        self.playing = True
        self.selected_card = None
        self.selected_position = None
        self.pending_drop_position = None
        self.battle_continue_event.clear()
        channel = HostMatchChannel(
            host,
            payload["match_id"],
            lambda: serialize_game_state(self.board, logic_p2, logic_p1),
        )
        logic_p2.choice_strategy.channel = channel

        def run_logic():
            try:
                self.game_result = run_game(
                    logic_p1,
                    logic_p2,
                    network_display_strategy(
                        channel,
                        self.BATTLE_FRAME_SECONDS,
                        lambda: (
                            not self.playing
                            or not self.running
                            or channel.disconnected
                        ),
                        self.battle_continue_event.is_set,
                        self.battle_continue_event.clear,
                    ),
                    self.board,
                    seed=int(payload["seed"]),
                    starting_player_id=int(payload["starting_player_id"]),
                )
            except SystemExit as error:
                if str(error):
                    self.logic_error = str(error)
                self.board.game_running = False
            except TimeoutError:
                self.logic_error = "Guest did not respond before the action timeout"
                self.board.game_running = False
            except Exception as error:
                self.logic_error = f"{type(error).__name__}: {error}"
                self.board.game_running = False

        logic_thread = threading.Thread(target=run_logic, name="lan-host-game", daemon=True)
        logic_thread.start()
        result_sent = False
        interruption_sent = False
        while self.playing and self.running:
            self.check_events()
            if (
                self.START_KEY
                and (self.board.battle_event or {}).get("phase")
                in ("dragon_defeated", "dragon_survived")
            ):
                self.battle_continue_event.set()
            channel.pump()
            if channel.disconnected:
                self.logic_error = channel.error or "Guest disconnected"
                logic_p1.choice_strategy.exit_thread()
                self.board.game_running = False
            if self.BACK_KEY:
                if self.confirm_dialog("Leave the active LAN match?"):
                    self.logic_error = "Host ended the match"
                    try:
                        host.peer.send(
                            MessageType.MATCH_RESULT,
                            {
                                "state": serialize_game_state(
                                    self.board,
                                    logic_p2,
                                    logic_p1,
                                    status="interrupted",
                                ),
                                "aborted": True,
                                "reason": self.logic_error,
                            },
                            match_id=payload["match_id"],
                        )
                        interruption_sent = True
                    except ConnectionError:
                        pass
                    break
            self._handle_local_mouse_choice()
            self.handle_choice()
            if self.game_result is not None and not result_sent:
                snapshot = serialize_game_state(self.board, logic_p2, logic_p1, status="finished")
                try:
                    host.peer.send(
                        MessageType.MATCH_RESULT,
                        {"state": snapshot, "result": vars(self.game_result)},
                        match_id=payload["match_id"],
                    )
                except ConnectionError:
                    pass
                result_sent = True
            if self.logic_error and not result_sent and not interruption_sent:
                try:
                    host.peer.send(
                        MessageType.MATCH_RESULT,
                        {
                            "state": serialize_game_state(
                                self.board,
                                logic_p2,
                                logic_p1,
                                status="interrupted",
                            ),
                            "aborted": True,
                            "reason": self.logic_error,
                        },
                        match_id=payload["match_id"],
                    )
                except (AttributeError, ConnectionError):
                    pass
                interruption_sent = True
            if self.game_result is not None and (self.START_KEY or self.mouse_clicked):
                break
            if self.logic_error and (self.START_KEY or self.mouse_clicked):
                break
            self.draw_responsive_game()
            if self.logic_error:
                self.draw_notice_overlay("LAN match interrupted", self.logic_error)
            self.window.blit(self.display, (0, 0))
            pygame.display.update()
            self.reset_keys()
            self.clock.tick(60)

        self.playing = False
        logic_p1.choice_strategy.exit_thread()
        channel.disconnected = True
        channel.error = channel.error or "Match closed"
        logic_thread.join(timeout=1.0)
        self.reset_keys()

    def lan_client_game_loop(self, client, payload):
        if not client or not client.peer:
            return
        self.playing = True
        self.logic_error = None
        state = None
        request = None
        finished = False
        self.selected_card_index = None
        self.selected_position = None
        self.pending_drop_position = None
        match_id = payload.get("match_id")
        while self.playing and self.running:
            self.check_events()
            for event in client.poll():
                if event.kind == "message" and event.message:
                    message = event.message
                    message_type = MessageType(message.type)
                    if message_type == MessageType.STATE_SNAPSHOT:
                        state = message.payload
                    elif message_type == MessageType.CHOICE_REQUEST:
                        request = message
                        state = (message.payload or {}).get("state", state)
                        self.current_legal_indices = (message.payload or {}).get("legal_indices", [])
                        if (
                            (message.payload or {}).get("choice_type") == "position"
                            and self.pending_drop_position in self.current_legal_indices
                        ):
                            self._send_client_action(client, request, self.pending_drop_position)
                            self.pending_drop_position = None
                            request = None
                    elif message_type == MessageType.MATCH_RESULT:
                        state = (message.payload or {}).get("state", state)
                        if (message.payload or {}).get("aborted"):
                            self.logic_error = str(
                                (message.payload or {}).get(
                                    "reason",
                                    "The host ended the match",
                                )
                            )
                        finished = True
                        request = None
                    elif message_type == MessageType.ERROR:
                        self.logic_error = str((message.payload or {}).get("message", "Host rejected the action"))
                    elif message_type == MessageType.DISCONNECT:
                        self.logic_error = str((message.payload or {}).get("reason", "Host disconnected"))
                        finished = True
                elif event.kind in ("error", "protocol_error", "disconnected"):
                    self.logic_error = event.detail or "Disconnected from host"
                    finished = True

            choice_type = (request.payload or {}).get("choice_type") if request else None
            if state is not None:
                self.draw_match_state(
                    state,
                    choice_type,
                    notice="Waiting for the host" if not request else "",
                    return_destination="lobby",
                    battle_continue_owner="host",
                )
                if request:
                    sent = self._handle_client_choice(client, request, state)
                    if sent:
                        request = None
                if self.logic_error:
                    self.draw_notice_overlay("LAN connection", self.logic_error)
            else:
                self.draw_background()
                self.draw_text("Waiting for the host…", self.TEXT_LARGE, self.DISPLAY_W // 2, self.DISPLAY_H // 2)

            if self.BACK_KEY and self.confirm_dialog("Leave the active LAN match?"):
                try:
                    client.peer.send(
                        MessageType.DISCONNECT,
                        {"reason": "Guest left the match"},
                        match_id=match_id,
                    )
                except ConnectionError:
                    pass
                break
            if finished and (self.START_KEY or self.mouse_clicked):
                break
            self.window.blit(self.display, (0, 0))
            pygame.display.update()
            self.reset_keys()
            self.clock.tick(60)

        self.playing = False
        if client.peer and client.peer.state.value == "connected":
            try:
                client.peer.send(MessageType.RETURN_TO_LOBBY, {}, match_id=match_id)
            except ConnectionError:
                pass
        self.reset_keys()

    def _send_client_action(self, client, request, value):
        client.peer.send(
            MessageType.PLAYER_ACTION,
            {"value": value},
            request_id=request.request_id,
            match_id=request.match_id,
        )

    def _handle_client_choice(self, client, request, state):
        choice_type = (request.payload or {}).get("choice_type")
        self._sync_choice_defaults(choice_type)
        legal = set((request.payload or {}).get("legal_indices", []))
        if choice_type == "play_or_pass" and self.PASS_KEY:
            self._send_client_action(client, request, "pass")
            return True
        if choice_type == "pass" and self.PASS_KEY:
            self._send_client_action(client, request, True)
            return True
        if choice_type == "use_ability":
            if self.USE_ABILITY_KEY:
                self._send_client_action(client, request, True)
                return True
            if self.SKIP_ABILITY_KEY:
                self._send_client_action(client, request, False)
                return True
        for event in self.events:
            if (
                event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
                and choice_type in ("card", "play_or_pass")
            ):
                for index, rect in enumerate(self.hand_card_rects):
                    if rect.collidepoint(event.pos) and index in legal:
                        self.selected_card_index = index
                        self.drag.begin(
                            f"card:{index}",
                            event.pos,
                            {f"slot:{slot}" for slot, card in enumerate(state.get("board", [])) if card is None},
                        )
                        self.interaction_message = ""
                        break
            elif event.type == pygame.MOUSEMOTION and self.drag.start is not None:
                self.drag.move(event.pos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.drag.start is not None:
                target = next(
                    (f"slot:{index}" for index, rect in enumerate(self.board_slot_rects) if rect.collidepoint(event.pos)),
                    None,
                )
                was_dragging = self.drag.dragging
                result = self.drag.release(target)
                if result and self.selected_card_index is not None:
                    self.pending_drop_position = int(result[1].split(":", 1)[1])
                    self._send_client_action(client, request, self.selected_card_index)
                    self.interaction_message = ""
                    return True
                if was_dragging:
                    self.interaction_message = "Drop on a highlighted empty board slot"

        if self.LEFT_KEY or self.RIGHT_KEY:
            if choice_type in ("card", "play_or_pass") and legal:
                ordered = sorted(legal)
                current = self.selected_card_index if self.selected_card_index in legal else ordered[0]
                offset = -1 if self.LEFT_KEY else 1
                self.selected_card_index = ordered[(ordered.index(current) + offset) % len(ordered)]
            elif choice_type in ("position", "target") and legal:
                ordered = sorted(legal)
                current = self.selected_position if self.selected_position in legal else ordered[0]
                offset = -1 if self.LEFT_KEY else 1
                self.selected_position = ordered[(ordered.index(current) + offset) % len(ordered)]

        if self.mouse_clicked:
            if choice_type == "pass":
                if self.action_rects.get("play", pygame.Rect(0, 0, 0, 0)).collidepoint(self.mouse_position):
                    self._send_client_action(client, request, False)
                    return True
                if self.action_rects.get("pass", pygame.Rect(0, 0, 0, 0)).collidepoint(self.mouse_position):
                    self._send_client_action(client, request, True)
                    return True
            elif choice_type in ("card", "play_or_pass"):
                for index, rect in enumerate(self.hand_card_rects):
                    if rect.collidepoint(self.mouse_position) and index in legal:
                        self.selected_card_index = index
                if (
                    self.selected_card_index in legal
                    and self.action_rects.get("confirm_card", pygame.Rect(0, 0, 0, 0)).collidepoint(self.mouse_position)
                ):
                    self._send_client_action(client, request, self.selected_card_index)
                    return True
                if (
                    choice_type == "play_or_pass"
                    and self.action_rects.get("pass", pygame.Rect(0, 0, 0, 0)).collidepoint(self.mouse_position)
                ):
                    self._send_client_action(client, request, "pass")
                    return True
            elif choice_type in ("position", "target"):
                for index, rect in enumerate(self.board_slot_rects):
                    if rect.collidepoint(self.mouse_position) and index in legal:
                        self._send_client_action(client, request, index)
                        return True
            elif choice_type == "use_ability":
                if self.action_rects.get("skip_ability", pygame.Rect(0, 0, 0, 0)).collidepoint(self.mouse_position):
                    self._send_client_action(client, request, False)
                    return True
                if self.action_rects.get("use_ability", pygame.Rect(0, 0, 0, 0)).collidepoint(self.mouse_position):
                    self._send_client_action(client, request, True)
                    return True

        if self.START_KEY:
            if choice_type == "pass":
                self._send_client_action(client, request, False)
                return True
            if choice_type in ("card", "play_or_pass") and self.selected_card_index in legal:
                self._send_client_action(client, request, self.selected_card_index)
                return True
            if choice_type in ("position", "target") and self.selected_position in legal:
                self._send_client_action(client, request, self.selected_position)
                return True
            if choice_type == "use_ability":
                self._send_client_action(client, request, self.binary_choice)
                return True
        return False

    def draw_notice_overlay(self, title, detail, *, color=None):
        metrics = self.layout
        color = color or self.palette.danger
        panel = metrics.centered_panel(0.72, 0.34)
        rect = pygame.Rect(panel.x, panel.y, panel.width, panel.height)
        pygame.draw.rect(self.display, self.palette.panel, rect, border_radius=12)
        pygame.draw.rect(self.display, color, rect, 2, border_radius=12)
        self.draw_text(title, metrics.font_large, panel.center[0], panel.y + panel.height // 3, color)
        self.draw_text(detail, metrics.font_normal, panel.center[0], panel.y + panel.height * 2 // 3)

    def confirm_dialog(self, title):
        selected = False
        self.reset_keys()
        while self.running:
            self.check_events()
            if self.BACK_KEY:
                self.reset_keys()
                return False
            if self.LEFT_KEY or self.RIGHT_KEY:
                selected = not selected
            if self.START_KEY:
                self.reset_keys()
                return selected
            metrics = self.layout
            self.draw_background()
            panel = metrics.centered_panel(0.68, 0.36)
            rect = pygame.Rect(panel.x, panel.y, panel.width, panel.height)
            pygame.draw.rect(self.display, self.palette.panel, rect, border_radius=12)
            pygame.draw.rect(self.display, self.palette.border, rect, 2, border_radius=12)
            self.draw_text(title, metrics.font_large, panel.center[0], panel.y + panel.height // 3)
            labels = (("Cancel", False), ("Leave", True))
            button_w = (panel.width - metrics.margin * 2 - metrics.gap) // 2
            for index, (label, value) in enumerate(labels):
                button = pygame.Rect(
                    panel.x + metrics.margin + index * (button_w + metrics.gap),
                    panel.y + panel.height * 2 // 3,
                    button_w,
                    metrics.target_height,
                )
                if self.mouse_clicked and button.collidepoint(self.mouse_position):
                    self.reset_keys()
                    return value
                pygame.draw.rect(
                    self.display,
                    self.palette.selected if selected == value else self.palette.panel_alt,
                    button,
                    border_radius=8,
                )
                pygame.draw.rect(self.display, self.palette.danger if value else self.palette.border, button, 2, border_radius=8)
                self.draw_text(label, metrics.font_normal, button.centerx, button.centery)
            self.window.blit(self.display, (0, 0))
            pygame.display.update()
            self.reset_keys()
            self.clock.tick(60)
        return False

    def draw_text(self, text, size, x, y, color=None):
        font = pygame.font.Font(self.font_name, int(size))
        text_surface = font.render(str(text), True, color or self.WHITE)
        text_rect = text_surface.get_rect()
        text_rect.center = (x,y)
        self.display.blit(text_surface, text_rect)

    def draw_text_left(self, text, size, x, y, color=None, max_width=None):
        font = pygame.font.Font(self.font_name, int(size))
        value = str(text)
        if max_width is not None:
            while value and font.size(value)[0] > max_width:
                value = value[:-1]
            if value != str(text) and len(value) > 3:
                value = value[:-3] + "..."
        text_surface = font.render(value, True, color or self.WHITE)
        self.display.blit(text_surface, (int(x), int(y - text_surface.get_height() / 2)))

    def draw_image(self, image_path, x, y, width, height):
        image = pygame.image.load(image_path)
        image = pygame.transform.scale(image, (int(width), int(height)))
        self.display.blit(image, (x, y))
