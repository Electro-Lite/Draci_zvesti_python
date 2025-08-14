import tkinter as tk
from tkinter import messagebox

from .card import Card
from .database_utils import DBUtil  # Adjust if the function/class name differs

def save_card():
    try:
        # Create Card instance using user input
        card = Card(
            name=entry_name.get(),
            type=entry_type.get(),
            mana_cost=entry_mana.get(),
            power=entry_power.get(),
            ability=entry_ability.get()
        )
        # If Card class has validation, let it raise exceptions or handle errors
        DBUtil.save_card(card)
        messagebox.showinfo("Success", "Card saved!")
        entry_name.delete(0, tk.END)
        entry_type.delete(0, tk.END)
        entry_mana.delete(0, tk.END)
        entry_power.delete(0, tk.END)
        entry_ability.delete(0, tk.END)
    except Exception as e:
        messagebox.showerror("Error", str(e))

root = tk.Tk()
root.title("Card Builder")

tk.Label(root, text="Name:").grid(row=0, column=0, sticky="e")
entry_name = tk.Entry(root)
entry_name.grid(row=0, column=1)

tk.Label(root, text="Type:").grid(row=1, column=0, sticky="e")
entry_type = tk.Entry(root)
entry_type.grid(row=1, column=1)

tk.Label(root, text="Mana Cost:").grid(row=2, column=0, sticky="e")
entry_mana = tk.Entry(root)
entry_mana.grid(row=2, column=1)

tk.Label(root, text="Power:").grid(row=3, column=0, sticky="e")
entry_power = tk.Entry(root)
entry_power.grid(row=3, column=1)

tk.Label(root, text="Ability:").grid(row=4, column=0, sticky="e")
entry_ability = tk.Entry(root)
entry_ability.grid(row=4, column=1)

tk.Button(root, text="Save Card", command=save_card).grid(row=5, column=0, columnspan=2, pady=10)

root.mainloop()
