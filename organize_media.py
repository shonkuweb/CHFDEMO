import os
import sqlite3
import glob

# Mapping old names to their organized destination.
file_mapping = {
    "ceintro.png": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_intro.png",
    "ce1.png": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_1.png",
    "ce2.png": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_2.png",
    "ce3.png": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_3.png",
    "ce4.png": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_4.png",
    "whiteglove1.png": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/white_glove_1.png",
    "whiteglove2.png": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/white_glove_2.png",
    "whiteglove3.png": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/white_glove_3.png",
    "whiteglove4.png": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/white_glove_4.png",
    "aboutus1.png": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/about/aboutus_legacy.png",
    "dummy.jpg": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/placeholder.jpg",
}

def ensure_dir(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d)

def move_files():
    print("Moving files to structured directories...")
    for old, new in file_mapping.items():
        if os.path.exists(old):
            ensure_dir(new)
            os.rename(old, new)
            print(f"Moved {old} -> {new}")
        else:
            print(f"File {old} not found, skipping...")

def update_db():
    print("Re-aligning Database entries...")
    conn = sqlite3.connect('chf_archive.db')
    cur = conn.cursor()
    for old, new in file_mapping.items():
        # Update site_content
        cur.execute("UPDATE site_content SET value = ? WHERE value = ?", (new, old))
        
        # Update categories
        cur.execute("UPDATE categories SET image = ? WHERE image = ?", (new, old))
    conn.commit()
    conn.close()
    print("Database updated!")

def update_codebase():
    print("Updating static HTML and seeder files...")
    # Find all .html and the seeder
    files_to_check = glob.glob("*.html") + ["database_seeder.py"]
    for file_path in files_to_check:
        with open(file_path, "r") as f:
            content = f.read()
            
        original_content = content
        for old, new in file_mapping.items():
            content = content.replace(f"'{old}'", f"'{new}'")
            content = content.replace(f'"{old}"', f'"{new}"')
            content = content.replace(f"url({old})", f"url({new})")
            
        if content != original_content:
            with open(file_path, "w") as f:
                f.write(content)
            print(f"Updated references in {file_path}")

if __name__ == "__main__":
    move_files()
    update_db()
    update_codebase()
    print("\n✅ Media Organization Complete! All counterparts mapped and organized.")
