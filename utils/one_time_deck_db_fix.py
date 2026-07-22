import sqlite3
from pathlib import Path

def migrate_database():
    base_dir = Path(__file__).parent.resolve()
    decks_path = base_dir / "decks.db"

    if not decks_path.exists():
        print("No existing decks.db found. Skipping migration.")
        return

    conn = sqlite3.connect(str(decks_path))
    cursor = conn.cursor()

    print("Starting migration...")

    # 1. Update decks table
    try:
        cursor.execute("ALTER TABLE decks ADD COLUMN signature TEXT")
        # Backfill existing decks: set their signature to their current unique id
        cursor.execute("UPDATE decks SET signature = id WHERE signature IS NULL")
        print("Successfully added 'signature' to 'decks' table.")
    except sqlite3.OperationalError as e:
        print(f"'decks' table check: {e}")

    # 2. Update deck_lines table
    try:
        cursor.execute("ALTER TABLE deck_lines ADD COLUMN signature TEXT")
        # Backfill existing lines: set their signature to the deck_id they are attached to
        cursor.execute("UPDATE deck_lines SET signature = deck_id WHERE signature IS NULL")
        print("Successfully added 'signature' to 'deck_lines' table.")
    except sqlite3.OperationalError as e:
        print(f"'deck_lines' table check: {e}")

    conn.commit()
    conn.close()
    print("Migration complete!")

if __name__ == "__main__":
    migrate_database()