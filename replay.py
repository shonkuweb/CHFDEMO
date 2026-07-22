import json

file_path = 'admin-dashboard.html'
# restore original
import os
os.system('git checkout HEAD -- admin.html')
os.system('mv admin.html admin-dashboard.html')

with open(file_path, 'r') as f:
    content = f.read()

for l in open('/Users/shonkuweb/.gemini/antigravity/brain/522303c9-b02c-4838-8aef-39dfe8090e61/.system_generated/logs/transcript_full.jsonl'):
    try:
        d = json.loads(l)
        if 'tool_calls' in d:
            for t in d['tool_calls']:
                if t['name'] in ['replace_file_content', 'multi_replace_file_content'] and 'admin.html' in str(t['args']):
                    chunks = t['args'].get('ReplacementChunks', [t['args']])
                    for chunk in chunks:
                        target = chunk['TargetContent']
                        replacement = chunk['ReplacementContent']
                        start_line = chunk.get('StartLine', 1) - 1
                        end_line = chunk.get('EndLine', -1)
                        
                        lines = content.split('\n')
                        if end_line == -1: end_line = len(lines)
                        
                        search_area = '\n'.join(lines[start_line:end_line])
                        
                        if target in search_area:
                            new_search_area = search_area.replace(target, replacement, 1)
                            lines[start_line:end_line] = new_search_area.split('\n')
                            content = '\n'.join(lines)
                        else:
                            # fallback if lines changed
                            if target in content:
                                content = content.replace(target, replacement, 1)
    except Exception as e: 
        pass

with open(file_path, 'w') as f:
    f.write(content)
print("Replay finished")
