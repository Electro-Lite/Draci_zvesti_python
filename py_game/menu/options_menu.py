from __future__ import annotations

from typing import TYPE_CHECKING

from py_game.menu.base_menu import Menu
from py_game.settings import AppSettings
from py_game.language import get_language, next_language_code

if TYPE_CHECKING:
    from py_game.game import Game


class OptionsMenu(Menu):
    RESOLUTIONS = ((800, 600), (1024, 768), (1280, 720), (1600, 900), (1920, 1080))

    def __init__(self, game: "Game"):
        super().__init__(game)
        self.selected = 0
        self.message = self.tr("settings_auto_save")
        self.message_color = self.game.palette.muted

    def _rows(self):
        settings = self.game.settings
        language_name = get_language(settings.language).name
        return [
            f"{self.tr('settings_language')}: {language_name}",
            f"{self.tr('settings_fullscreen')}: {self.tr('on') if settings.fullscreen else self.tr('off')}",
            f"{self.tr('settings_resolution')}: {settings.width} × {settings.height}",
            f"{self.tr('settings_volume')}: {settings.master_volume}%",
            f"{self.tr('settings_ai_delay')}: {settings.ai_delay_ms} ms",
            f"{self.tr('settings_tooltips')}: {self.tr('on') if settings.show_tooltips else self.tr('off')}",
            f"{self.tr('settings_player_name')}: {settings.player_name}",
            f"{self.tr('settings_lan_port')}: {settings.lan_port}",
            self.tr("settings_reset"),
            self.tr("back"),
        ]

    @staticmethod
    def _step(value, direction, minimum, maximum, amount):
        return max(minimum, min(maximum, value + direction * amount))

    def _edit(self, direction=1):
        settings = self.game.settings
        if self.selected == 0:
            settings.language = next_language_code(settings.language, direction)
            self.game.language = get_language(settings.language)
        elif self.selected == 1:
            settings.fullscreen = not settings.fullscreen
        elif self.selected == 2:
            try:
                index = self.RESOLUTIONS.index((settings.width, settings.height))
            except ValueError:
                index = 2
            settings.width, settings.height = self.RESOLUTIONS[
                (index + direction) % len(self.RESOLUTIONS)
            ]
        elif self.selected == 3:
            settings.master_volume = self._step(settings.master_volume, direction, 0, 100, 5)
        elif self.selected == 4:
            settings.ai_delay_ms = self._step(settings.ai_delay_ms, direction, 0, 5000, 50)
        elif self.selected == 5:
            settings.show_tooltips = not settings.show_tooltips
        elif self.selected == 6:
            value = self._text_dialog(self.tr("settings_player_name"), settings.player_name, 24)
            if value and value.strip():
                settings.player_name = value.strip()
        elif self.selected == 7:
            value = self._text_dialog(self.tr("settings_lan_port"), str(settings.lan_port), 5, str.isdigit)
            if value:
                port = int(value)
                if not 1024 <= port <= 65535:
                    self.message = self.tr("lan_port_error")
                    self.message_color = self.game.palette.danger
                    return
                settings.lan_port = port
        elif self.selected == 8:
            if not self.confirm_action(
                self.tr("settings_reset_title"),
                (self.tr("settings_reset_detail"),),
                confirm_label=self.tr("settings_reset_action"),
            ):
                return
            self.game.settings = AppSettings()
        elif self.selected == 9:
            self.return_to_previous()
            return
        try:
            self.game.apply_settings()
            self.message = self.tr("settings_saved")
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
                self.tr("settings_title"),
                self.tr("settings_subtitle"),
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
