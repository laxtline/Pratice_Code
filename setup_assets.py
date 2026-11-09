"""Download the public visual assets once; the app then works offline."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import shutil
import urllib.request

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / 'static' / 'assets'
VENDOR = ROOT / 'static' / 'vendor'
BASE = 'https://cdn.playground-v2.programiz.com/assets/'
names = ['python','r','sql','html','java','kotlin','c','cpp','csharp','javascript',
         'typescript','golang','rust','scala','dart','ruby','php','swift']
urls = {f'{n}.svg': BASE + f'icons/{n}.svg' for n in names}
urls.update({'logo.svg': BASE+'logos/logo.svg', 'logo-inverted.svg':BASE+'logos/logo-inverted.svg',
             'fonts.css':'https://fonts.programiz.com/compiler.css'})

def fetch(item):
    name, url = item
    with urllib.request.urlopen(url, timeout=30) as response:
        (ASSETS / name).write_bytes(response.read())
    return name

if __name__ == '__main__':
    ASSETS.mkdir(parents=True, exist_ok=True)
    VENDOR.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        for name in pool.map(fetch, urls.items()):
            print('Saved', name)
    for name in names:
        file = ASSETS/(name+'.svg')
        text = file.read_text(encoding='utf-8')
        # The original page styles inline SVG paths. Standalone image files
        # need an explicit fill because their root declares fill="none".
        text = re.sub(r'<path(?![^>]*\bfill=)', '<path fill="#aeb0bd"', text)
        file.write_text(text,encoding='utf-8')
    css = (ASSETS/'fonts.css').read_text()
    for url in set(re.findall(r'url\([\'\"]?(https://[^)\'\"]+)', css)):
        name = url.split('/')[-1].split('?')[0]
        fetch((name, url))
        css = css.replace(url, '/assets/'+name)
    (ASSETS/'fonts.css').write_text(css)
    cm = ROOT/'frontend-deps'/'node_modules'/'codemirror'
    for rel, name in [('lib/codemirror.js','codemirror.js'),('lib/codemirror.css','codemirror.css'),
                      ('mode/python/python.js','python.js'),('addon/edit/matchbrackets.js','matchbrackets.js'),
                      ('addon/edit/closebrackets.js','closebrackets.js'),('addon/selection/active-line.js','active-line.js'),
                      ('addon/comment/comment.js','comment.js'),('LICENSE','CODEMIRROR-LICENSE')]:
        shutil.copyfile(cm/rel, VENDOR/name)
    for mode in ('javascript','xml','css','htmlmixed','clike','sql','r','go','rust','dart','ruby','php','swift'):
        shutil.copyfile(cm/'mode'/mode/(mode+'.js'),VENDOR/(mode+'.js'))
