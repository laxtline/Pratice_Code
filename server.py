"""Dependency-free local Python compiler, terminal, trace and sharing server."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import argparse
import atexit
import io
import json
import mimetypes
import os
import secrets
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from languages import LANGUAGES, manifest

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / 'static'
APP_HOME = Path(os.environ.get('LOCAL_COMPILER_HOME', str(ROOT))).resolve()
DATA = APP_HOME / 'data'
DATA.mkdir(exist_ok=True)
WORKSPACE = APP_HOME / 'workspace'
WORKSPACE.mkdir(exist_ok=True)
FILES_LOCK = threading.Lock()
for language_config in LANGUAGES.values():
    language_file = WORKSPACE / language_config['filename']
    if not language_file.exists():
        language_file.write_text(language_config['code'],encoding='utf-8')
MAX_SOURCE = 200_000
MAX_OUTPUT = 1_000_000
RUN_TIMEOUT = 20
RUNS = {}
RUNS_LOCK = threading.Lock()

def db():
    connection = sqlite3.connect(DATA/'compiler.sqlite3')
    connection.execute('CREATE TABLE IF NOT EXISTS shares (id TEXT PRIMARY KEY, code TEXT NOT NULL, created REAL NOT NULL)')
    if 'language' not in [r[1] for r in connection.execute('PRAGMA table_info(shares)')]:
        connection.execute("ALTER TABLE shares ADD COLUMN language TEXT NOT NULL DEFAULT 'python'")
    return connection

class Run:
    def __init__(self, code, mode, language='python'):
        self.id = secrets.token_urlsafe(18)
        self.events = []
        self.lock = threading.RLock()
        self.status = 'running'
        self.waiting = False
        self.language = language
        self.started = time.monotonic()
        self.activity = self.started
        self.elapsed = 0
        self.output_size = 0
        self.temp = tempfile.TemporaryDirectory(prefix='programiz-local-')
        path = Path(self.temp.name)/LANGUAGES[language]['filename']
        path.write_text(code, encoding='utf-8')
        env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
        # -I ignores inherited Python paths and user site packages.
        if language == 'python':
            command = [sys.executable,'-I','-u',str(ROOT/'worker.py'),str(path),mode]
        else:
            command = [sys.executable,'-u',str(ROOT/'polyglot_worker.py'),str(path),language]
        self.process = subprocess.Popen(command,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            cwd=self.temp.name,env=env,text=True,encoding='utf-8',errors='replace',bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            start_new_session=os.name != 'nt')
        threading.Thread(target=self.read_output, daemon=True).start()
        threading.Thread(target=self.read_errors, daemon=True).start()
        threading.Thread(target=self.watch, daemon=True).start()

    def add(self, event):
        with self.lock:
            event = dict(event, seq=len(self.events))
            self.events.append(event)

    def read_errors(self):
        for line in self.process.stderr:
            self.add({'type':'stderr','text':line})

    def read_output(self):
        try:
            for line in self.process.stdout:
                try:
                    event = json.loads(line)
                except ValueError:
                    event = {'type':'stdout','text':line}
                if event['type'] in ('stdout','stderr'):
                    self.output_size += len(event.get('text','').encode('utf-8'))
                    if self.output_size > MAX_OUTPUT:
                        self.stop('Output limit exceeded (1 MB).')
                        break
                with self.lock:
                    if event['type'] == 'input_request':
                        self.waiting = True
                        self.activity = time.monotonic()
                    if event['type'] == 'complete':
                        self.exit_code = event.get('exit_code',0)
                    else:
                        self.add(event)
            self.process.wait()
        finally:
            with self.lock:
                if self.status == 'running':
                    self.status = 'finished'
                    self.waiting = False
                    self.add({'type':'done','exit_code':self.process.returncode or 0,
                              'reason':None,'elapsed':round(time.monotonic()-self.started,3)})
            for stream in (self.process.stdin,self.process.stdout,self.process.stderr):
                try:
                    stream.close()
                except OSError:
                    pass
            try:
                self.temp.cleanup()
            except OSError:
                pass

    def watch(self):
        previous = time.monotonic()
        while self.status == 'running':
            time.sleep(0.1)
            now = time.monotonic()
            if not self.waiting or self.language != 'python':
                self.elapsed += now-previous
            previous = now
            if self.elapsed > RUN_TIMEOUT:
                self.stop(f'Execution timed out after {RUN_TIMEOUT} seconds.')
            elif self.waiting and now-self.activity > 600:
                self.stop('Input timed out after 10 minutes.')

    def stop(self, reason='Execution stopped.'):
        with self.lock:
            if self.status != 'running':
                return
            self.status = 'stopped'
            self.waiting = False
            # Stop the owned execution process and descendants only.
            if self.process.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill','/PID',str(self.process.pid),'/T','/F'],
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    try:
                        os.killpg(self.process.pid,signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            self.add({'type':'done','exit_code':-1,'reason':reason,
                      'elapsed':round(time.monotonic()-self.started,3)})

    def input(self, value, eof=False):
        with self.lock:
            if self.status != 'running' or not self.waiting:
                raise ValueError('The program is not waiting for input.')
            if eof:
                self.process.stdin.close()
            else:
                self.process.stdin.write(value+'\n')
                self.process.stdin.flush()
            self.waiting = False
            self.activity = time.monotonic()
            self.add({'type':'stdin','text':value+'\n' if not eof else ''})

def stop_all():
    for run in list(RUNS.values()):
        run.stop('Server stopped.')

atexit.register(stop_all)

class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, fmt, *args):
        if args and str(args[0]).startswith('POST'):
            super().log_message(fmt,*args)

    def respond(self, status, content, content_type='application/json; charset=utf-8', extra=None):
        if not isinstance(content,bytes):
            content = json.dumps(content,ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(content)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        for key,value in (extra or {}).items():
            self.send_header(key,value)
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError,ConnectionResetError):
            pass

    def valid_host(self):
        host = self.headers.get('Host','')
        return host in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')

    def do_GET(self):
        if not self.valid_host():
            return self.respond(403,{'error':'Local access only.'})
        parsed = urlparse(self.path)
        path = parsed.path
        if path == '/api/health':
            return self.respond(200,{'ok':True,'app':'programiz-local','python':sys.version.split()[0]})
        if path == '/api/languages':
            return self.respond(200,{'languages':manifest(),'directory':str(WORKSPACE)})
        if path.startswith('/api/files/'):
            language = path.rsplit('/',1)[-1]
            if language not in LANGUAGES:
                return self.respond(404,{'error':'Unknown language.'})
            file = WORKSPACE/LANGUAGES[language]['filename']
            with FILES_LOCK:
                return self.respond(200,{'code':file.read_text(encoding='utf-8'),'filename':file.name,'path':str(file)})
        if path.startswith('/api/runs/'):
            run = RUNS.get(path.rsplit('/',1)[-1])
            if not run:
                return self.respond(404,{'error':'Run not found.'})
            try:
                offset = max(0,int(parse_qs(parsed.query).get('after',['0'])[0]))
            except ValueError:
                return self.respond(400,{'error':'Invalid event offset.'})
            with run.lock:
                return self.respond(200,{'events':run.events[offset:],'next':len(run.events),
                                         'status':run.status,'waiting':run.waiting})
        if path.startswith('/api/shares/'):
            with db() as connection:
                row = connection.execute('SELECT code,language FROM shares WHERE id=?',(path.rsplit('/',1)[-1],)).fetchone()
            return self.respond(200,{'code':row[0],'language':row[1]}) if row else self.respond(404,{'error':'Shared code not found.'})
        if path in ('/','/index.html','/python-programming/online-compiler/') or path.startswith('/s/'):
            file = STATIC/'index.html'
        else:
            file = (STATIC/path.lstrip('/')).resolve()
            if not file.is_relative_to(STATIC.resolve()):
                return self.respond(403,{'error':'Forbidden.'})
        if not file.is_file():
            return self.respond(404,{'error':'Not found.'})
        self.respond(200,file.read_bytes(),mimetypes.guess_type(file)[0] or 'application/octet-stream')

    def do_POST(self):
        if not self.valid_host():
            return self.respond(403,{'error':'Local access only.'})
        origin = self.headers.get('Origin')
        if self.headers.get('X-Local-Compiler') != '1' or (origin and origin not in (
            f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}')):
            return self.respond(403,{'error':'Requests must come from the local editor.'})
        try:
            length = int(self.headers.get('Content-Length','0'))
            if length < 0 or length > MAX_SOURCE+100_000:
                return self.respond(413,{'error':'Request is too large.'})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data,dict):
                raise ValueError('Expected a JSON object.')
            path = urlparse(self.path).path
            if path == '/api/shutdown':
                self.respond(200,{'ok':True})
                threading.Thread(target=self.server.shutdown,daemon=True).start()
                return
            if path in ('/api/runs','/api/shares','/api/download') or path.startswith('/api/files/'):
                code = data.get('code','')
                if not isinstance(code,str) or len(code.encode('utf-8')) > MAX_SOURCE:
                    raise ValueError('Code must be text under 200 KB.')
                language = data.get('language','python') if not path.startswith('/api/files/') else path.rsplit('/',1)[-1]
                if language not in LANGUAGES:
                    raise ValueError('Unknown language.')
            if path.startswith('/api/files/'):
                file = WORKSPACE/LANGUAGES[language]['filename']
                with FILES_LOCK:
                    temporary_file = file.with_suffix(file.suffix+'.saving')
                    temporary_file.write_text(code,encoding='utf-8')
                    temporary_file.replace(file)
                return self.respond(200,{'saved':True,'filename':file.name,'path':str(file)})
            if path == '/api/runs':
                mode = data.get('mode','run')
                if mode not in ('run','trace'):
                    raise ValueError('Unknown execution mode.')
                if mode == 'trace' and language != 'python':
                    raise ValueError('Step visualization is available for Python. Use Run for this language.')
                if language == 'html':
                    raise ValueError('HTML renders in the live browser preview.')
                with RUNS_LOCK:
                    if sum(r.status == 'running' for r in RUNS.values()) >= 4:
                        return self.respond(429,{'error':'Four programs are already running. Stop one first.'})
                    # Retain recent completed runs for the browser's final poll.
                    for key in list(RUNS):
                        if RUNS[key].status != 'running' and time.monotonic()-RUNS[key].started > 600:
                            del RUNS[key]
                    run = Run(code,mode,language)
                    RUNS[run.id] = run
                return self.respond(201,{'id':run.id})
            if path.startswith('/api/runs/'):
                _,_,_,run_id,action = path.split('/')
                run = RUNS.get(run_id)
                if not run:
                    return self.respond(404,{'error':'Run not found.'})
                if action == 'stop':
                    run.stop()
                elif action == 'input':
                    value = data.get('value','')
                    if not isinstance(value,str) or len(value)>10_000:
                        raise ValueError('Input must be text under 10 KB.')
                    run.input(value,bool(data.get('eof',False)))
                else:
                    return self.respond(404,{'error':'Unknown action.'})
                return self.respond(200,{'ok':True})
            if path == '/api/shares':
                share_id = secrets.token_urlsafe(9)
                with db() as connection:
                    connection.execute('INSERT INTO shares (id,code,created,language) VALUES (?,?,?,?)',(share_id,code,time.time(),language))
                return self.respond(201,{'path':'/s/'+share_id})
            if path == '/api/download':
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr(LANGUAGES[language]['filename'],code)
                    archive.writestr('README.txt',f"{LANGUAGES[language]['name']} project\n\nOpen {LANGUAGES[language]['filename']} with the matching local runtime.\n")
                return self.respond(200,buffer.getvalue(),'application/zip',
                    {'Content-Disposition':f'attachment; filename="{language}-project.zip"'})
            return self.respond(404,{'error':'Unknown endpoint.'})
        except (ValueError,KeyError,BrokenPipeError) as error:
            return self.respond(400,{'error':str(error)})
        except Exception as error:
            print('Request failed:',repr(error),file=sys.stderr)
            return self.respond(500,{'error':'The local server could not complete this request.'})

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8000)
    args = parser.parse_args()
    mimetypes.add_type('application/javascript','.js')
    mimetypes.add_type('image/svg+xml','.svg')
    httpd = ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'Local Python compiler: http://127.0.0.1:{httpd.server_port}',flush=True)
    print('Press Ctrl+C to stop. Runs use your local Python interpreter.',flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_all()
        httpd.server_close()
