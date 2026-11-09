"""Owned Python execution worker. JSON-lines is private to the local backend."""
import builtins
import io
import json
import os
import sys
import threading
import traceback

channel = sys.stdout
original_stdin = sys.stdin
lock = threading.Lock()
trace_enabled = sys.argv[2] == 'trace'
source = open(sys.argv[1], encoding='utf-8').read()

def emit(kind, **values):
    with lock:
        channel.write(json.dumps(dict(type=kind, **values), ensure_ascii=True) + '\n')
        channel.flush()

class Output(io.TextIOBase):
    def __init__(self, kind):
        self.kind = kind
    @property
    def encoding(self):
        return 'utf-8'
    def writable(self):
        return True
    def isatty(self):
        return True
    def write(self, value):
        if value:
            emit(self.kind, text=str(value))
        return len(value)
    def flush(self):
        pass

class Input(io.TextIOBase):
    @property
    def encoding(self):
        return 'utf-8'
    def readable(self):
        return True
    def isatty(self):
        return True
    def readline(self, size=-1):
        emit('input_request')
        return original_stdin.readline(size)
    def read(self, size=-1):
        if size < 0:
            emit('input_request', eof=True)
            return original_stdin.read()
        emit('input_request')
        return original_stdin.read(size)

sys.stdout = Output('stdout')
sys.stderr = Output('stderr')
sys.stdin = Input()

def local_input(prompt=''):
    sys.stdout.write(str(prompt))
    result = sys.stdin.readline()
    if not result:
        raise EOFError('EOF when reading a line')
    return result.removesuffix('\n').removesuffix('\r')

builtins.input = local_input
steps = 0
trace_truncated = False

def value_preview(value, depth=0, seen=None):
    seen = set() if seen is None else seen
    if isinstance(value, (str, int, float, bool, type(None))):
        try:
            text = repr(value)
        except Exception:
            text = '<value>'
        return {'type': type(value).__name__, 'value': text[:400]}
    if id(value) in seen:
        return {'type': type(value).__name__, 'value': '<recursive reference>'}
    seen.add(id(value))
    if depth < 2 and isinstance(value, (list, tuple, set, frozenset)):
        items = [value_preview(v, depth+1, seen.copy()) for v in list(value)[:30]]
        return {'type':type(value).__name__,'items':items,'length':len(value)}
    if depth < 2 and isinstance(value, dict):
        items = [{'key':value_preview(k, depth+1, seen.copy()),'value':value_preview(v, depth+1, seen.copy())}
                 for k,v in list(value.items())[:30]]
        return {'type':'dict','entries':items,'length':len(value)}
    # Never call arbitrary user-defined __repr__ while tracing.
    if isinstance(value, type(local_input)):
        text = '<function '+value.__name__+'>'
    elif isinstance(value, type(sys)):
        text = '<module '+value.__name__+'>'
    else:
        text = '<'+type(value).__name__+'>'
    return {'type':type(value).__name__,'value':text}

def trace(frame, event, arg):
    global steps, trace_truncated
    if frame.f_code.co_filename != 'main.py':
        return None
    if event in ('line', 'return', 'exception'):
        if steps >= 500:
            if not trace_truncated:
                emit('trace_limit', text='Showing the first 500 execution steps.')
                trace_truncated = True
            return None
        stack = []
        current = frame
        while current:
            if current.f_code.co_filename == 'main.py':
                variables = {str(k):value_preview(v) for k,v in list(current.f_locals.items())[:60]
                             if not str(k).startswith('__')}
                stack.append({'name':current.f_code.co_name,'line':current.f_lineno,'variables':variables})
            current = current.f_back
        info = dict(line=frame.f_lineno,event=event,frames=stack[::-1])
        if event == 'return':
            info['return_value'] = value_preview(arg)
        if event == 'exception':
            info['exception'] = arg[0].__name__
        emit('trace', **info)
        steps += 1
    return trace

exit_code = 0
try:
    if trace_enabled:
        sys.settrace(trace)
    globals_dict = {'__name__':'__main__','__file__':'main.py','__builtins__':builtins}
    exec(compile(source, 'main.py', 'exec'), globals_dict)
except SystemExit as error:
    if isinstance(error.code, int):
        exit_code = error.code
    elif error.code is not None:
        sys.stderr.write(str(error.code)+'\n')
        exit_code = 1
except BaseException as error:
    sys.settrace(None)
    exit_code = 1
    if isinstance(error, SyntaxError):
        sys.stderr.write(''.join(traceback.format_exception_only(type(error), error)))
    else:
        frames = [f for f in traceback.extract_tb(error.__traceback__) if f.filename != __file__]
        sys.stderr.write('Traceback (most recent call last):\n')
        source_lines = source.splitlines()
        for f in frames:
            sys.stderr.write(f'  File "{f.filename}", line {f.lineno}, in {f.name}\n')
            if f.filename == 'main.py' and 0 < f.lineno <= len(source_lines):
                sys.stderr.write('    '+source_lines[f.lineno-1].strip()+'\n')
        sys.stderr.write(''.join(traceback.format_exception_only(type(error), error)))
finally:
    sys.settrace(None)
    emit('complete', exit_code=exit_code)
sys.exit(exit_code)
