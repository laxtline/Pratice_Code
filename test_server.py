"""Integration checks against the running local server. Run: python test_server.py"""
import io
import json
import os
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

BASE = os.environ.get('LOCAL_COMPILER_TEST_URL','http://127.0.0.1:8000')

def api(path, data=None, headers=None):
    request = Request(BASE+path, data=None if data is None else json.dumps(data).encode(),
        headers=headers if headers is not None else {'Content-Type':'application/json','X-Local-Compiler':'1'})
    with urlopen(request, timeout=30) as response:
        return json.load(response)

def start(code, mode='run', language='python'):
    return api('/api/runs',{'code':code,'mode':mode,'language':language})['id']

def wait(run_id, predicate=None, timeout=10):
    deadline = time.monotonic()+timeout
    while time.monotonic()<deadline:
        result = api('/api/runs/'+run_id)
        if predicate(result) if predicate else result['status']!='running':
            return result
        time.sleep(.05)
    raise AssertionError('Run did not reach expected state: '+run_id)

def output(result):
    return ''.join(e.get('text','') for e in result['events'] if e['type'] in ('stdout','stderr','stdin'))

class CompilerTests(unittest.TestCase):
    def test_output_unicode_and_errors(self):
        result=wait(start('import sys\nprint("नमस्ते 🐍")\nsys.stderr.write("warning\\n")'))
        self.assertIn('नमस्ते 🐍',output(result))
        self.assertIn('warning',output(result))
        self.assertEqual(result['events'][-1]['exit_code'],0)
        result=wait(start('print(1/0)'))
        self.assertIn('ZeroDivisionError',output(result))
        self.assertNotEqual(result['events'][-1]['exit_code'],0)
        result=wait(start('for x in range(3)\n print(x)'))
        self.assertIn('SyntaxError',output(result))

    def test_interactive_input_twice(self):
        run_id=start('name=input("Name: ")\nage=int(input("Age: "))\nprint(name,age+1)')
        self.assertIn('Name: ',output(wait(run_id,lambda r:r['waiting'])))
        api('/api/runs/'+run_id+'/input',{'value':'Surya'})
        result=wait(run_id,lambda r:r['waiting'] and 'Age:' in output(r))
        api('/api/runs/'+run_id+'/input',{'value':'25'})
        result=wait(run_id)
        self.assertIn('Surya 26',output(result))
        self.assertEqual(result['events'][-1]['exit_code'],0)

    def test_stdin_readline_and_eof(self):
        run_id=start('import sys\nprint(sys.stdin.readline().strip().upper())')
        wait(run_id,lambda r:r['waiting'])
        api('/api/runs/'+run_id+'/input',{'value':'hello'})
        self.assertIn('HELLO',output(wait(run_id)))
        run_id=start('import sys\nprint(repr(sys.stdin.read()))')
        wait(run_id,lambda r:r['waiting'])
        api('/api/runs/'+run_id+'/input',{'eof':True})
        self.assertIn("''",output(wait(run_id)))

    def test_tracer_frames_and_collections(self):
        code='numbers=[1,2,3]\ndef total(n):\n if n==0: return 0\n return n+total(n-1)\nanswer=total(3)\nprint(answer)'
        result=wait(start(code,'trace'))
        traces=[e for e in result['events'] if e['type']=='trace']
        self.assertGreater(len(traces),10)
        self.assertTrue(any(len(e['frames'])>=4 for e in traces))
        self.assertTrue(any('numbers' in e['frames'][0]['variables'] for e in traces))
        self.assertIn('6',output(result))

    def test_stop_and_timeout(self):
        run_id=start('while True: pass')
        api('/api/runs/'+run_id+'/stop',{})
        result=wait(run_id)
        self.assertEqual(result['status'],'stopped')
        self.assertIn('stopped',result['events'][-1]['reason'])
        run_id=start('while True: pass')
        result=wait(run_id,timeout=25)
        self.assertIn('timed out',result['events'][-1]['reason'])

    def test_output_limit(self):
        result=wait(start('print("x"*1100000)'))
        self.assertEqual(result['status'],'stopped')
        self.assertIn('Output limit',result['events'][-1]['reason'])

    def test_share_download_and_assets(self):
        code='print("saved")\n'
        share=api('/api/shares',{'code':code})
        self.assertEqual(api('/api/shares/'+share['path'].split('/')[-1])['code'],code)
        with urlopen(BASE+share['path']) as response:
            self.assertIn(b'Local Python compiler',response.read())
        request=Request(BASE+'/api/download',data=json.dumps({'code':code}).encode(),headers={'Content-Type':'application/json','X-Local-Compiler':'1'})
        with urlopen(request) as response:
            with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                self.assertEqual(archive.read('main.py').decode(),code)
        for path in ('/','/style.css','/app.js','/vendor/codemirror.js','/assets/python.svg','/assets/fonts.css'):
            with urlopen(BASE+path) as response:
                self.assertEqual(response.status,200)

    def test_language_runtimes_and_file_saving(self):
        from pathlib import Path
        result=api('/api/languages')
        self.assertEqual(len(result['languages']),18)
        folder=Path(result['directory'])
        self.assertTrue((folder/'main.py').is_file())
        original=api('/api/files/javascript')['code']
        try:
            api('/api/files/javascript',{'code':'console.log("saved on disk");'})
            self.assertEqual((folder/'main.js').read_text(encoding='utf-8'),'console.log("saved on disk");')
            self.assertIn('saved on disk',api('/api/files/javascript')['code'])
        finally:
            api('/api/files/javascript',{'code':original})
        result=wait(start('console.log("JS works",6*7)','run','javascript'))
        self.assertIn('JS works 42',output(result))
        self.assertEqual(result['events'][-1]['exit_code'],0)
        result=wait(start('const message: string = "TS works"; console.log(message);','run','typescript'))
        self.assertIn('TS works',output(result))
        self.assertEqual(result['events'][-1]['exit_code'],0)
        result=wait(start('SELECT 6*7 AS answer;','run','sql'))
        self.assertIn('42',output(result))
        self.assertEqual(result['events'][-1]['exit_code'],0)
        result=wait(start('SELECT FROM;','run','sql'))
        self.assertIn('OperationalError',output(result))
        share=api('/api/shares',{'code':'console.log(1)','language':'javascript'})
        self.assertEqual(api('/api/shares/'+share['path'].split('/')[-1])['language'],'javascript')

    def test_reject_foreign_origin_and_invalid_requests(self):
        with self.assertRaises(HTTPError) as error:
            api('/api/runs',{'code':'print(1)'},headers={'Content-Type':'application/json'})
        self.assertEqual(error.exception.code,403)
        with self.assertRaises(HTTPError) as error:
            api('/api/runs',{'code':'print(1)'},headers={'Content-Type':'application/json','X-Local-Compiler':'1','Origin':'https://example.com'})
        self.assertEqual(error.exception.code,403)
        with self.assertRaises(HTTPError) as error:
            api('/api/runs',{'code':'print(1)','mode':'unknown'})
        self.assertEqual(error.exception.code,400)
        with self.assertRaises(HTTPError) as error:
            urlopen(BASE+'/../server.py')
        self.assertEqual(error.exception.code,403)

if __name__=='__main__':
    unittest.main(verbosity=2)
