"""Run an available local language runtime and forward terminal events."""
from pathlib import Path
import json
import os
import sqlite3
import subprocess
import sys
import threading
from languages import LANGUAGES, command_path

path = Path(sys.argv[1])
language = sys.argv[2]
config = LANGUAGES[language]
channel = sys.stdout
lock = threading.Lock()

def emit(kind, **values):
    with lock:
        channel.write(json.dumps(dict(type=kind, **values), ensure_ascii=True)+'\n')
        channel.flush()

if language == 'sql':
    connection = sqlite3.connect(':memory:')
    connection.set_progress_handler(lambda: 0,1000)
    statement = ''
    try:
        for character in path.read_text(encoding='utf-8')+'\n;':
            statement += character
            if character == ';' and sqlite3.complete_statement(statement):
                cursor = connection.execute(statement)
                if cursor.description:
                    names = [c[0] for c in cursor.description]
                    rows = cursor.fetchmany(1001)
                    truncated = len(rows)>1000
                    rows = rows[:1000]
                    text_rows = [[str(v) if v is not None else 'NULL' for v in row] for row in rows]
                    widths = [min(60,max(len(name),*(len(row[i]) for row in text_rows))) if text_rows else len(name) for i,name in enumerate(names)]
                    def format_row(row):
                        return ' | '.join(value[:60].ljust(widths[i]) for i,value in enumerate(row))+'\n'
                    emit('stdout',text=format_row(names)+'-+-'.join('-'*w for w in widths)+'\n')
                    for row in text_rows:
                        emit('stdout',text=format_row(row))
                    emit('stdout',text=f'\n{len(rows)} row(s)'+(' (first 1000 shown)' if truncated else '')+'\n')
                statement = ''
        emit('complete',exit_code=0)
    except Exception as error:
        emit('stderr',text=f'{type(error).__name__}: {error}\n')
        emit('complete',exit_code=1)
        sys.exit(1)
    finally:
        connection.close()
    sys.exit(0)

runtime = command_path(language)
if not runtime:
    emit('stderr',text=f"{config['name']} runtime is not installed. Install {config['runtime']} and restart the local server.\nYour code is saved locally and can still be edited and downloaded.\n")
    emit('complete',exit_code=127)
    sys.exit(127)

exe = str(path.parent / ('program.exe' if os.name=='nt' else 'program'))
compile_command = None
commands = {
 'javascript':[runtime,str(path)],'typescript':[runtime,'--disable-warning=ExperimentalWarning',str(path)],
 'r':[runtime,str(path)],'java':[runtime,str(path)],'golang':[runtime,'run',str(path)],
 'scala':[runtime,str(path)],'dart':[runtime,'run',str(path)],'ruby':[runtime,str(path)],
 'php':[runtime,str(path)],'swift':[runtime,str(path)],'c':[exe],'cpp':[exe],
 'rust':[exe],'csharp':[exe],'kotlin':['java','-jar',str(path.parent/'main.jar')]
}
if language in ('c','cpp'):
    compile_command=[runtime,str(path),'-o',exe,'-std=c11' if language=='c' else '-std=c++17']
if language=='rust':
    compile_command=[runtime,str(path),'-o',exe]
if language=='csharp':
    compile_command=[runtime,'/nologo','/out:'+exe,str(path)]
if language=='kotlin':
    compile_command=[runtime,str(path),'-include-runtime','-d',str(path.parent/'main.jar')]
flags = subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
if compile_command:
    compiled = subprocess.run(compile_command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=flags)
    if compiled.stdout:
        emit('stdout' if compiled.returncode==0 else 'stderr',text=compiled.stdout)
    if compiled.returncode:
        emit('complete',exit_code=compiled.returncode)
        sys.exit(compiled.returncode)

process = subprocess.Popen(commands[language],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
    creationflags=flags,env=dict(os.environ,NODE_NO_WARNINGS='1'))

def forward(stream, kind):
    import codecs
    decoder=codecs.getincrementaldecoder('utf-8')('replace')
    while True:
        chunk = os.read(stream.fileno(),4096)
        if not chunk:
            tail=decoder.decode(b'',True)
            if tail: emit(kind,text=tail)
            return
        text=decoder.decode(chunk)
        if text: emit(kind,text=text)

def forward_input():
    while process.poll() is None:
        line = sys.stdin.readline()
        try:
            if not line:
                process.stdin.close()
                return
            process.stdin.write(line.encode('utf-8'))
            process.stdin.flush()
            emit('input_request',continuous=True)
        except (OSError,ValueError):
            return

threads = [threading.Thread(target=forward,args=(process.stdout,'stdout')),
           threading.Thread(target=forward,args=(process.stderr,'stderr'))]
for thread in threads: thread.start()
if language not in ('sql',):
    emit('input_request',continuous=True)
    threading.Thread(target=forward_input,daemon=True).start()
process.wait()
for thread in threads: thread.join()
emit('complete',exit_code=process.returncode)
sys.exit(process.returncode)
