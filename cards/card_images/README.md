# Localized card faces

Card image paths stored in the databases are language-neutral. Runtime loading
adds a language suffix:

- `Card_cs.png` — Czech card face
- `Card_en.png` — English card face

Unsuffixed images are supported only as a migration fallback and are treated as
Czech. Run the deterministic generator from the repository root after adding or
changing a card face:

```bash
.zvesti_venv/bin/python cards/build_localized_card_images.py --overwrite
```

Legendary (`Power.LEGENDARY`) nameplates are preserved exactly. Their rules text
is still localized. The generator also includes finished legendary faces that
are not registered in `cards.db` yet.
