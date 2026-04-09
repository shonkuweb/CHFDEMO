import codecs
import re
import glob
import os

def sync():
    # Source of truth
    source_file = 'index.html'
    if not os.path.exists(source_file):
        print(f"Error: {source_file} not found")
        return

    with codecs.open(source_file, 'r', 'utf-8') as f:
        master_content = f.read()

    # Define extraction patterns for index.html
    header_pattern = re.compile(r'<header[^>]*>.*?</header>', re.DOTALL)
    # Match from overlay comment to the closing div of the menu
    menu_pattern = re.compile(r'<!-- Mobile Menu Overlay -->\s*<div id="mobile-menu".*?</div>(?=\s*<main)', re.DOTALL)
    # The variant where mobile menu is AFTER main
    menu_pattern_alternative = re.compile(r'<!-- Mobile Menu Overlay -->\s*<div id="mobile-menu".*?</div>(?=\s*<footer)', re.DOTALL)
    id_pattern = re.compile(r'<div id="mobile-menu".*?</div>', re.DOTALL)
    footer_pattern = re.compile(r'<footer[^>]*>.*?</footer>', re.DOTALL)
    script_pattern = re.compile(r'<script>\s*// Mobile Menu Logic.*?</script>', re.DOTALL)

    # Extract master blocks
    header_match = header_pattern.search(master_content)
    menu_match = menu_pattern.search(master_content)
    footer_match = footer_pattern.search(master_content)
    script_match = script_pattern.search(master_content)

    if not all([header_match, menu_match, footer_match, script_match]):
        print("Error: Could not extract all master blocks from index.html")
        if not header_match: print("- Header missing")
        if not menu_match: print("- Mobile Menu missing")
        if not footer_match: print("- Footer missing")
        if not script_match: print("- Navigation Script missing")
        return

    master_header = header_match.group(0)
    master_menu = menu_match.group(0)
    master_footer = footer_match.group(0)
    master_script = script_match.group(0)

    # Files to ignore
    ignore_files = ['index.html', 'admin.html', 'server.py', 'sync_footer.py', 'sync_mobile_menu.py', 'sync_global.py', 'update_socials.py', 'mcp_config.json']

    html_files = glob.glob('*.html')
    updated_count = 0

    for file in html_files:
        if file in ignore_files:
            continue

        with codecs.open(file, 'r', 'utf-8') as f:
            content = f.read()

        changed = False

        # Replace Header
        if header_pattern.search(content):
            content = header_pattern.sub(master_header.replace('\\', '\\\\'), content)
            changed = True
        
        # Replace Footer
        if footer_pattern.search(content):
            content = footer_pattern.sub(master_footer.replace('\\', '\\\\'), content)
            changed = True

        # Replace Mobile Menu (Try both positional patterns)
        if menu_pattern.search(content):
            content = menu_pattern.sub(master_menu.replace('\\', '\\\\'), content)
            changed = True
        elif menu_pattern_alternative.search(content):
            # If it was after main, we still replace it in-place using the alternative pattern
            content = menu_pattern_alternative.sub(master_menu.replace('\\', '\\\\'), content)
            changed = True
        else:
             # Fallback: find it by id if comments are missing
             if id_pattern.search(content):
                 content = id_pattern.sub(master_menu.replace('\\', '\\\\'), content)
                 changed = True

        # Replace Navigation Script
        if script_pattern.search(content):
            content = script_pattern.sub(master_script, content)
            changed = True
        else:
            # Fallback for script if comment is missing
            fallback_script_pattern = re.compile(r'<script>\s*// Mobile Menu Logic.*?</script>', re.DOTALL)
            # Try to find common mobile menu script lines
            simple_script_pattern = re.compile(r'<script>\s*const mobileBtn = document\.getElementById\(\'mobile-menu-btn\'\);.*?</script>', re.DOTALL)
            if simple_script_pattern.search(content):
                content = simple_script_pattern.sub(master_script, content)
                changed = True

        if changed:
            with codecs.open(file, 'w', 'utf-8') as f:
                f.write(content)
            updated_count += 1
            print(f"Synced {file}")

    print(f"\nSuccessfully synchronized {updated_count} files.")

if __name__ == '__main__':
    sync()
