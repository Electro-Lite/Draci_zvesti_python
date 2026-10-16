import pygame as pg
from typing import TYPE_CHECKING

from py_game.ui.layout import RectSpec
from py_game.ui.widgets import Button, TextInput

if TYPE_CHECKING:
    from py_game.game import Game

class Menu():
    def __init__(self, game: 'Game'):
        self.game = game
        self.mid_w, self.mid_h = self.game.DISPLAY_W / 2, self.game.DISPLAY_H / 2
        self.run_display = True
        self.cursor_rect = pg.Rect(0, 0, 20, 20)
        self.offset = -100

        self.TEXT_SMALL  = self.game.TEXT_SMALL
        self.TEXT_NORMAL = self.game.TEXT_NORMAL
        self.TEXT_LARGE  = self.game.TEXT_LARGE
        self.previous_menu = None
        self.buttons: list[Button] = []

    def refresh_layout(self):
        self.mid_w = self.game.DISPLAY_W / 2
        self.mid_h = self.game.DISPLAY_H / 2
        self.TEXT_SMALL = self.game.TEXT_SMALL
        self.TEXT_NORMAL = self.game.TEXT_NORMAL
        self.TEXT_LARGE = self.game.TEXT_LARGE

    def begin_frame(self):
        self.game.check_events()
        self.refresh_layout()

    def build_menu_buttons(
        self,
        labels: list[str],
        selected: int,
        *,
        top_ratio: float = 0.24,
        bottom_ratio: float = 0.90,
        width_ratio: float = 0.56,
        enabled: list[bool] | None = None,
    ) -> list[Button]:
        metrics = self.game.layout
        width = min(
            int(self.game.DISPLAY_W * width_ratio),
            round(720 * max(1.0, metrics.scale)),
        )
        area = RectSpec(
            (self.game.DISPLAY_W - width) // 2,
            int(self.game.DISPLAY_H * top_ratio),
            width,
            int(self.game.DISPLAY_H * (bottom_ratio - top_ratio)),
        )
        rows = metrics.vertical_rows(len(labels), area)
        mouse = self.game.mouse_position
        self.buttons = [
            Button(
                key=str(index),
                label=label,
                rect=rect,
                enabled=enabled[index] if enabled else True,
                selected=index == selected,
                hovered=rect.contains(mouse),
            )
            for index, (label, rect) in enumerate(zip(labels, rows))
        ]
        return self.buttons

    def clicked_button(self, buttons: list[Button] | None = None) -> int | None:
        if not self.game.mouse_clicked:
            return None
        for index, button in enumerate(buttons or self.buttons):
            if button.hit_test(self.game.mouse_position):
                return index
        return None

    def draw_background(self):
        self.game.draw_background()

    def draw_title(self, title: str, subtitle: str | None = None):
        metrics = self.game.layout
        self.game.draw_text(
            title,
            metrics.font_large,
            self.mid_w,
            metrics.margin + metrics.font_large // 2,
        )
        if subtitle:
            self.game.draw_text(
                subtitle,
                metrics.font_small,
                self.mid_w,
                metrics.margin + metrics.font_large + metrics.gap,
                self.game.palette.muted,
            )

    def draw_buttons(self, buttons: list[Button] | None = None):
        font = pg.font.Font(self.game.font_name, self.game.layout.font_normal)
        for button in buttons or self.buttons:
            button.draw(self.game.display, font, self.game.palette)

    def draw_message(self, message: str, color=None):
        if not message:
            return
        self.game.draw_text(
            message,
            self.game.layout.font_small,
            self.mid_w,
            self.game.DISPLAY_H - self.game.layout.margin,
            color or self.game.palette.muted,
        )

    def return_to_previous(self):
        self.run_display = False
        self.game.curr_menu = self.previous_menu
        if self.previous_menu is not None:
            self.previous_menu.run_display = True

    def prompt_text(self, title, initial="", *, max_length=64, validator=None):
        field = TextInput(initial, max_length, validator, focused=True)
        self.game.reset_keys()
        while self.game.running:
            self.begin_frame()
            for event in self.game.events:
                if event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE:
                    return None
                if event.type == pg.KEYDOWN and event.key in (pg.K_RETURN, pg.K_KP_ENTER):
                    return field.value
                field.handle_event(event)
            self.draw_text_prompt(title, field.value)
            self.blit_screen()
        return None

    def draw_text_prompt(self, title: str, value: str) -> None:
        """Draw the shared responsive text-entry dialog for UI and visual tests."""
        self.draw_background()
        panel = self.game.layout.centered_panel(0.68, 0.38)
        panel_rect = pg.Rect(panel.x, panel.y, panel.width, panel.height)
        pg.draw.rect(self.game.display, self.game.palette.panel, panel_rect, border_radius=12)
        pg.draw.rect(self.game.display, self.game.palette.border, panel_rect, 2, border_radius=12)
        self.game.draw_text(
            title,
            self.game.layout.font_large,
            panel.center[0],
            panel.y + panel.height // 4,
        )
        field_rect = pg.Rect(
            panel.x + self.game.layout.margin,
            panel.y + panel.height // 2,
            panel.width - self.game.layout.margin * 2,
            self.game.layout.target_height,
        )
        pg.draw.rect(self.game.display, self.game.palette.panel_alt, field_rect, border_radius=8)
        pg.draw.rect(self.game.display, self.game.palette.accent, field_rect, 2, border_radius=8)
        self.game.draw_text_left(
            value or " ",
            self.game.layout.font_normal,
            field_rect.x + self.game.layout.gap,
            field_rect.centery,
            max_width=field_rect.width - self.game.layout.gap * 2,
        )
        self.game.draw_text(
            "Enter to confirm  •  Escape to cancel",
            self.game.layout.font_small,
            panel.center[0],
            panel.bottom - self.game.layout.margin,
            self.game.palette.muted,
        )

    def confirm_action(self, title, lines=(), *, confirm_label="Confirm"):
        selected = False
        self.game.reset_keys()
        while self.game.running:
            self.begin_frame()
            if self.game.BACK_KEY:
                return False
            if self.game.LEFT_KEY or self.game.RIGHT_KEY:
                selected = not selected
            buttons = self._confirmation_buttons(confirm_label, selected)
            for button in buttons:
                button.hovered = button.rect.contains(self.game.mouse_position)
            if self.game.mouse_clicked:
                if buttons[0].hit_test(self.game.mouse_position):
                    return False
                if buttons[1].hit_test(self.game.mouse_position):
                    return True
            if self.game.START_KEY:
                return selected
            self.draw_confirmation(title, lines, confirm_label, selected, buttons)
            self.blit_screen()
        return False

    def _confirmation_buttons(self, confirm_label: str, selected: bool) -> list[Button]:
        panel = self.game.layout.centered_panel(0.72, 0.60)
        button_width = (
            panel.width - self.game.layout.margin * 2 - self.game.layout.gap
        ) // 2
        return [
            Button(
                "cancel",
                "Cancel",
                RectSpec(
                    panel.x + self.game.layout.margin,
                    panel.bottom - self.game.layout.margin - self.game.layout.target_height,
                    button_width,
                    self.game.layout.target_height,
                ),
                selected=not selected,
            ),
            Button(
                "confirm",
                confirm_label,
                RectSpec(
                    panel.x + self.game.layout.margin + button_width + self.game.layout.gap,
                    panel.bottom - self.game.layout.margin - self.game.layout.target_height,
                    button_width,
                    self.game.layout.target_height,
                ),
                selected=selected,
                destructive=confirm_label.lower()
                in {
                    "delete",
                    "discard",
                    "leave",
                    "reset",
                    "stop and quit",
                    "stop training",
                },
            ),
        ]

    def draw_confirmation(
        self,
        title: str,
        lines=(),
        confirm_label: str = "Confirm",
        selected: bool = False,
        buttons: list[Button] | None = None,
    ) -> None:
        """Draw a confirmation without consuming events (also used by review tooling)."""
        self.draw_background()
        panel = self.game.layout.centered_panel(0.72, 0.60)
        rect = pg.Rect(panel.x, panel.y, panel.width, panel.height)
        pg.draw.rect(self.game.display, self.game.palette.panel, rect, border_radius=12)
        pg.draw.rect(self.game.display, self.game.palette.border, rect, 2, border_radius=12)
        self.game.draw_text(
            title,
            self.game.layout.font_large,
            panel.center[0],
            panel.y + self.game.layout.margin + self.game.layout.font_large // 2,
        )
        line_top = panel.y + self.game.layout.margin + self.game.layout.font_large * 2
        line_bottom = panel.bottom - self.game.layout.margin * 2 - self.game.layout.target_height
        row_height = max(
            self.game.layout.font_small + 2,
            (line_bottom - line_top) // max(1, min(8, len(lines))),
        )
        for index, line in enumerate(lines[:8]):
            self.game.draw_text_left(
                str(line),
                self.game.layout.font_normal,
                panel.x + self.game.layout.margin,
                line_top + index * row_height,
                max_width=panel.width - self.game.layout.margin * 2,
            )
        buttons = buttons or self._confirmation_buttons(confirm_label, selected)
        font = pg.font.Font(self.game.font_name, self.game.layout.font_normal)
        for button in buttons:
            button.draw(self.game.display, font, self.game.palette)

    def show_lines(self, title, lines):
        self.game.reset_keys()
        while self.game.running:
            self.begin_frame()
            if self.game.BACK_KEY or self.game.START_KEY or self.game.mouse_clicked:
                return
            self.draw_lines_panel(title, lines)
            self.blit_screen()

    def draw_lines_panel(self, title: str, lines) -> None:
        """Draw a scroll-free compact details panel for up to twelve lines."""
        self.draw_background()
        panel = self.game.layout.centered_panel(0.82, 0.80)
        rect = pg.Rect(panel.x, panel.y, panel.width, panel.height)
        pg.draw.rect(self.game.display, self.game.palette.panel, rect, border_radius=12)
        pg.draw.rect(self.game.display, self.game.palette.border, rect, 2, border_radius=12)
        self.game.draw_text(
            title,
            self.game.layout.font_large,
            panel.center[0],
            panel.y + self.game.layout.margin,
        )
        usable = panel.height - self.game.layout.margin * 3 - self.game.layout.font_large
        row_height = max(24, usable // max(1, min(12, len(lines))))
        for index, line in enumerate(lines[:12]):
            self.game.draw_text_left(
                str(line),
                self.game.layout.font_small,
                panel.x + self.game.layout.margin,
                panel.y
                + self.game.layout.margin * 2
                + self.game.layout.font_large
                + index * row_height,
                max_width=panel.width - self.game.layout.margin * 2,
            )

    def draw_cursor(self):
        self.game.draw_text("*", self.TEXT_LARGE, self.cursor_rect.x, self.cursor_rect.y + 5)

    def blit_screen(self):
        self.game.window.blit(self.game.display, (0, 0))
        pg.display.update()
        self.game.reset_keys()
        self.game.clock.tick(60)

    def display_menu(self):
        raise NotImplementedError()
