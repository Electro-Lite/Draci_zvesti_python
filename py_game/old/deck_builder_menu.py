# deck_builder_pygame.py
# Pygame reimplementation of the Tkinter Deck Builder you provided.
# Save near your project (cards.*, utils.database_utils) and run: python deck_builder_pygame.py
#
# Notes:
# - Uses DBUtil() the same way as your Tkinter app (get_all_cards, load_card, save_deck, load_deck, delete_deck).
# - Pillow (PIL) is optional. If available we use it to generate thumbnails for preview.
# - UI is intentionally simple and opinionated; meant to be a functional port, not pixel-perfect.

import pygame
import sys
import os
import math
import time
import traceback
from pathlib import Path

# Project-specific imports (must exist in your project)
from cards.card import Card
from utils.database_utils import DBUtil
from cards.power import Power

# Optional Pillow import
try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# Configuration
WIDTH, HEIGHT = 1200, 780
FPS = 60
BG = (28, 30, 36)
PANEL = (42, 46, 55)
ACCENT = (85, 200, 170)
TEXT = (230, 230, 230)
SUB = (170, 170, 170)
ERROR = (220, 100, 100)
PREVIEW_MAX = (360, 280)
MAX_DECK_CARDS = 12

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Deck Builder - Pygame")
clock = pygame.time.Clock()
FONT = pygame.font.SysFont(None, 20)
FONT_B = pygame.font.SysFont(None, 26)
TITLE_FONT = pygame.font.SysFont(None, 36)

# --- UI primitives: Button, TextInput, ScrollList, MessageBox simplicity ---


class Button:
    def __init__(self, rect, text, onclick=None, font=None):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.onclick = onclick
        self.font = font or FONT

    def draw(self, surf, hover=False):
        color = ACCENT if hover else PANEL
        pygame.draw.rect(surf, color, self.rect, border_radius=6)
        txt = self.font.render(self.text, True, BG if hover else TEXT)
        surf.blit(txt, txt.get_rect(center=self.rect.center))

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                if self.onclick:
                    self.onclick()


class TextInput:
    def __init__(self, rect, text=""):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.active = False
        self.cursor_show = True
        self.cursor_timer = 0

    def draw(self, surf):
        pygame.draw.rect(surf, PANEL, self.rect, border_radius=6)
        pygame.draw.rect(surf, SUB, self.rect, width=2, border_radius=6)
        txt = FONT.render(self.text or "", True, TEXT)
        surf.blit(txt, (self.rect.x + 6, self.rect.y + (self.rect.h - txt.get_height()) // 2))
        if self.active:
            # caret blink
            if self.cursor_show:
                cursor_x = self.rect.x + 6 + txt.get_width() + 2
                pygame.draw.rect(surf, TEXT, (cursor_x, self.rect.y + 6, 2, self.rect.h - 12))

    def update(self, dt):
        if self.active:
            self.cursor_timer += dt
            if self.cursor_timer >= 0.5:
                self.cursor_timer = 0
                self.cursor_show = not self.cursor_show

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
        if not self.active:
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key == pygame.K_RETURN:
                self.active = False
            else:
                if event.unicode and len(self.text) < 64:
                    self.text += event.unicode


class ScrollList:
    """Simple scrollable list. Items are strings. Single selection only."""
    def __init__(self, rect, items=None, line_h=28):
        self.rect = pygame.Rect(rect)
        self.items = items or []
        self.offset = 0
        self.line_h = line_h
        self.selected = None
        self.hover_index = None
        self.last_click_time = 0

    def set_items(self, items):
        self.items = list(items)
        self.offset = 0
        self.selected = None

    def draw(self, surf):
        pygame.draw.rect(surf, PANEL, self.rect, border_radius=6)
        pygame.draw.rect(surf, SUB, self.rect, width=2, border_radius=6)
        x = self.rect.x + 6
        y = self.rect.y + 6 - self.offset
        visible_h = self.rect.h - 12
        # clip
        clip = surf.get_clip()
        surf.set_clip(self.rect)
        for i, it in enumerate(self.items):
            item_rect = pygame.Rect(x, y + i * (self.line_h + 4), self.rect.w - 12, self.line_h)
            # selected background
            if i == self.selected:
                pygame.draw.rect(surf, (60, 80, 90), item_rect, border_radius=4)
            elif i == self.hover_index:
                pygame.draw.rect(surf, (50, 60, 70), item_rect, border_radius=4)
            # text
            txt = FONT.render(it, True, TEXT)
            surf.blit(txt, (item_rect.x + 6, item_rect.y + (self.line_h - txt.get_height()) // 2))
        surf.set_clip(clip)

    def handle_event(self, event, dbl_click_callback=None, select_callback=None):
        if event.type == pygame.MOUSEMOTION:
            mx, my = event.pos
            if self.rect.collidepoint((mx, my)):
                rel_y = my - (self.rect.y + 6) + self.offset
                idx = int(rel_y // (self.line_h + 4))
                if 0 <= idx < len(self.items):
                    self.hover_index = idx
                else:
                    self.hover_index = None
            else:
                self.hover_index = None
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and self.rect.collidepoint(event.pos):
                mx, my = event.pos
                rel_y = my - (self.rect.y + 6) + self.offset
                idx = int(rel_y // (self.line_h + 4))
                if 0 <= idx < len(self.items):
                    now = time.time()
                    if now - self.last_click_time < 0.35:
                        # double click
                        if dbl_click_callback:
                            dbl_click_callback(idx)
                    else:
                        self.selected = idx
                        if select_callback:
                            select_callback(idx)
                    self.last_click_time = now
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 4:  # wheel up
                self.offset = max(0, self.offset - (self.line_h + 4) * 3)
            if event.button == 5:  # wheel down
                max_off = max(0, len(self.items) * (self.line_h + 4) - (self.rect.h - 12))
                self.offset = min(max_off, self.offset + (self.line_h + 4) * 3)


# --- App State / Logic ---


class DeckBuilderPygame:
    def __init__(self):
        self.running = True
        self.status = "Ready"
        self.db = DBUtil()
        self.card_objs = []
        self.selected_card_obj = None
        self.current_deck = []  # list[Card]
        self.preview_surf = None
        self._preview_path = None

        # UI elements
        # left panel - search + card list
        self.search_input = TextInput((18, 56, 360, 34))
        self.card_list = ScrollList((18, 96, 360, 600))
        # right panel - deck management + deck list + details + preview
        self.deckname_input = TextInput((410, 56, 360, 34))
        self.btn_save = Button((790, 54, 120, 36), "Save Deck", onclick=self.save_deck)
        self.btn_load = Button((920, 54, 120, 36), "Load Deck", onclick=self.load_deck)
        self.btn_delete = Button((1050, 54, 120, 36), "Delete Deck", onclick=self.delete_deck)
        self.deck_list_ui = ScrollList((410, 110, 360, 210))
        self.btn_add = Button((18, 710, 360, 44), "Add to Deck", onclick=self.add_to_deck)
        self.btn_remove = Button((410, 330, 360, 36), "Remove from Deck", onclick=self.remove_from_deck)

        # card details area
        self.card_detail_rect = pygame.Rect(790, 110, 380, 400)
        self.preview_rect = pygame.Rect(790, 520, PREVIEW_MAX[0] + 20, PREVIEW_MAX[1] + 20)

        # load initial data
        self.refresh_card_list()
        self.refresh_deck_list()

        # double-click helpers: delegated inside ScrollList
        # keyboard shortcuts
        pygame.key.set_repeat(400, 80)

    # --- Data operations using DBUtil (same semantics as your Tkinter app) ---

    def refresh_card_list(self):
        try:
            cards = self.db.get_all_cards()
            self.card_objs = cards
            search = (self.search_input.text or "").lower()
            items = []
            for c in cards:
                if not search or (search in c.name.lower()) or (search in getattr(c, "id", "").lower()):
                    items.append(f"{getattr(c, 'id', '')} | {getattr(c, 'name', '')}")
            self.card_list.set_items(items)
            self.status = "Loaded cards"
        except Exception:
            self._log_exc("Error loading cards")
            self.status = "Error loading cards"

    def refresh_deck_list(self):
        items = [f"{getattr(c, 'id', '')} | {getattr(c, 'name', '')}" for c in self.current_deck]
        self.deck_list_ui.set_items(items)

    def _log_exc(self, prefix=None):
        if prefix:
            print(prefix, file=sys.stderr)
        traceback.print_exc()

    def pick_card_by_index(self, idx):
        # idx is index into currently shown list; map to card id then load object
        try:
            item = self.card_list.items[idx]
            card_id = item.split("|", 1)[0].strip()
            card = self.db.load_card(card_id)
            if card:
                self.selected_card_obj = card
                self.show_card_details(card)
        except Exception:
            self._log_exc("Error selecting card")
            self.status = "Error selecting card"

    def pick_deck_card_by_index(self, idx):
        try:
            card = self.current_deck[idx]
            self.selected_card_obj = card
            self.show_card_details(card)
        except Exception:
            self._log_exc("Error selecting deck card")

    def try_add_card(self, card):
        if card is None:
            return False
        if len(self.current_deck) >= MAX_DECK_CARDS:
            self.status = f"Deck full (max {MAX_DECK_CARDS})"
            return False
        self.current_deck.append(card)
        self.refresh_deck_list()
        self.status = f"Added {card.name}"
        return True

    # --- UI actions ---

    def add_to_deck(self):
        if self.selected_card_obj:
            self.try_add_card(self.selected_card_obj)
            return
        sel = self.card_list.selected
        if sel is None:
            self.status = "No card selected to add"
            return
        # load and add
        try:
            item = self.card_list.items[sel]
            card_id = item.split("|", 1)[0].strip()
            card = self.db.load_card(card_id)
            if card:
                self.selected_card_obj = card
                self.try_add_card(card)
        except Exception:
            self._log_exc("Error adding card")

    def remove_from_deck(self):
        sel = self.deck_list_ui.selected
        if sel is None:
            self.status = "No deck card selected to remove"
            return
        try:
            removed = self.current_deck.pop(sel)
            self.refresh_deck_list()
            self.status = f"Removed {removed.name}"
        except Exception:
            self._log_exc("Error removing from deck")
            self.status = "Error removing from deck"

    def show_card_details(self, card):
        # load preview
        img_path = getattr(card, "image", None)
        if img_path:
            self.load_preview(img_path)
        else:
            self.preview_surf = None
            self._preview_path = None
        # we don't need to show all textual properties on click; draw() reads selected_card_obj

    def load_preview(self, path):
        self.preview_surf = None
        self._preview_path = None
        if not path or not os.path.exists(path):
            self.status = "Preview missing"
            return
        try:
            pw, ph = PREVIEW_MAX
            if PIL_AVAILABLE:
                img = Image.open(path).convert("RGBA")
                img.thumbnail((pw, ph), Image.Resampling.LANCZOS)
                data = img.tobytes()
                surf = pygame.image.frombuffer(data, img.size, "RGBA").convert_alpha()
                self.preview_surf = surf
            else:
                surf = pygame.image.load(path).convert_alpha()
                # scale to fit
                w, h = surf.get_size()
                s = max(1, math.ceil(w / pw), math.ceil(h / ph))
                if s > 1:
                    surf = pygame.transform.smoothscale(surf, (max(1, w//s), max(1, h//s)))
                else:
                    surf = pygame.transform.smoothscale(surf, (min(pw, w), min(ph, h)))
                self.preview_surf = surf
            self._preview_path = path
            self.status = f"Previewing {Path(path).name}"
        except Exception:
            self._log_exc(f"Preview failed for {path}")
            self.preview_surf = None
            self.status = "Preview failed"

    # --- Persistence (DB) actions ---

    def save_deck(self):
        name = self.deckname_input.text.strip()
        if not name:
            self.status = "Enter a deck name first"
            return
        if not self.current_deck:
            self.status = "Cannot save empty deck"
            return
        try:
            from cards.deck import Deck
            deck_obj = Deck()
            deck_obj.name = name
            deck_obj.description = getattr(deck_obj, "description", "") or ""
            deck_obj.cards = list(self.current_deck)
            # compute power as sum if available
            try:
                deck_obj.power = sum((int(getattr(c, "power", 0) or 0) for c in deck_obj.cards))
            except Exception:
                deck_obj.power = getattr(deck_obj, "power", 0) or 0
            self.db.save_deck(deck_obj)
            self.status = f"Saved deck '{name}'"
        except Exception as e:
            self._log_exc("Error saving deck")
            self.status = f"Error saving deck: {e}"

    def load_deck(self):
        # simple selection dialog implemented inline: gather (id, name), show mini-list
        try:
            c = self.db.conn_decks.cursor()
            c.execute('SELECT id, name FROM decks ORDER BY name')
            rows = c.fetchall()
            if not rows:
                self.status = "No saved decks"
                return
            # open a simple command-line style pick: render a tiny overlay list and wait for click
            choice = self.simple_selection_dialog("Select Deck to Load", rows)
            if not choice:
                self.status = "Load cancelled"
                return
            deck_obj = self.db.load_deck(choice)
            if deck_obj is None:
                self.status = f"Failed to load deck {choice}"
                return
            self.deckname_input.text = deck_obj.name or ""
            self.current_deck = list(getattr(deck_obj, "cards", []))
            self.refresh_deck_list()
            self.status = f"Loaded deck '{deck_obj.name}'"
        except Exception:
            self._log_exc("Error loading deck")
            self.status = "Error loading deck"

    def delete_deck(self):
        try:
            name = self.deckname_input.text.strip()
            c = self.db.conn_decks.cursor()
            if name:
                c.execute('SELECT id, name FROM decks WHERE name = ? ORDER BY id', (name,))
                matches = c.fetchall()
                if not matches:
                    self.status = f"No deck named {name}"
                    return
                if len(matches) == 1:
                    deck_id = matches[0][0]
                else:
                    choice = self.simple_selection_dialog("Select Deck to Delete", matches)
                    if not choice:
                        self.status = "Delete cancelled"
                        return
                    deck_id = choice
            else:
                c.execute('SELECT id, name FROM decks ORDER BY name')
                all_decks = c.fetchall()
                if not all_decks:
                    self.status = "No decks to delete"
                    return
                choice = self.simple_selection_dialog("Select Deck to Delete", all_decks)
                if not choice:
                    self.status = "Delete cancelled"
                    return
                deck_id = choice
            # confirm
            if not self.simple_confirm_dialog("Confirm Delete", "Delete selected deck?"):
                self.status = "Delete cancelled"
                return
            self.db.delete_deck(deck_id)
            self.status = "Deck deleted"
            # clear UI if it matched loaded
            if self.deckname_input.text.strip() == name:
                self.deckname_input.text = ""
                self.current_deck = []
                self.refresh_deck_list()
        except Exception:
            self._log_exc("Error deleting deck")
            self.status = "Error deleting deck"

    # --- Small overlays / dialogs implemented in-pygame (blocking) ---

    def simple_selection_dialog(self, title, rows):
        """Rows: list of (id, name). Returns chosen id or None. Blocking but simple."""
        # generate items
        items = [f"{r[1]}  |  {r[0]}" for r in rows]
        # overlay loop
        w, h = 520, 420
        ox = (WIDTH - w) // 2
        oy = (HEIGHT - h) // 2
        sel = 0
        offset = 0
        running = True
        clock_local = pygame.time.Clock()
        while running:
            dt = clock_local.tick(60) / 1000.0
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    return None
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        return None
                    if ev.key == pygame.K_UP:
                        sel = max(0, sel - 1)
                    if ev.key == pygame.K_DOWN:
                        sel = min(len(items) - 1, sel + 1)
                    if ev.key == pygame.K_RETURN:
                        return rows[sel][0]
                if ev.type == pygame.MOUSEBUTTONDOWN:
                    if ev.button == 1:
                        mx, my = ev.pos
                        if ox <= mx <= ox + w and oy + 60 <= my <= oy + h - 60:
                            idx = int((my - (oy + 60) + offset) // 28)
                            if 0 <= idx < len(items):
                                return rows[idx][0]
                    if ev.button == 4:
                        offset = max(0, offset - 84)
                    if ev.button == 5:
                        max_off = max(0, len(items) * 28 - (h - 120))
                        offset = min(max_off, offset + 84)

            # draw overlay
            surf = screen.copy()
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            surf.blit(overlay, (0, 0))
            box = pygame.Rect(ox, oy, w, h)
            pygame.draw.rect(surf, PANEL, box, border_radius=8)
            pygame.draw.rect(surf, SUB, box, width=2, border_radius=8)
            surf.blit(TITLE_FONT.render(title, True, TEXT), (ox + 16, oy + 12))
            # list area clip
            list_rect = pygame.Rect(ox + 10, oy + 60, w - 20, h - 120)
            clip = surf.get_clip()
            surf.set_clip(list_rect)
            y = oy + 60 - offset
            for i, it in enumerate(items):
                item_rect = pygame.Rect(list_rect.x + 6, y + i * 28, list_rect.w - 12, 24)
                if i == sel:
                    pygame.draw.rect(surf, (60, 80, 90), item_rect)
                surf.blit(FONT.render(it, True, TEXT), (item_rect.x + 6, item_rect.y + 4))
            surf.set_clip(clip)
            # buttons
            ok_rect = pygame.Rect(ox + w - 220, oy + h - 48, 100, 34)
            cancel_rect = pygame.Rect(ox + w - 110, oy + h - 48, 100, 34)
            pygame.draw.rect(surf, ACCENT, ok_rect, border_radius=6)
            pygame.draw.rect(surf, PANEL, cancel_rect, border_radius=6)
            surf.blit(FONT.render("OK", True, BG), FONT.render("OK", True, BG).get_rect(center=ok_rect.center))
            surf.blit(FONT.render("Cancel", True, TEXT), FONT.render("Cancel", True, TEXT).get_rect(center=cancel_rect.center))
            screen.blit(surf, (0, 0))
            pygame.display.flip()
        return None

    def simple_confirm_dialog(self, title, message):
        w, h = 420, 160
        ox = (WIDTH - w) // 2
        oy = (HEIGHT - h) // 2
        clock_local = pygame.time.Clock()
        while True:
            dt = clock_local.tick(60) / 1000.0
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    return False
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        return False
                    if ev.key == pygame.K_RETURN:
                        return True
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    mx, my = ev.pos
                    yes_rect = pygame.Rect(ox + 60, oy + 100, 100, 36)
                    no_rect = pygame.Rect(ox + 260, oy + 100, 100, 36)
                    if yes_rect.collidepoint((mx, my)):
                        return True
                    if no_rect.collidepoint((mx, my)):
                        return False
            # draw
            surf = screen.copy()
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            surf.blit(overlay, (0, 0))
            box = pygame.Rect(ox, oy, w, h)
            pygame.draw.rect(surf, PANEL, box, border_radius=8)
            pygame.draw.rect(surf, SUB, box, width=2, border_radius=8)
            surf.blit(TITLE_FONT.render(title, True, TEXT), (ox + 16, oy + 12))
            surf.blit(FONT.render(message, True, TEXT), (ox + 20, oy + 56))
            yes_rect = pygame.Rect(ox + 60, oy + 100, 100, 36)
            no_rect = pygame.Rect(ox + 260, oy + 100, 100, 36)
            pygame.draw.rect(surf, ACCENT, yes_rect, border_radius=6)
            pygame.draw.rect(surf, PANEL, no_rect, border_radius=6)
            surf.blit(FONT.render("Yes", True, BG), FONT.render("Yes", True, BG).get_rect(center=yes_rect.center))
            surf.blit(FONT.render("No", True, TEXT), FONT.render("No", True, TEXT).get_rect(center=no_rect.center))
            screen.blit(surf, (0, 0))
            pygame.display.flip()

    # --- Main loop / rendering ---

    def handle_event(self, event):
        # global keys
        if event.type == pygame.QUIT:
            self.running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.running = False
            if event.key == pygame.K_F5:
                self.refresh_card_list()
            if event.key == pygame.K_RETURN and self.deckname_input.active:
                self.deckname_input.active = False

        # forward events to inputs & lists
        self.search_input.handle_event(event)
        self.deckname_input.handle_event(event)

        # lists handle
        self.card_list.handle_event(event, dbl_click_callback=lambda idx: self._card_double(idx),
                                   select_callback=lambda idx: self._card_select(idx))
        self.deck_list_ui.handle_event(event, dbl_click_callback=lambda idx: self._deck_double(idx),
                                       select_callback=lambda idx: self._deck_select(idx))

        # buttons
        for b in (self.btn_save, self.btn_load, self.btn_delete, self.btn_add, self.btn_remove):
            b.handle_event(event)

        # when search text changed (typing), refresh results
        if event.type == pygame.KEYDOWN:
            # crude: refresh on any typing while search active, or on backspace when active
            if self.search_input.active:
                self.refresh_card_list()

    def _card_select(self, idx):
        # show details
        self.pick_card_by_index(idx)

    def _card_double(self, idx):
        # add to deck
        try:
            item = self.card_list.items[idx]
            card_id = item.split("|", 1)[0].strip()
            card = self.db.load_card(card_id)
            if card:
                self.selected_card_obj = card
                self.try_add_card(card)
        except Exception:
            self._log_exc("Double-click add error")

    def _deck_select(self, idx):
        self.pick_deck_card_by_index(idx)

    def _deck_double(self, idx):
        try:
            removed = self.current_deck.pop(idx)
            self.refresh_deck_list()
            self.status = f"Removed {removed.name}"
        except Exception:
            self._log_exc("Double-click remove error")

    def update(self, dt):
        self.search_input.update(dt)
        self.deckname_input.update(dt)

    def draw(self):
        screen.fill(BG)
        # title
        screen.blit(TITLE_FONT.render("Deck Builder", True, TEXT), (18, 12))
        # left panel labels
        screen.blit(FONT.render("Search (type to filter):", True, TEXT), (18, 36))
        self.search_input.draw(screen)
        # left list title
        screen.blit(FONT_B.render("Available Cards", True, TEXT), (18, 96 - 28))
        self.card_list.draw(screen)

        # Add button
        mx, my = pygame.mouse.get_pos()
        for b in (self.btn_add, self.btn_remove, self.btn_save, self.btn_load, self.btn_delete):
            b.draw(screen, hover=b.rect.collidepoint((mx, my)))

        # right top: deck name and controls
        screen.blit(FONT.render("Deck Name:", True, TEXT), (410, 36))
        self.deckname_input.draw(screen)
        self.deck_list_ui.draw(screen)
        # deck top label
        screen.blit(FONT_B.render("Current Deck", True, TEXT), (410, 96 - 28))

        # card details area
        pygame.draw.rect(screen, PANEL, self.card_detail_rect, border_radius=8)
        pygame.draw.rect(screen, SUB, self.card_detail_rect, width=2, border_radius=8)
        screen.blit(FONT_B.render("Card Details", True, TEXT), (self.card_detail_rect.x + 12, self.card_detail_rect.y + 8))
        # details text from selected_card_obj
        if self.selected_card_obj:
            y = self.card_detail_rect.y + 44
            def draw_label(name, val):
                nonlocal y
                screen.blit(FONT.render(name, True, SUB), (self.card_detail_rect.x + 12, y))
                screen.blit(FONT.render(val, True, TEXT), (self.card_detail_rect.x + 120, y))
                y += 26
            c = self.selected_card_obj
            draw_label("Name:", getattr(c, "name", "N/A"))
            draw_label("Type:", str(getattr(c, "type", "N/A")))
            draw_label("Color:", str(getattr(c, "color", "N/A")))
            power_val = getattr(c, "power", None)
            try:
                pname = Power(power_val).name if power_val is not None else "N/A"
            except Exception:
                pname = str(power_val)
            draw_label("Power:", pname)
            draw_label("HP:", str(getattr(c, "hp", "N/A")))
            draw_label("DMG:", str(getattr(c, "dmg", "N/A")))
            dbuf = getattr(c, "color_buf", (0, 0))
            if isinstance(dbuf, (list, tuple)) and len(dbuf) >= 2:
                draw_label("DMG Buff:", str(dbuf[0]))
                draw_label("HP Buff:", str(dbuf[1]))
            else:
                draw_label("DMG Buff:", "0")
                draw_label("HP Buff:", "0")
            draw_label("Ability:", str(getattr(c, "ability", "N/A"))[:80])

        # preview area
        pygame.draw.rect(screen, PANEL, self.preview_rect, border_radius=8)
        pygame.draw.rect(screen, SUB, self.preview_rect, width=2, border_radius=8)
        screen.blit(FONT_B.render("Preview", True, TEXT), (self.preview_rect.x + 10, self.preview_rect.y + 6))
        if self.preview_surf:
            ps = self.preview_surf
            pw, ph = ps.get_size()
            px = self.preview_rect.x + (self.preview_rect.w - pw) // 2
            py = self.preview_rect.y + 34 + (self.preview_rect.h - 34 - ph) // 2
            screen.blit(ps, (px, py))
        else:
            # fallback text
            screen.blit(FONT.render("No Image", True, SUB), (self.preview_rect.x + 20, self.preview_rect.y + 36))
        # status bar
        pygame.draw.rect(screen, (18, 18, 18), (0, HEIGHT - 28, WIDTH, 28))
        status_txt = FONT.render(self.status, True, TEXT)
        screen.blit(status_txt, (12, HEIGHT - 24))

    def run(self):
        last = time.time()
        while self.running:
            dt = clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                self.handle_event(event)
            self.update(dt)
            self.draw()
            pygame.display.flip()
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    app = DeckBuilderPygame()
    app.run()
