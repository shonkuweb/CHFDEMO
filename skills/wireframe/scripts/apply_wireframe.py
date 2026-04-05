import os
import re

directory = os.getcwd()

css_utility = """        @layer utilities {
            .wireframe-cross {
                background-image: url('assets/wireframe-placeholder.svg');
                background-size: 100% 100%;
                background-repeat: no-repeat;
                background-position: center;
            }
        }"""

for filename in os.listdir(directory):
    if filename.endswith('.html'):
        filepath = os.path.join(directory, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Update the empty placeholder boxes to be more grey and have the cross class
        old_classes_1 = 'bg-surface-dark border border-white/5'
        new_classes_1 = 'bg-[#1a1a1a] border border-[#444] wireframe-cross'
        
        content = content.replace(old_classes_1, new_classes_1)
        
        # Inject the CSS utility class into the Tailwind block
        if '.wireframe-cross' not in content:
            if '<style type="text/tailwindcss">' in content:
                content = content.replace('<style type="text/tailwindcss">', f'<style type="text/tailwindcss">\n{css_utility}')
            else:
                head_end = content.find('</head>')
                if head_end != -1:
                    content = content[:head_end] + f'<style type="text/tailwindcss">\n{css_utility}\n</style>\n' + content[head_end:]

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

print("Wireframe styling applied to placeholder divs.")
