import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
import os
import math
import traceback
import sys
import logging

from cards.card_type            import CardType
from cards.mana                 import ManaColor
from cards.card                 import Card
from utils.database_utils       import DBUtil
from cards.power                import Power
from cards.ability.abilities    import Ability
#TODO image path is stored absolute -> If folder placement changes (someone download the git repo and runs), The images will fail to load.


# Optional Pillow import for better image preview; fall back gracefully if not available
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except Exception as e:
    PIL_AVAILABLE = False
    print("Pillow import failed:", file=sys.stderr)
    traceback.print_exc()

PREVIEW_MAX_SIZE = (360, 280)  # width, height in pixels

# simple helper to ensure we always print exception details to the console
logging.basicConfig(level=logging.DEBUG)

def _log_exc(prefix: str | None = None):
    if prefix:
        print(prefix, file=sys.stderr)
    traceback.print_exc()


def find_ability_class(class_name_str):
    """Return an instance of the Ability subclass matching class_name_str or None."""
    for subclass in Ability.__subclasses__():
        if subclass.__name__ == class_name_str:
            try:
                return subclass()
            except Exception:
                _log_exc(f"find_ability_class: failed to instantiate {subclass.__name__}:")
                return None
    return None


def only_int(v):
    return v.isdigit() or v == ""


def power_name_from_value(val):
    for p in Power:
        try:
            if p.value == val:
                return p.name
        except Exception:
            continue
    return Power.STARTER.name


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
        x, y, cx, cy = self.widget.bbox("insert") if self.widget.winfo_class() == 'Entry' else (0, 0, 0, 0)
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


class CardBuilderApp(ttk.Frame):
    def __init__(self, master=None):
        super().__init__(master, padding=12)
        self.master = master
        self.grid(sticky="nsew")
        self.master.title("Card Builder — Improved UI")
        self.master.minsize(720, 420)
        self.setup_style()
        self.create_variables()
        self.create_widgets()
        self.layout_widgets()
        self.bind_shortcuts()
        self.refresh_ui_by_type()

    def setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except Exception:
            _log_exc("Theme load failed:")
        style.configure('TLabel', font=(None, 10))
        style.configure('TButton', font=(None, 10))
        style.configure('TEntry', font=(None, 10))
        style.configure('TCombobox', font=(None, 10))

    def create_variables(self):
        self.name_var = tk.StringVar()
        self.type_var = tk.StringVar(value=CardType.PLAYER.name)
        self.color_var = tk.StringVar(value=ManaColor.RED.name)
        self.power_var = tk.StringVar(value=Power.STARTER.name)
        self.ability_var = tk.StringVar()
        self.hp_var = tk.StringVar()
        self.dmg_var = tk.StringVar()
        self.buff_hp_var = tk.StringVar()
        self.buff_dmg_var = tk.StringVar()
        self.image_var = tk.StringVar()
        self.loaded_card_id = None
        self.status_var = tk.StringVar(value="Ready")

    def create_widgets(self):
        self.form = ttk.Frame(self)
        self.lbl_name = ttk.Label(self.form, text="Name")
        self.ent_name = ttk.Entry(self.form, textvariable=self.name_var)
        Tooltip(self.ent_name, "Card display name")

        self.lbl_type = ttk.Label(self.form, text="Type")
        self.cmb_type = ttk.Combobox(self.form, textvariable=self.type_var, state='readonly', width=18)
        self.cmb_type['values'] = [CardType.PLAYER.name, CardType.DRAGON.name]
        self.cmb_type.bind('<<ComboboxSelected>>', lambda e: self.refresh_ui_by_type())

        self.lbl_color = ttk.Label(self.form, text="Color")
        self.cmb_color = ttk.Combobox(self.form, textvariable=self.color_var, state='readonly', width=18)
        self.cmb_color['values'] = [c.name for c in [ManaColor.RED, ManaColor.BLACK, ManaColor.BLUE, ManaColor.GREEN]]

        self.lbl_power = ttk.Label(self.form, text="Power")
        self.cmb_power = ttk.Combobox(self.form, textvariable=self.power_var, state='readonly', width=18)
        self.cmb_power['values'] = [p.name for p in Power]

        self.lbl_ability = ttk.Label(self.form, text="Ability")
        self.cmb_ability = ttk.Combobox(self.form, textvariable=self.ability_var, state='readonly', width=18)
        self.ability_names = [cls.__name__ for cls in Ability.__subclasses__()]
        if not self.ability_names:
            self.ability_names = ["NoAbilitiesFound"]
        self.cmb_ability['values'] = self.ability_names
        self.ability_var.set(self.ability_names[0])

        vcmd = (self.register(only_int), '%P')
        self.lbl_hp = ttk.Label(self.form, text="HP")
        self.ent_hp = ttk.Entry(self.form, textvariable=self.hp_var, validate='key', validatecommand=vcmd)
        Tooltip(self.ent_hp, "Health points (integer)")

        self.lbl_dmg = ttk.Label(self.form, text="DMG")
        self.ent_dmg = ttk.Entry(self.form, textvariable=self.dmg_var, validate='key', validatecommand=vcmd)
        Tooltip(self.ent_dmg, "Damage (integer)")

        self.lbl_buff_hp = ttk.Label(self.form, text="Buff HP")
        self.ent_buff_hp = ttk.Entry(self.form, textvariable=self.buff_hp_var, validate='key', validatecommand=vcmd)

        self.lbl_buff_dmg = ttk.Label(self.form, text="Buff DMG")
        self.ent_buff_dmg = ttk.Entry(self.form, textvariable=self.buff_dmg_var, validate='key', validatecommand=vcmd)

        # Image selection restricted to card_images folder
        self.lbl_image = ttk.Label(self.form, text="Image")
        self.btn_browse = ttk.Button(self.form, text="Browse…", command=self.browse_image)

        self.btn_save = ttk.Button(self.form, text="Save Card", command=self.save_card)
        self.btn_reset = ttk.Button(self.form, text="Reset", command=self.reset_form)
        self.btn_load = ttk.Button(self.form, text="Load Card…", command=self.open_load_dialog)

        # Preview: switch to a Canvas for pixel-accurate sizing & centering
        self.preview = ttk.Frame(self, relief='groove')
        self.preview_title = ttk.Label(self.preview, text="Preview", font=(None, 12, 'bold'))
        pw, ph = PREVIEW_MAX_SIZE
        self.preview_canvas = tk.Canvas(self.preview, width=pw, height=ph, bg='#f7f7f7', highlightthickness=1, highlightbackground="#cccccc")
        self._preview_img = None  # keep PhotoImage reference
        self.status = ttk.Label(self, textvariable=self.status_var, anchor='w')

    def layout_widgets(self):
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)
        self.rowconfigure(0, weight=1)

        self.form.grid(row=0, column=0, sticky='nsew')
        self.preview.grid(row=0, column=1, sticky='ns', padx=(12, 0))

        pad_opts = {'padx': 4, 'pady': 6}
        r = 0
        self.lbl_name.grid(row=r, column=0, sticky='e', **pad_opts)
        self.ent_name.grid(row=r, column=1, sticky='we', **pad_opts)
        r += 1
        self.lbl_type.grid(row=r, column=0, sticky='e', **pad_opts)
        self.cmb_type.grid(row=r, column=1, sticky='w', **pad_opts)
        r += 1
        self.lbl_color.grid(row=r, column=0, sticky='e', **pad_opts)
        self.cmb_color.grid(row=r, column=1, sticky='w', **pad_opts)
        r += 1
        self.lbl_power.grid(row=r, column=0, sticky='e', **pad_opts)
        self.cmb_power.grid(row=r, column=1, sticky='w', **pad_opts)
        r += 1
        self.lbl_ability.grid(row=r, column=0, sticky='e', **pad_opts)
        self.cmb_ability.grid(row=r, column=1, sticky='we', **pad_opts)
        r += 1
        self.lbl_hp.grid(row=r, column=0, sticky='e', **pad_opts)
        self.ent_hp.grid(row=r, column=1, sticky='w', **pad_opts)
        r += 1
        self.lbl_dmg.grid(row=r, column=0, sticky='e', **pad_opts)
        self.ent_dmg.grid(row=r, column=1, sticky='w', **pad_opts)
        r += 1
        self.lbl_buff_hp.grid(row=r, column=0, sticky='e', **pad_opts)
        self.ent_buff_hp.grid(row=r, column=1, sticky='w', **pad_opts)
        r += 1
        self.lbl_buff_dmg.grid(row=r, column=0, sticky='e', **pad_opts)
        self.ent_buff_dmg.grid(row=r, column=1, sticky='w', **pad_opts)
        r += 1
        self.lbl_image.grid(row=r, column=0, sticky='e', **pad_opts)
        self.btn_browse.grid(row=r, column=1, sticky='w', padx=4, pady=(6, 0))
        r += 1
        self.btn_save.grid(row=r, column=0, sticky='we', pady=(12, 0), padx=4)
        self.btn_load.grid(row=r, column=1, sticky='we', pady=(12, 0), padx=4)
        r += 1
        self.btn_reset.grid(row=r, column=0, columnspan=2, sticky='we', pady=(8, 0), padx=4)

        self.preview_title.pack(anchor='nw', padx=6, pady=(6, 2))
        self.preview_canvas.pack(padx=6, pady=6)

        self.status.grid(row=2, column=0, columnspan=2, sticky='we', pady=(8, 0))

    def bind_shortcuts(self):
        self.master.bind('<Return>', lambda e: self.save_card())
        self.master.bind('<Control-n>', lambda e: self.reset_form())
        self.master.bind('<Escape>', lambda e: self.master.quit())

    def refresh_ui_by_type(self):
        t = self.type_var.get()
        if t == CardType.DRAGON.name:
            self.lbl_buff_hp.grid_remove()
            self.ent_buff_hp.grid_remove()
            self.lbl_buff_dmg.grid_remove()
            self.ent_buff_dmg.grid_remove()
            self.clear_preview()
        else:
            self.lbl_buff_hp.grid()
            self.ent_buff_hp.grid()
            self.lbl_buff_dmg.grid()
            self.ent_buff_dmg.grid()
        self.show_preview(self.image_var.get())

    def browse_image(self):
        try:
            cur_dir = Path(__file__).parent
        except Exception:
            cur_dir = Path(os.getcwd())
            _log_exc("Could not determine __file__ parent, using cwd:")

        image_dir = cur_dir / 'card_images'
        # ensure the folder exists so initialdir is valid
        if not image_dir.exists():
            messagebox.showwarning('Images folder', f'No card_images folder found at: {image_dir}')
            return

        file = filedialog.askopenfilename(initialdir=image_dir, title='Select card image', filetypes=[('Images', '*.png;*.jpg;*.jpeg')])
        if not file:
            return

        # Ensure selected file is inside image_dir to enforce restriction
        try:
            file_path = Path(file).resolve()
            if image_dir.resolve() not in file_path.parents and image_dir.resolve() != file_path.parent:
                messagebox.showerror('Invalid selection', 'Please select an image from the card_images directory.')
                return
        except Exception:
            _log_exc("Error validating selected image path:")

        self.image_var.set(str(file_path))
        self.show_preview(str(file_path))

    def clear_preview(self):
        self.preview_canvas.delete('all')
        pw, ph = PREVIEW_MAX_SIZE
        # draw placeholder text centered
        self.preview_canvas.create_text(pw/2, ph/2, text='No image', fill='#666666', font=(None, 11))
        self._preview_img = None
        self.status_var.set('')

    def show_preview(self, path):
        pw, ph = PREVIEW_MAX_SIZE
        self.preview_canvas.delete('all')
        if not path:
            self.clear_preview()
            return
        try:
            if PIL_AVAILABLE:
                img = Image.open(path)
                # Use a high-quality resample if available
                img.thumbnail((pw, ph), Image.LANCZOS if hasattr(Image, 'LANCZOS') else Image.ANTIALIAS)
                self._preview_img = ImageTk.PhotoImage(img)
                # center the image
                self.preview_canvas.create_image(pw/2, ph/2, image=self._preview_img, anchor='center')
                self.status_var.set(f"Previewing: {Path(path).name}")
            else:
                # Fallback: try tk.PhotoImage (may fail for JPG)
                photo = tk.PhotoImage(file=path)
                # If image larger than preview, subsample integer-wise
                w = photo.width()
                h = photo.height()
                sx = max(1, math.ceil(w / pw))
                sy = max(1, math.ceil(h / ph))
                s = max(sx, sy)
                if s > 1:
                    try:
                        photo = photo.subsample(s, s)
                    except Exception:
                        _log_exc("Subsample failed on PhotoImage:")
                self._preview_img = photo
                self.preview_canvas.create_image(pw/2, ph/2, image=self._preview_img, anchor='center')
                self.status_var.set(f"Previewing: {Path(path).name} (no Pillow)")
        except Exception:
            _log_exc("Preview failed for selected image:")
            self.clear_preview()
            self.status_var.set("Preview failed for selected image")

    def open_load_dialog(self):
        # Create a modal dialog to choose card to load
        dlg = tk.Toplevel(self.master)
        dlg.title('Load Card')
        dlg.transient(self.master)
        dlg.grab_set()
        dlg.geometry('520x360')

        lbl = ttk.Label(dlg, text='Select a card to load:')
        lbl.pack(padx=8, pady=(8, 4))

        frame = ttk.Frame(dlg)
        frame.pack(fill='both', expand=True, padx=8, pady=4)

        search_var = tk.StringVar()
        ent_search = ttk.Entry(frame, textvariable=search_var)
        ent_search.pack(fill='x', pady=(0, 6))

        listbox = tk.Listbox(frame)
        listbox.pack(fill='both', expand=True)

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill='x', pady=6, padx=8)
        btn_delete = ttk.Button(btn_frame, text='Delete', command=lambda: self._delete_selected_from_listbox(listbox))
        btn_load = ttk.Button(btn_frame, text='Load', command=lambda: self._load_selected_from_listbox(listbox, dlg))
        btn_cancel = ttk.Button(btn_frame, text='Cancel', command=dlg.destroy)
        btn_delete.pack(side='left')
        btn_cancel.pack(side='right', padx=(0, 8))
        btn_load.pack(side='right')

        def on_search(*args):
            q = search_var.get().lower()
            listbox.delete(0, tk.END)
            try:
                cur = DBUtil().conn_cards.cursor()
                cur.execute('SELECT id, name FROM cards ORDER BY name')
                rows = cur.fetchall()
                for r in rows:
                    if not q or q in (r[0] or '').lower() or q in (r[1] or '').lower():
                        listbox.insert(tk.END, f"{r[0]} | {r[1]}")
                if not rows:
                    listbox.insert(tk.END, 'No cards found')
            except Exception:
                _log_exc("DB read failed in open_load_dialog on_search:")
                listbox.insert(tk.END, 'Error reading DB')

        search_var.trace_add('write', lambda *_: on_search())
        listbox.bind('<Double-Button-1>', lambda e: self._load_selected_from_listbox(listbox, dlg))

        # initial populate
        on_search()

    def _load_selected_from_listbox(self, listbox, dlg):
        sel = listbox.curselection()
        if not sel:
            messagebox.showwarning('Select', 'Please select a card to load.')
            return
        text = listbox.get(sel[0])
        if text.startswith('No cards') or text.startswith('Error'):
            return
        card_id = text.split('|', 1)[0].strip()
        dlg.destroy()
        self.load_card_by_id(card_id)

    def _delete_selected_from_listbox(self, listbox):
        sel = listbox.curselection()
        if not sel:
            messagebox.showwarning('Select', 'Please select a card to delete.')
            return
        text = listbox.get(sel[0])
        if text.startswith('No cards') or text.startswith('Error'):
            return
        card_id = text.split('|', 1)[0].strip()
        if not messagebox.askyesno('Confirm delete', f'Are you sure you want to delete {card_id}?'):
            return
        try:
            DBUtil().delete_card(card_id)
            messagebox.showinfo('Deleted', f'Card {card_id} deleted.')
            # if this card was loaded into the form, clear
            if self.loaded_card_id == card_id:
                self.reset_form()
            # refresh listbox contents
            listbox.delete(0, tk.END)
            try:
                cur = DBUtil().conn_cards.cursor()
                cur.execute('SELECT id, name FROM cards ORDER BY name')
                rows = cur.fetchall()
                for r in rows:
                    listbox.insert(tk.END, f"{r[0]} | {r[1]}")
                if not rows:
                    listbox.insert(tk.END, 'No cards found')
            except Exception:
                _log_exc("DB read failed while refreshing listbox after delete:")
                listbox.insert(tk.END, 'Error reading DB')
        except Exception as e:
            _log_exc("Delete failed:")
            messagebox.showerror('Delete failed', str(e))

    def load_card_by_id(self, card_id):
        try:
            c = DBUtil().load_card(card_id)
            if not c:
                messagebox.showerror('Not found', f'Card {card_id} not found')
                return
            # populate UI fields
            self.loaded_card_id = c.id
            self.name_var.set(c.name        or '')
            self.power_var.set(c.power.name or Power.STARTER.name)
            self.type_var.set(c.type.name   or CardType.PLAYER.name)
            self.color_var.set(c.color      or ManaColor.BLUE.name)

            # ability: DB stores string; try to make instance and set name
            ability_val = getattr(c, 'ability', None)
            ability_name = None
            if isinstance(ability_val, str):
                # try class name match
                ability_name = ability_val
                # if ability_val is repr like "<SomeAbility ...>" this won't match; try scanning for name in self.ability_names:
                for name in self.ability_names:
                    if name in ability_val:
                        ability_name = name
                        break
            elif ability_val is not None:
                ability_name = ability_val.__class__.__name__

            if ability_name and ability_name in self.ability_names:
                self.ability_var.set(ability_name)
            else:
                self.ability_var.set(self.ability_names[0])

            self.hp_var.set(        str(getattr(c, 'hp', '')            or ''))
            self.dmg_var.set(       str(getattr(c, 'dmg', '')           or ''))
            self.buff_dmg_var.set(  str(getattr(c, 'color_buf', '')[0]  or ''))
            self.buff_hp_var.set(   str(getattr(c, 'color_buf', '')[1]  or ''))

            # image
            img = getattr(c, 'image', None)
            if img:
                self.image_var.set(img)
                self.show_preview(img)
            else:
                self.image_var.set('')
                self.clear_preview()

            self.status_var.set(f'Loaded: {c.id}')
        except Exception:
            _log_exc("Load failed:")
            messagebox.showerror('Load failed', 'An error occurred while loading the card. See console for details.')
            self.status_var.set('Load failed')

    def validate_form(self):
        if not self.name_var.get().strip():
            return False, 'Name is required.'
        if self.ability_var.get() not in self.ability_names:
            return False, 'Selected ability is invalid.'
        for var, label in [(self.hp_var, 'HP'), (self.dmg_var, 'DMG'), (self.buff_hp_var, 'Buff HP'), (self.buff_dmg_var, 'Buff DMG')]:
            if var.get() and not var.get().isdigit():
                return False, f'{label} must be an integer.'
        return True, ''

    def save_card(self):
        ok, msg = self.validate_form()
        if not ok:
            messagebox.showerror('Validation error', msg)
            return
        try:
            ability_inst = find_ability_class(self.ability_var.get())
            if ability_inst is None:
                raise ValueError('Could not instantiate ability')

            card = Card(
                name        = self.name_var.get().strip(),
                power       = Power[self.power_var.get()].value,
                color       = self.color_var.get(),
                type        = self.type_var.get(),
                ability     = ability_inst,
                hp          = int(self.hp_var.get()) if self.hp_var.get() else 0,
                dmg         = int(self.dmg_var.get()) if self.dmg_var.get() else 0,
                color_buf   = [int(self.buff_hp_var.get()) if self.buff_hp_var.get() else 0, int(self.buff_dmg_var.get()) if self.buff_dmg_var.get() else 0],
                image       = self.image_var.get() if self.image_var.get() else None,
            )

            # preserve loaded id/owner if editing
            if self.loaded_card_id:
                try:
                    card.id = self.loaded_card_id
                except Exception:
                    _log_exc("Failed to preserve loaded_card_id:")

            DBUtil().save_card(card)
            messagebox.showinfo('Success', f'Card "{card.name}" saved.')
            self.status_var.set(f'Saved: {card.name}')
            self.reset_form()
        except Exception:
            _log_exc("Save failed:")
            messagebox.showerror('Save failed', 'An error occurred while saving the card. See console for details.')
            self.status_var.set('Save failed')

    def reset_form(self):
        self.name_var.set('')
        self.type_var.set(CardType.PLAYER.name)
        self.color_var.set(ManaColor.RED.name)
        self.power_var.set(Power.STARTER.name)
        self.ability_var.set(self.ability_names[0])
        self.hp_var.set('')
        self.dmg_var.set('')
        self.buff_hp_var.set('')
        self.buff_dmg_var.set('')
        self.image_var.set('')
        self.loaded_card_id = None
        self.refresh_ui_by_type()
        self.status_var.set('Ready')


if __name__ == '__main__':
    root = tk.Tk()
    app = CardBuilderApp(master=root)
    root.mainloop()
