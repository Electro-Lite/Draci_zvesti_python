import sqlite3

def fix_image_paths(db_path="cards.db"):
    # Connect to the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Fetch all cards that have an image path saved
    cursor.execute("SELECT id, image FROM cards WHERE image IS NOT NULL")
    rows = cursor.fetchall()

    updated_count = 0

    for card_id, image_path in rows:
        if not image_path:
            continue

        # 1. Convert Windows backslashes to forward slashes
        new_path = image_path.replace("\\", "/")

        # 2. Strip out the absolute Windows path. 
        # Based on your error, we want everything starting from "cards/"
        target_dir = "cards/card_images/"
        
        if target_dir in new_path:
            # Keep only the relative portion: 'cards/card_images/Filename.png'
            new_path = new_path[new_path.find(target_dir):]
        else:
            # Fallback: if the path structure is different, just grab the filename
            # and prepend the expected relative directory.
            filename = new_path.split("/")[-1]
            new_path = f"cards/card_images/{filename}"

        # 3. Update the database if the path needed changing
        if new_path != image_path:
            cursor.execute("UPDATE cards SET image = ? WHERE id = ?", (new_path, card_id))
            updated_count += 1
            print(f"✅ Updated '{card_id}': \n   Old: {image_path}\n   New: {new_path}\n")

    # Commit changes and close
    conn.commit()
    conn.close()
    
    print(f"🎉 Finished! Successfully updated {updated_count} image paths.")

if __name__ == "__main__":
    fix_image_paths()
