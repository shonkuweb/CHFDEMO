import codecs
import re
import glob

try:
    with codecs.open('index.html', 'r', 'utf-8') as f:
        idx_content = f.read()
except Exception as e:
    print(f"Error reading index.html: {e}")
    exit(1)

# Pattern to capture from <!-- Mobile Menu Overlay --> up to the </nav></div> before <main
menu_pattern = re.compile(r'<!-- Mobile Menu Overlay -->.*?</nav>\s*</div>(?=\s*<main)', re.DOTALL)
match = menu_pattern.search(idx_content)

if not match:
    print("Could not find mobile menu in index.html")
    exit(1)

master_menu = match.group(0)

html_files = glob.glob('*.html')
updated_count = 0
for file in html_files:
    if file == 'index.html':
        continue
    
    with codecs.open(file, 'r', 'utf-8') as f:
        content = f.read()
        
    if menu_pattern.search(content):
        new_content = menu_pattern.sub(master_menu.replace('\\', '\\\\'), content)
        
        with codecs.open(file, 'w', 'utf-8') as f:
            f.write(new_content)
        updated_count += 1
        print(f"Synced mobile menu in {file}")
    else:
        print(f"No mobile menu tag found in {file}")

print(f"Successfully synced mobile menu across {updated_count} files.")
