import os
import glob
import re

def inject_assets():
    # Assets to inject
    css_link = '    <!-- Premium Animations -->\n    <link rel="stylesheet" href="assets/animations.css">\n    <script src="assets/animation-core.js" defer></script>\n'
    
    # Path to HTML files
    html_files = glob.glob('*.html')
    
    for file_path in html_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Check if already injected
        if 'assets/animations.css' in content:
            print(f"Skipping {file_path} (already injected)")
            continue
            
        # Inject before </head> or before another common tag
        if '</head>' in content:
            new_content = content.replace('</head>', css_link + '</head>')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Injected assets into {file_path}")
        else:
            print(f"Could not find </head> in {file_path}")

if __name__ == "__main__":
    inject_assets()
