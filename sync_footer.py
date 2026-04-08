import codecs
import re
import glob

# Read index.html to grab the reference footer
try:
    with codecs.open('index.html', 'r', 'utf-8') as f:
        idx_content = f.read()
except Exception as e:
    print(f"Error reading index.html: {e}")
    exit(1)

footer_pattern = re.compile(r'<footer[^>]*>.*?</footer>', re.DOTALL)
match = footer_pattern.search(idx_content)

if not match:
    print("Could not find footer in index.html")
    exit(1)

master_footer = match.group(0)

# Replace in all HTML files
html_files = glob.glob('*.html')
updated_count = 0
for file in html_files:
    if file == 'index.html':
        continue
    
    with codecs.open(file, 'r', 'utf-8') as f:
        content = f.read()
        
    if footer_pattern.search(content):
        new_content = footer_pattern.sub(master_footer, content)
        
        with codecs.open(file, 'w', 'utf-8') as f:
            f.write(new_content)
        updated_count += 1
        print(f"Synced footer in {file}")
    else:
        print(f"No footer tag found in {file}")

print(f"Successfully synced footer across {updated_count} files.")
