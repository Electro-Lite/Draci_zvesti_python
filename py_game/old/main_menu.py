
# (This is the original Pygame main menu with one small change: the "Decks" button launches
# the external Tkinter Deck Builder (deck_builder.py) as a separate process.)

import pygame
import sys
import json
import os
import subprocess

# --- Configuration ---
WIDTH, HEIGHT = 800, 600
FPS = 60
BG_COLOR = (30, 30, 40)
CARD_COLOR = (46, 52, 64)
ACCENT = (100, 200, 180)
WHITE = (230, 230, 230)
GRAY = (150, 150, 150)

DECKS_FILE = 'decks.json'

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption('Main Menu')
clock = pygame.time.Clock()

FONT = pygame.font.SysFont(None, 28)
BIG = pygame.font.SysFont(None, 36)
TITLE_FONT = pygame.font.SysFont(None, 56)

# --- Utilities ---

def load_decks():
    if not os.path.exists(DECKS_FILE):
        return []
    try:
        with open(DECKS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def save_decks(decks):
    try:
        with open(DECKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(decks, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print('Failed to save decks:', e)


# --- UI Widgets ---
class Button:
    def __init__(self, rect, text, onclick=None, font=None):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.onclick = onclick
        self.font = font or FONT

    def draw(self, surf, hover=False):
        color = ACCENT if hover else CARD_COLOR
        pygame.draw.rect(surf, color, self.rect, border_radius=8)
        txt = self.font.render(self.text, True, WHITE)
        tr = txt.get_rect(center=self.rect.center)
        surf.blit(txt, tr)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                if self.onclick:
                    self.onclick()


class TextInput:
    def __init__(self, rect, text=''):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.active = False
        self.cursor_timer = 0

    def draw(self, surf):
        pygame.draw.rect(surf, CARD_COLOR, self.rect, border_radius=6)
        pygame.draw.rect(surf, GRAY, self.rect, width=2, border_radius=6)
        txt = FONT.render(self.text, True, WHITE)
        surf.blit(txt, (self.rect.x + 8, self.rect.y + (self.rect.h - txt.get_height()) // 2))
        # cursor
        if self.active and (pygame.time.get_ticks() // 500) % 2:
            cursor_x = self.rect.x + 8 + txt.get_width() + 2
            cursor_y = self.rect.y + 8
            pygame.draw.rect(surf, WHITE, (cursor_x, cursor_y, 2, self.rect.h - 16))

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
        if not self.active:
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self.active = False
            elif event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            else:
                if len(event.unicode) > 0 and len(self.text) < 64:
                    self.text += event.unicode


# --- App State / Screens ---
class App:
    def __init__(self):
        self.screen = 'menu'  # menu, play, decks, train, settings, about
        self.running = True
        self.decks = load_decks()
        self.selected_deck_index = None
        self.message = ''
        self.create_ui()

    def create_ui(self):
        # Main menu buttons
        btn_w, btn_h = 200, 50
        cx = WIDTH // 2 - btn_w // 2
        start_y = 160
        gap = 12
        self.buttons = []

        def make_button(y, text, target=None, onclick=None):
            def go():
                if onclick:
                    onclick()
                elif target:
                    self.screen = target
                    self.message = ''
            b = Button((cx, y, btn_w, btn_h), text, onclick=go, font=BIG)
            self.buttons.append(b)
            return b

        make_button(start_y, 'Play', 'play')
        # Decks button launches external Tkinter Deck Builder (deck_builder.py)
        make_button(start_y + (btn_h + gap) * 1, 'Decks', onclick=self.open_deck_builder)
        make_button(start_y + (btn_h + gap) * 2, 'Train', 'train')
        make_button(start_y + (btn_h + gap) * 3, 'Settings', 'settings')
        make_button(start_y + (btn_h + gap) * 4, 'About', 'about')
        # quit separately
        quit_btn = Button((cx, start_y + (btn_h + gap) * 5, btn_w, btn_h), 'Quit', onclick=self.quit_app, font=BIG)
        self.buttons.append(quit_btn)

        # Play submenu buttons
        sub_w = 220
        sx = WIDTH // 2 - sub_w // 2
        sy = 180
        self.play_buttons = []
        self.play_buttons.append(Button((sx, sy, sub_w, 48), 'Play Online', onclick=lambda: self.show_message('Play Online not implemented'), font=FONT))
        self.play_buttons.append(Button((sx, sy + 60, sub_w, 48), 'Play Hot Seat', onclick=lambda: self.show_message('Play Hot Seat selected'), font=FONT))
        self.play_buttons.append(Button((sx, sy + 120, sub_w, 48), 'Play AI', onclick=lambda: self.show_message('Play vs AI selected'), font=FONT))
        back_btn = Button((20, HEIGHT - 70, 120, 44), 'Back', onclick=lambda: self.set_screen('menu'))
        self.play_buttons.append(back_btn)

        # Decks UI (kept minimal in case you still want the Pygame deck list available)
        self.deck_buttons = []
        self.deck_list_rect = pygame.Rect(50, 120, 500, 380)
        self.deck_create_btn = Button((580, 150, 180, 44), 'Create New', onclick=self.open_create_deck)
        self.deck_edit_btn = Button((580, 210, 180, 44), 'Edit', onclick=self.open_edit_deck)
        self.deck_delete_btn = Button((580, 270, 180, 44), 'Delete', onclick=self.delete_selected_deck)
        self.deck_back_btn = Button((580, 330, 180, 44), 'Back', onclick=lambda: self.set_screen('menu'))

        # Deck input dialog
        self.deck_input = TextInput((200, 220, 400, 44))
        self.deck_dialog_open = False
        self.editing_index = None

    def open_deck_builder(self):
        """Launch the standalone Tkinter deck builder in a separate process.
        This keeps the Pygame loop running. The deck_builder.py file must be in the same directory.
        """
        try:
            folder = os.path.dirname(os.path.abspath(__file__) )
            print(folder)
            script = os.path.join(folder, 'deck_builder_menu.py')
            if not os.path.exists(script):
                self.show_message('deck_builder.py not found in the same folder')
                return
            # spawn a new python process
            subprocess.Popen([sys.executable, script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.show_message('Deck Builder opened')
        except Exception as e:
            self.show_message(f'Failed to open Deck Builder: {e}')

    def quit_app(self):
        self.running = False

    def set_screen(self, s):
        self.screen = s
        self.deck_dialog_open = False
        self.deck_input.active = False

    def show_message(self, msg):
        self.message = msg
        print(msg)

    # Deck actions (unchanged from original simple implementation)
    def open_create_deck(self):
        self.deck_dialog_open = True
        self.deck_input.text = ''
        self.editing_index = None
        self.deck_input.active = True

    def open_edit_deck(self):
        idx = self.selected_deck_index
        if idx is None or idx < 0 or idx >= len(self.decks):
            self.show_message('No deck selected to edit')
            return
        self.deck_dialog_open = True
        self.deck_input.text = self.decks[idx].get('name', '')
        self.deck_input.active = True
        self.editing_index = idx

    def delete_selected_deck(self):
        idx = self.selected_deck_index
        if idx is None or idx < 0 or idx >= len(self.decks):
            self.show_message('No deck selected to delete')
            return
        name = self.decks[idx].get('name', '<unnamed>')
        self.decks.pop(idx)
        save_decks(self.decks)
        self.selected_deck_index = None
        self.show_message(f'Deleted deck "{name}"')

    def finalize_deck_dialog(self):
        name = self.deck_input.text.strip()
        if not name:
            self.show_message('Deck name cannot be empty')
            return
        if self.editing_index is None:
            deck = {'name': name, 'cards': []}
            self.decks.append(deck)
            save_decks(self.decks)
            self.show_message(f'Created deck "{name}"')
        else:
            self.decks[self.editing_index]['name'] = name
            save_decks(self.decks)
            self.show_message(f'Edited deck "{name}"')
        self.deck_dialog_open = False
        self.deck_input.active = False
        self.editing_index = None

    def draw(self):
        screen.fill(BG_COLOR)
        if self.screen == 'menu':
            self.draw_menu()
        elif self.screen == 'play':
            self.draw_play()
        elif self.screen == 'decks':
            self.draw_decks()
        elif self.screen == 'train':
            self.draw_train()
        elif self.screen == 'settings':
            self.draw_settings()
        elif self.screen == 'about':
            self.draw_about()

        # global message
        if self.message:
            msg = FONT.render(self.message, True, WHITE)
            screen.blit(msg, (20, HEIGHT - 30))

    def draw_menu(self):
        title = TITLE_FONT.render('Main Menu', True, WHITE)
        screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 50))
        mx, my = pygame.mouse.get_pos()
        for b in self.buttons:
            b.draw(screen, hover=b.rect.collidepoint((mx, my)))

    def draw_play(self):
        title = TITLE_FONT.render('Play', True, WHITE)
        screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 50))
        mx, my = pygame.mouse.get_pos()
        for b in self.play_buttons:
            b.draw(screen, hover=b.rect.collidepoint((mx, my)))

    def draw_decks(self):
        title = TITLE_FONT.render('Decks', True, WHITE)
        screen.blit(title, (50, 40))
        # list box
        pygame.draw.rect(screen, CARD_COLOR, self.deck_list_rect, border_radius=8)
        pygame.draw.rect(screen, GRAY, self.deck_list_rect, width=2, border_radius=8)
        # draw decks
        x, y = self.deck_list_rect.x + 8, self.deck_list_rect.y + 8
        item_h = 48
        mx, my = pygame.mouse.get_pos()
        for i, deck in enumerate(self.decks):
            item_rect = pygame.Rect(x, y + i * (item_h + 8), self.deck_list_rect.w - 16, item_h)
            color = (70, 70, 80) if i == self.selected_deck_index else (56, 60, 70)
            pygame.draw.rect(screen, color, item_rect, border_radius=6)
            name = deck.get('name', '<unnamed>')
            txt = FONT.render(name, True, WHITE)
            screen.blit(txt, (item_rect.x + 10, item_rect.y + (item_h - txt.get_height()) // 2))
            meta = FONT.render(f"{len(deck.get('cards', []))} cards", True, GRAY)
            screen.blit(meta, (item_rect.right - meta.get_width() - 10, item_rect.y + (item_h - meta.get_height()) // 2))

        # deck buttons
        mx, my = pygame.mouse.get_pos()
        for btn in [self.deck_create_btn, self.deck_edit_btn, self.deck_delete_btn, self.deck_back_btn]:
            btn.draw(screen, hover=btn.rect.collidepoint((mx, my)))

        # dialog
        if self.deck_dialog_open:
            self.draw_deck_dialog()

    def draw_deck_dialog(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        screen.blit(overlay, (0, 0))
        box = pygame.Rect(WIDTH // 2 - 320 // 2, HEIGHT // 2 - 160 // 2, 320, 160)
        pygame.draw.rect(screen, CARD_COLOR, box, border_radius=8)
        pygame.draw.rect(screen, GRAY, box, width=2, border_radius=8)
        title_text = 'Create Deck' if self.editing_index is None else 'Edit Deck'
        title = BIG.render(title_text, True, WHITE)
        screen.blit(title, (box.x + 16, box.y + 12))
        self.deck_input.rect.topleft = (box.x + 16, box.y + 56)
        self.deck_input.rect.w = box.w - 32
        self.deck_input.draw(screen)
        ok_btn = Button((box.x + 30, box.y + 110, 100, 36), 'OK', onclick=self.finalize_deck_dialog)
        cancel_btn = Button((box.x + box.w - 130, box.y + 110, 100, 36), 'Cancel', onclick=lambda: self.cancel_deck_dialog())
        mx, my = pygame.mouse.get_pos()
        ok_btn.draw(screen, hover=ok_btn.rect.collidepoint((mx, my)))
        cancel_btn.draw(screen, hover=cancel_btn.rect.collidepoint((mx, my)))

    def cancel_deck_dialog(self):
        self.deck_dialog_open = False
        self.deck_input.active = False
        self.editing_index = None

    def draw_train(self):
        title = TITLE_FONT.render('Train', True, WHITE)
        screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 50))
        msg = FONT.render('Training tools would appear here. (Not implemented)', True, WHITE)
        screen.blit(msg, (50, 150))
        back = Button((20, HEIGHT - 70, 120, 44), 'Back', onclick=lambda: self.set_screen('menu'))
        back.draw(screen, hover=back.rect.collidepoint(pygame.mouse.get_pos()))

    def draw_settings(self):
        title = TITLE_FONT.render('Settings', True, WHITE)
        screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 50))
        msg = FONT.render('Settings screen (Not implemented).', True, WHITE)
        screen.blit(msg, (50, 150))
        back = Button((20, HEIGHT - 70, 120, 44), 'Back', onclick=lambda: self.set_screen('menu'))
        back.draw(screen, hover=back.rect.collidepoint(pygame.mouse.get_pos()))

    def draw_about(self):
        title = TITLE_FONT.render('About', True, WHITE)
        screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 50))
        lines = [
            'Main Menu Demo - Pygame',
            'Features: Menu, Play submenu, Decks (create/edit/delete).',
            'This is a sample starter app.',
            'Press ESC to go back / quit.'
        ]
        for i, l in enumerate(lines):
            screen.blit(FONT.render(l, True, WHITE), (50, 150 + i * 28))
        back = Button((20, HEIGHT - 70, 120, 44), 'Back', onclick=lambda: self.set_screen('menu'))
        back.draw(screen, hover=back.rect.collidepoint(pygame.mouse.get_pos()))

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.screen == 'menu':
                    self.running = False
                else:
                    self.set_screen('menu')
            if event.key == pygame.K_r:
                self.decks = load_decks()
                self.show_message('Reloaded decks')

        if self.screen == 'menu':
            for b in self.buttons:
                b.handle_event(event)
        elif self.screen == 'play':
            for b in self.play_buttons:
                b.handle_event(event)
        elif self.screen == 'decks':
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and not self.deck_dialog_open:
                mx, my = event.pos
                x, y = self.deck_list_rect.x + 8, self.deck_list_rect.y + 8
                item_h = 48
                for i, deck in enumerate(self.decks):
                    item_rect = pygame.Rect(x, y + i * (item_h + 8), self.deck_list_rect.w - 16, item_h)
                    if item_rect.collidepoint((mx, my)):
                        self.selected_deck_index = i
                for btn in [self.deck_create_btn, self.deck_edit_btn, self.deck_delete_btn, self.deck_back_btn]:
                    btn.handle_event(event)
            if self.deck_dialog_open:
                self.deck_input.handle_event(event)
                if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                    self.finalize_deck_dialog()
        elif self.screen in ('train', 'settings', 'about'):
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if pygame.Rect(20, HEIGHT - 70, 120, 44).collidepoint(event.pos):
                    self.set_screen('menu')

    def update(self, dt):
        pass

    def run(self):
        while self.running:
            dt = clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                self.handle_event(event)
            self.update(dt)
            self.draw()
            pygame.display.flip()
        pygame.quit()
        sys.exit()


if __name__ == '__main__':
    app = App()
    app.run()


