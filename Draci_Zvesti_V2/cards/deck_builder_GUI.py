import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
import os
import math
import traceback
import sys
import logging

from cards.card_type import CardType
from cards.mana import ManaColor
from cards.card import Card
from utils.database_utils import DBUtil
from cards.power import Power
from cards.ability.abilities import Ability

# Optional Pillow import for better image preview; fall back gracefully if not available
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Pillow library not found. Image preview quality may be reduced.", file=sys.stderr)


PREVIEW_MAX_SIZE = (360, 280)  # width, height in pixels
MAX_DECK_CARDS = 12            # maximum cards allowed in a deck

# simple helper to ensure we always print exception details to the console
logging.basicConfig(level=logging.DEBUG)

def _log_exc(prefix: str | None = None):
    if prefix:
        print(prefix, file=sys.stderr)
    traceback.print_exc()

class Tooltip:
    """Simple tooltip for widgets."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _=None):
        if self.tipwindow:
            return
        x, y, _, _ = self.widget.bbox("insert") if self.widget.winfo_class() == 'Entry' else (0, 0, 0, 0)
        x = x + self.widget.winfo_rootx() + 25
        y = y + self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify=tk.LEFT, background="#ffffe0", relief=tk.SOLID, borderwidth=1, font=("tahoma", "8", "normal"))
        label.pack(ipadx=4)

    def hide(self, _=None):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None

# --- New Deck Selection Dialog ---
class DeckSelectionDialog(tk.Toplevel):
    """
    A modal dialog to select a deck.
    Accepts deck_list which can be:
      - list[str] (displayed as-is, returned result is that string)
      - list[(id, name)] tuples (display text is "name (id)" and returned result is id)
    The dialog.result will be the selected id (if tuples provided) or the string item.
    """
    def __init__(self, parent, title, deck_list):
        super().__init__(parent)
        self.transient(parent)
        self.title(title)
        self.result = None

        # Normalize deck_list and build id map
        self._id_map = {}  # index -> id_or_value
        self.listbox = tk.Listbox(self, height=12, width=48, font=(None, 10))

        for idx, item in enumerate(deck_list):
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                deck_id, deck_name = item[0], item[1]
                display = f"{deck_name}  |  {deck_id}"
                self._id_map[idx] = deck_id
            else:
                display = str(item)
                self._id_map[idx] = display
            self.listbox.insert(tk.END, display)

        self.listbox.pack(padx=10, pady=10, fill="both", expand=True)
        self.listbox.bind("<Double-Button-1>", self._on_ok)

        button_frame = ttk.Frame(self)
        button_frame.pack(padx=10, pady=(0, 10), fill="x", anchor="e")

        ok_button = ttk.Button(button_frame, text="OK", command=self._on_ok)
        ok_button.pack(side="right", padx=5)
        cancel_button = ttk.Button(button_frame, text="Cancel", command=self._on_cancel)
        cancel_button.pack(side="right")
        
        # Center the dialog
        self.update_idletasks()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        dialog_width = self.winfo_width()
        dialog_height = self.winfo_height()
        x = parent_x + (parent_width // 2) - (dialog_width // 2)
        y = parent_y + (parent_height // 2) - (dialog_height // 2)
        self.geometry(f'+{x}+{y}')
        
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.grab_set()
        self.wait_window(self)

    def _on_ok(self, event=None):
        selection = self.listbox.curselection()
        if selection:
            idx = selection[0]
            self.result = self._id_map.get(idx)
            self.destroy()
        else:
            messagebox.showwarning("Selection Required", "Please select a deck from the list.", parent=self)

    def _on_cancel(self, event=None):
        self.result = None
        self.destroy()

class DeckBuilderApp(ttk.Frame):
    def __init__(self, master=None):
        super().__init__(master, padding=12)
        self.master = master
        self.grid(sticky="nsew")
        self.master.title("Deck Builder")
        self.master.minsize(1000, 700)
        self.setup_style()
        self.create_variables()
        self.create_widgets()
        self.layout_widgets()
        self.bind_shortcuts()
        self.refresh_card_list()
        # Note: saved decks are shown via selection dialog; current deck is shown in deck_list
        self.refresh_deck_list()


    def setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except tk.TclError:
            _log_exc("Theme 'clam' not available, using default.")
        style.configure('TLabel', font=(None, 10))
        style.configure('TButton', font=(None, 10))
        style.configure('TEntry', font=(None, 10))
        style.configure('TCombobox', font=(None, 10))

    def create_variables(self):
        self.deck_name_var = tk.StringVar()
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self.current_deck = []    # list[Card]
        self.selected_card = None
        self._preview_img = None  # keep PhotoImage reference

    def create_widgets(self):
        # --- Left Frame ---
        self.left_frame = ttk.LabelFrame(self, text="Available Cards")

        # Search and filter
        self.search_frame = ttk.Frame(self.left_frame)
        self.lbl_search = ttk.Label(self.search_frame, text="Search:")
        self.ent_search = ttk.Entry(self.search_frame, textvariable=self.search_var)
        self.btn_search = ttk.Button(self.search_frame, text="Search", command=self.refresh_card_list)
        self.search_var.trace_add('write', lambda *args: self.refresh_card_list())

        # Card list
        self.card_list_frame = ttk.Frame(self.left_frame)
        self.card_list = tk.Listbox(self.card_list_frame, height=20, width=30)
        self.card_list_scroll = ttk.Scrollbar(self.card_list_frame, orient=tk.VERTICAL, command=self.card_list.yview)
        self.card_list.configure(yscrollcommand=self.card_list_scroll.set)
        self.card_list.bind('<<ListboxSelect>>', self.on_card_select)
        # Double-click on card list to add the card
        self.card_list.bind('<Double-Button-1>', self.on_card_double_click)

        # Add to deck button
        self.btn_add_to_deck = ttk.Button(self.left_frame, text="Add to Deck", command=self.add_to_deck)

        # --- Right Frame ---
        self.right_frame = ttk.LabelFrame(self, text="Deck Management")

        # Deck management
        self.deck_manage_frame = ttk.Frame(self.right_frame)
        self.lbl_deck_name = ttk.Label(self.deck_manage_frame, text="Deck Name:")
        self.ent_deck_name = ttk.Entry(self.deck_manage_frame, textvariable=self.deck_name_var, width=20)
        self.btn_save_deck = ttk.Button(self.deck_manage_frame, text="Save Deck", command=self.save_deck)
        self.btn_load_deck = ttk.Button(self.deck_manage_frame, text="Load Deck", command=self.load_deck)
        self.btn_delete_deck = ttk.Button(self.deck_manage_frame, text="Delete Deck", command=self.delete_deck)

        # Deck list
        self.deck_list_label = ttk.Label(self.right_frame, text="Current Deck:")
        self.deck_list_frame = ttk.Frame(self.right_frame)
        self.deck_list = tk.Listbox(self.deck_list_frame, height=10, width=30)
        self.deck_list_scroll = ttk.Scrollbar(self.deck_list_frame, orient=tk.VERTICAL, command=self.deck_list.yview)
        self.deck_list.configure(yscrollcommand=self.deck_list_scroll.set)
        self.deck_list.bind('<<ListboxSelect>>', self.on_deck_card_select)
        # Double-click on deck list to remove the card at that index
        self.deck_list.bind('<Double-Button-1>', self.on_deck_double_click)
        self.btn_remove_from_deck = ttk.Button(self.right_frame, text="Remove from Deck", command=self.remove_from_deck)

        # --- Card Details Frame ---
        self.details_frame = ttk.LabelFrame(self.right_frame, text="Card Details")
        
        # Detail widgets
        self.lbl_name = ttk.Label(self.details_frame, text="Name:")
        self.lbl_name_value = ttk.Label(self.details_frame, text="", wraplength=250)
        self.lbl_type = ttk.Label(self.details_frame, text="Type:")
        self.lbl_type_value = ttk.Label(self.details_frame, text="")
        self.lbl_color = ttk.Label(self.details_frame, text="Color:")
        self.lbl_color_value = ttk.Label(self.details_frame, text="")
        self.lbl_power = ttk.Label(self.details_frame, text="Power:")
        self.lbl_power_value = ttk.Label(self.details_frame, text="")
        self.lbl_hp = ttk.Label(self.details_frame, text="HP:")
        self.lbl_hp_value = ttk.Label(self.details_frame, text="")
        self.lbl_dmg = ttk.Label(self.details_frame, text="DMG:")
        self.lbl_dmg_value = ttk.Label(self.details_frame, text="")
        self.lbl_dmg_buff = ttk.Label(self.details_frame, text="DMG Buff:")
        self.lbl_dmg_buff_value = ttk.Label(self.details_frame, text="")
        self.lbl_hp_buff = ttk.Label(self.details_frame, text="HP Buff:")
        self.lbl_hp_buff_value = ttk.Label(self.details_frame, text="")
        self.lbl_ability = ttk.Label(self.details_frame, text="Ability:")
        self.lbl_ability_value = ttk.Label(self.details_frame, text="", wraplength=250)

        # Preview
        self.preview = ttk.Frame(self.details_frame, relief='groove')
        self.preview_title = ttk.Label(self.preview, text="Preview", font=(None, 12, 'bold'))
        pw, ph = PREVIEW_MAX_SIZE
        self.preview_canvas = tk.Canvas(self.preview, width=pw, height=ph, bg='#f7f7f7', highlightthickness=1, highlightbackground="#cccccc")

        # Status bar
        self.status = ttk.Label(self, textvariable=self.status_var, anchor='w')

    def layout_widgets(self):
        # Configure root window and main frame resizing
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # --- Left Frame Layout ---
        self.left_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 12), pady=5)
        self.left_frame.columnconfigure(0, weight=1)
        self.left_frame.rowconfigure(1, weight=1) # Allow card list to expand

        self.search_frame.grid(row=0, column=0, sticky='ew', pady=(0, 6), padx=5)
        self.search_frame.columnconfigure(1, weight=1) # Allow search entry to expand
        self.lbl_search.grid(row=0, column=0, sticky='w', padx=(0, 4))
        self.ent_search.grid(row=0, column=1, sticky='ew', padx=(0, 4))
        self.btn_search.grid(row=0, column=2, sticky='e')

        self.card_list_frame.grid(row=1, column=0, sticky='nsew', pady=(0, 6), padx=5)
        self.card_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.card_list_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.btn_add_to_deck.grid(row=2, column=0, sticky='ew', padx=5, pady=(0, 5))

        # --- Right Frame Layout ---
        self.right_frame.grid(row=0, column=1, sticky='nsew', pady=5)
        self.right_frame.columnconfigure(0, weight=1)
        self.right_frame.rowconfigure(2, weight=1)  # Allow Deck list to expand
        self.right_frame.rowconfigure(4, weight=2)  # Allow Card details to expand more

        # Deck management
        self.deck_manage_frame.grid(row=0, column=0, sticky='ew', pady=(5, 10), padx=5)
        self.deck_manage_frame.columnconfigure(1, weight=1) # Allow deck name entry to expand
        self.lbl_deck_name.grid(row=0, column=0, sticky='w', padx=(0, 4))
        self.ent_deck_name.grid(row=0, column=1, sticky='ew', padx=(0, 4))
        self.btn_save_deck.grid(row=0, column=2, sticky='ew', padx=(0, 4))
        self.btn_load_deck.grid(row=0, column=3, sticky='ew', padx=(0, 4))
        self.btn_delete_deck.grid(row=0, column=4, sticky='ew')

        # Deck list
        self.deck_list_label.grid(row=1, column=0, sticky='w', padx=5, pady=(5, 0))
        self.deck_list_frame.grid(row=2, column=0, sticky='nsew', pady=(0, 5), padx=5)
        self.deck_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.deck_list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.btn_remove_from_deck.grid(row=3, column=0, sticky='ew', padx=5, pady=(0, 10))

        # --- Card Details Layout ---
        self.details_frame.grid(row=4, column=0, sticky='nsew', padx=5, pady=(0, 5))

        row = 0
        details = [
            (self.lbl_name, self.lbl_name_value),
            (self.lbl_type, self.lbl_type_value),
            (self.lbl_color, self.lbl_color_value),
            (self.lbl_power, self.lbl_power_value),
            (self.lbl_hp, self.lbl_hp_value),
            (self.lbl_dmg, self.lbl_dmg_value),
            (self.lbl_dmg_buff, self.lbl_dmg_buff_value),
            (self.lbl_hp_buff, self.lbl_hp_buff_value)
        ]
        for lbl, val in details:
            lbl.grid(row=row, column=0, sticky='w', padx=4, pady=2)
            val.grid(row=row, column=1, sticky='w', padx=4, pady=2)
            row += 1

        self.lbl_ability.grid(row=row, column=0, sticky='nw', padx=4, pady=2)
        self.lbl_ability_value.grid(row=row, column=1, sticky='w', padx=4, pady=2)
        row += 1
        
        self.details_frame.columnconfigure(1, weight=1)
        self.details_frame.rowconfigure(row, weight=1) # Make the preview row expandable

        # Preview
        self.preview.grid(row=row, column=0, columnspan=2, sticky='nsew', padx=4, pady=4)
        self.preview_title.pack(anchor='nw', padx=6, pady=(6, 2))
        self.preview_canvas.pack(padx=6, pady=6, expand=True, fill='both') # Allow canvas to expand

        # Status bar
        self.status.grid(row=1, column=0, columnspan=2, sticky='we', pady=(8, 0))

    def bind_shortcuts(self):
        self.master.bind('<Control-s>', lambda e: self.save_deck())
        self.master.bind('<Control-l>', lambda e: self.load_deck())
        self.master.bind('<Delete>', lambda e: self.remove_from_deck())
        self.master.bind('<Escape>', lambda e: self.master.quit())

    def refresh_card_list(self):
        self.card_list.delete(0, tk.END)
        try:
            db_util = DBUtil()
            search_term = self.search_var.get().lower()
            cards = db_util.get_all_cards()
            for card in cards:
                if search_term in card.name.lower() or search_term in card.id.lower():
                    self.card_list.insert(tk.END, f"{card.id} | {card.name}")
        except Exception as e:
            _log_exc("Error loading cards:")
            self.status_var.set("Error loading cards")

    def refresh_deck_list(self):
        # refresh the *current deck* display (cards in current_deck)
        self.deck_list.delete(0, tk.END)
        for card in self.current_deck:
            self.deck_list.insert(tk.END, f"{card.id} | {card.name}")

    def on_card_select(self, event):
        selection = self.card_list.curselection()
        if not selection:
            return
        selected_text = self.card_list.get(selection[0])
        card_id = selected_text.split('|', 1)[0].strip()
        try:
            db_util = DBUtil()
            card = db_util.load_card(card_id)
            if card:
                self.selected_card = card
                self.show_card_details(card)
        except Exception as e:
            _log_exc("Error loading card details:")
            self.status_var.set("Error loading card details")

    def on_card_double_click(self, event):
        """Double-click in available cards -> add that card to current deck (if under limit)."""
        selection = self.card_list.curselection()
        if not selection:
            return
        selected_text = self.card_list.get(selection[0])
        card_id = selected_text.split('|', 1)[0].strip()
        try:
            db_util = DBUtil()
            card = db_util.load_card(card_id)
            if card:
                # show details and then attempt to add
                self.selected_card = card
                self.show_card_details(card)
                self.try_add_card(card)
        except Exception:
            _log_exc("Error adding card on double-click:")

    def on_deck_card_select(self, event):
        selection = self.deck_list.curselection()
        if not selection:
            return
        selected_text = self.deck_list.get(selection[0])
        card_id = selected_text.split('|', 1)[0].strip()
        for card in self.current_deck:
            if card.id == card_id:
                self.show_card_details(card)
                break

    def on_deck_double_click(self, event):
        """Double-click in deck list -> remove the clicked card from current deck."""
        selection = self.deck_list.curselection()
        if not selection:
            return
        idx = selection[0]
        try:
            removed_card = self.current_deck.pop(idx)
            self.refresh_deck_list()
            self.status_var.set(f"Removed {removed_card.name} from deck (double-click)")
        except Exception:
            _log_exc("Error removing card on double-click:")

    def show_card_details(self, card):
        self.lbl_name_value.config(text=card.name)
        self.lbl_type_value.config(text=getattr(card, 'type', 'N/A'))
        self.lbl_color_value.config(text=getattr(card, 'color', 'N/A'))

        power_value = getattr(card, 'power', None)
        power_name = "N/A"
        if power_value is not None:
            try:
                power_name = Power(power_value).name
            except (ValueError, TypeError):
                power_name = str(power_value)
        self.lbl_power_value.config(text=power_name)

        self.lbl_ability_value.config(text=str(getattr(card, 'ability', 'N/A')))
        self.lbl_hp_value.config(text=str(getattr(card, 'hp', 'N/A')))
        self.lbl_dmg_value.config(text=str(getattr(card, 'dmg', 'N/A')))

        color_buf = getattr(card, 'color_buf', (0, 0))
        if isinstance(color_buf, (list, tuple)) and len(color_buf) >= 2:
            self.lbl_dmg_buff_value.config(text=str(color_buf[0]))
            self.lbl_hp_buff_value.config(text=str(color_buf[1]))
        else:
            self.lbl_dmg_buff_value.config(text="0")
            self.lbl_hp_buff_value.config(text="0")

        img_path = getattr(card, 'image', None)
        if img_path:
            self.show_preview(img_path)
        else:
            self.clear_preview()

    def clear_preview(self):
        self.preview_canvas.delete('all')
        pw, ph = PREVIEW_MAX_SIZE
        self.preview_canvas.create_text(pw/2, ph/2, text='No Image', fill='#666666', font=(None, 11))
        self._preview_img = None
        self.status_var.set('')

    def show_preview(self, path):
        self.preview_canvas.delete('all')
        if not path:
            self.clear_preview()
            return
        
        pw, ph = PREVIEW_MAX_SIZE
        try:
            if PIL_AVAILABLE:
                with Image.open(path) as img:
                    # Updated to use modern constant
                    img.thumbnail((pw, ph), Image.Resampling.LANCZOS)
                    self._preview_img = ImageTk.PhotoImage(img)
                    self.preview_canvas.create_image(pw/2, ph/2, image=self._preview_img, anchor='center')
                self.status_var.set(f"Previewing: {Path(path).name}")
            else:
                photo = tk.PhotoImage(file=path)
                w, h = photo.width(), photo.height()
                s = max(1, math.ceil(w / pw), math.ceil(h / ph))
                if s > 1:
                    photo = photo.subsample(s, s)
                self._preview_img = photo
                self.preview_canvas.create_image(pw/2, ph/2, image=self._preview_img, anchor='center')
                self.status_var.set(f"Previewing: {Path(path).name} (no Pillow)")
        except Exception:
            _log_exc(f"Preview failed for image: {path}")
            self.clear_preview()
            self.status_var.set("Preview failed for selected image")

    def try_add_card(self, card: Card):
        """Centralized logic to attempt to add a Card to current_deck respecting the MAX_DECK_CARDS limit."""
        if card is None:
            return False
        if len(self.current_deck) >= MAX_DECK_CARDS:
            messagebox.showwarning('Deck Full', f'Cannot add more than {MAX_DECK_CARDS} cards to a deck.')
            return False
        # Add card (allow duplicates) and refresh UI
        self.current_deck.append(card)
        self.refresh_deck_list()
        self.status_var.set(f"Added {card.name} to deck")
        return True

    def add_to_deck(self):
        # Use selected_card if present, otherwise try to get selection from listbox
        if self.selected_card:
            self.try_add_card(self.selected_card)
            return

        selection = self.card_list.curselection()
        if not selection:
            messagebox.showwarning('Select', 'Please select a card to add to the deck.')
            return
        selected_text = self.card_list.get(selection[0])
        card_id = selected_text.split('|', 1)[0].strip()
        try:
            db_util = DBUtil()
            card = db_util.load_card(card_id)
            if card:
                self.selected_card = card
                self.show_card_details(card)
                self.try_add_card(card)
        except Exception:
            _log_exc("Error adding card:")

    def remove_from_deck(self):
        selection = self.deck_list.curselection()
        if not selection:
            messagebox.showwarning('Select', 'Please select a card to remove from the deck.')
            return
            
        # Remove from list based on selection index, safer for duplicate cards
        removed_card = self.current_deck.pop(selection[0])
        self.refresh_deck_list()
        self.status_var.set(f"Removed {removed_card.name} from deck")

    def save_deck(self):
        deck_name = self.deck_name_var.get().strip()
        if not deck_name:
            messagebox.showwarning('Deck Name', 'Please enter a deck name.')
            return
        if not self.current_deck:
            messagebox.showwarning('Empty Deck', 'Cannot save an empty deck.')
            return
        try:
            # Build a Deck object and pass to DBUtil().save_deck
            from cards.deck import Deck
            deck_obj = Deck()
            # leave deck_obj.id unset so DB can generate id if needed
            deck_obj.name = deck_name
            deck_obj.description = getattr(deck_obj, "description", "") or ""
            # copy card objects so DBUtil can extract ids from deck.cards
            deck_obj.cards = list(self.current_deck)
            # optional: compute power as sum of card.power (if numeric)
            try:
                deck_obj.power = sum((int(getattr(c, "power", 0) or 0) for c in deck_obj.cards))
            except Exception:
                deck_obj.power = getattr(deck_obj, "power", 0) or 0

            DBUtil().save_deck(deck_obj)
            self.status_var.set(f"Deck '{deck_name}' saved successfully")
            messagebox.showinfo('Success', f"Deck '{deck_name}' saved successfully")
        except Exception as e:
            _log_exc("Error saving deck:")
            messagebox.showerror('Error', f'Failed to save deck: {e}')

    # --- Modified load_deck function ---
    def load_deck(self):
        try:
            db_util = DBUtil()
            # Fetch all decks as (id, name) pairs for accurate selection
            c = db_util.conn_decks.cursor()
            c.execute('SELECT id, name FROM decks ORDER BY name')
            rows = c.fetchall()
            if not rows:
                messagebox.showinfo('No Decks Found', 'There are no saved decks in the database.')
                return

            # rows is list of (id, name)
            dialog = DeckSelectionDialog(self, "Select a Deck", rows)
            deck_id = dialog.result

            if not deck_id:  # User cancelled or closed the dialog
                self.status_var.set("Load deck operation cancelled.")
                return

            # Load Deck instance from DBUtil
            deck_obj = db_util.load_deck(deck_id)
            if deck_obj is None:
                messagebox.showerror('Error', f"Failed to load deck with id '{deck_id}'.")
                return

            # Set UI state from loaded Deck
            self.deck_name_var.set(deck_obj.name or "")
            # deck_obj.cards is expected to be list[Card] (DBUtil.load_deck uses load_card)
            self.current_deck = list(getattr(deck_obj, "cards", []))
            self.refresh_deck_list()
            self.status_var.set(f"Deck '{deck_obj.name}' loaded successfully")

        except Exception as e:
            _log_exc("Error loading deck:")
            messagebox.showerror('Error', f'Failed to load deck: {e}')

    def delete_deck(self):
        try:
            db_util = DBUtil()
            deck_name = self.deck_name_var.get().strip()

            # If a name is provided, look up matching deck ids
            c = db_util.conn_decks.cursor()
            if deck_name:
                c.execute('SELECT id, name FROM decks WHERE name = ? ORDER BY id', (deck_name,))
                matches = c.fetchall()
                if not matches:
                    messagebox.showwarning('Not Found', f"No deck with name '{deck_name}' found.")
                    return
                # If multiple matches, let user choose; otherwise pick single
                if len(matches) == 1:
                    deck_id = matches[0][0]
                else:
                    dialog = DeckSelectionDialog(self, "Select Deck to Delete", matches)
                    deck_id = dialog.result
                    if not deck_id:
                        self.status_var.set("Delete deck operation cancelled.")
                        return
            else:
                # no name given -> let user pick from all decks
                c.execute('SELECT id, name FROM decks ORDER BY name')
                all_decks = c.fetchall()
                if not all_decks:
                    messagebox.showinfo('No Decks', 'No saved decks to delete.')
                    return
                dialog = DeckSelectionDialog(self, "Select Deck to Delete", all_decks)
                deck_id = dialog.result
                if not deck_id:
                    self.status_var.set("Delete deck operation cancelled.")
                    return

            # confirm deletion
            if not messagebox.askyesno('Confirm Delete', f"Are you sure you want to delete the selected deck?"):
                return

            db_util.delete_deck(deck_id)
            self.status_var.set(f"Deck deleted successfully")
            messagebox.showinfo('Success', f"Deck deleted successfully")
            # Clear UI if it was the loaded deck
            if self.deck_name_var.get().strip() == deck_name:
                self.deck_name_var.set("")
                self.current_deck = []
                self.refresh_deck_list()

        except Exception as e:
            _log_exc("Error deleting deck:")
            messagebox.showerror('Error', f'Failed to delete deck: {e}')

if __name__ == '__main__':
    root = tk.Tk()
    app = DeckBuilderApp(master=root)
    root.mainloop()
