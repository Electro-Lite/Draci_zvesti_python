from __future__ import annotations

from typing import TYPE_CHECKING

from py_game.menu.base_menu import Menu
from py_game.settings import AppSettings

if TYPE_CHECKING:
    from py_game.game import Game


class OptionsMenu(Menu):
    RESOLUTIONS = ((800, 600), (1024, 768), (1280, 720), (1600, 900), (1920, 1080))

    def __init__(self, game: "Game"):
        super().__init__(game)
        self.selected = 0
        self.message = "Settings are saved automatically"
        self.message_color = self.game.palette.muted

    def _rows(self):
        settings = self.game.settings
        return [
            f"Fullscreen: {'On' if settings.fullscreen else 'Off'}",
            f"Resolution: {settings.width} × {settings.height}",
            f"Master volume: {settings.master_volume}%",
            f"AI action delay: {settings.ai_delay_ms} ms",
            f"Tooltips: {'On' if settings.show_tooltips else 'Off'}",
            f"Player name: {settings.player_name}",
            f"LAN port: {settings.lan_port}",
            "Reset defaults",
            "Back",
        ]

    @staticmethod
    def _step(value, direction, minimum, maximum, amount):
        return max(minimum, min(maximum, value + direction * amount))

    def _edit(self, direction=1):
        settings = self.game.settings
        if self.selected == 0:
            settings.fullscreen = not settings.fullscreen
        elif self.selected == 1:
            try:
                index = self.RESOLUTIONS.index((settings.width, settings.height))
            except ValueError:
                index = 2
            settings.width, settings.height = self.RESOLUTIONS[
                (index + direction) % len(self.RESOLUTIONS)
            ]
        elif self.selected == 2:
            settings.master_volume = self._step(settings.master_volume, direction, 0, 100, 5)
        elif self.selected == 3:
            settings.ai_delay_ms = self._step(settings.ai_delay_ms, direction, 0, 5000, 50)
        elif self.selected == 4:
            settings.show_tooltips = not settings.show_tooltips
        elif self.selected == 5:
            value = self._text_dialog("Player name", settings.player_name, 24)
            if value and value.strip():
                settings.player_name = value.strip()
        elif self.selected == 6:
            value = self._text_dialog("LAN port", str(settings.lan_port), 5, str.isdigit)
            if value:
                port = int(value)
                if not 1024 <= port <= 65535:
                    self.message = "LAN port must be between 1024 and 65535"
                    self.message_color = self.game.palette.danger
                    return
                settings.lan_port = port
        elif self.selected == 7:
            if not self.confirm_action(
                "Reset all settings?",
                ("Display, audio, interaction, and LAN settings will be reset.",),
                confirm_label="Reset",
            ):
                return
            self.game.settings = AppSettings()
        elif self.selected == 8:
            self.return_to_previous()
            return
        try:
            self.game.apply_settings()
            self.message = "Settings saved"
            self.message_color = self.game.palette.success
        except (OSError, ValueError) as error:
            self.message = str(error)
            self.message_color = self.game.palette.danger

    def check_input(self):
        rows = self._rows()
        if self.game.BACK_KEY:
            self.return_to_previous()
            return
        if self.game.UP_KEY:
            self.selected = (self.selected - 1) % len(rows)
        if self.game.DOWN_KEY:
            self.selected = (self.selected + 1) % len(rows)
        if self.game.LEFT_KEY:
            self._edit(-1)
        elif self.game.RIGHT_KEY:
            self._edit(1)
        clicked = self.clicked_button()
        if clicked is not None:
            self.selected = clicked
            self._edit(1)
        elif self.game.START_KEY:
            self._edit(1)

    def display_menu(self):
        self.run_display = True
        while self.run_display and self.game.running:
            self.begin_frame()
            rows = self._rows()
            self.build_menu_buttons(
                rows,
                self.selected,
                top_ratio=0.18,
                bottom_ratio=0.90,
                width_ratio=0.64,
            )
            self.check_input()
            if not self.run_display:
                break
            self.draw_background()
            self.draw_title(
                "Settings",
                "Use Left/Right to adjust, Enter or click to activate",
            )
            self.draw_buttons()
            self.draw_message(self.message, self.message_color)
            self.blit_screen()

    def _text_dialog(self, title, initial, max_length, validator=None):
        return self.prompt_text(
            title,
            initial,
            max_length=max_length,
            validator=validator,
        )
