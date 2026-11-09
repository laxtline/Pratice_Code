from pathlib import Path
import re
root=Path(__file__).resolve().parent/'static'/'assets'
for file in root.glob('*.svg'):
    if file.name.startswith('logo'):
        continue
    text=file.read_text(encoding='utf-8')
    text=re.sub(r'<path(?![^>]*\bfill=)', '<path fill="#aeb0bd"', text)
    file.write_text(text,encoding='utf-8')
