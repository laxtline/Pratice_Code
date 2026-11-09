"""Exercise installation/update/removal in an isolated workspace directory."""
from pathlib import Path
from urllib.request import Request,urlopen
import json
import os
import subprocess
import tempfile
import time

ROOT=Path(__file__).resolve().parent
SETUP=ROOT/'Local-Code-Compiler-Setup.exe'
UNINSTALL=ROOT/'build'/'installer'/'Uninstall.exe'
test_base=ROOT/'build'/'installer-tests'
test_base.mkdir(parents=True,exist_ok=True)
folder=Path(tempfile.mkdtemp(prefix='install-',dir=test_base))
assert folder.resolve().is_relative_to(test_base.resolve())

def install():
    subprocess.run([str(SETUP),'--silent','--test','--target',str(folder),'--import-code'],check=True)

print('Test folder:',folder,flush=True)
install()
record=json.loads((folder/'.installation.json').read_text(encoding='utf-8-sig'))
runtime=next((folder/'.desktop-runtime').iterdir())
assert (runtime/'python.exe').is_file()
assert (runtime/'server.py').is_file()
assert (runtime/'static'/'index.html').is_file()
assert (folder/'Local Code Compiler.exe').is_file()
assert (folder/'Uninstall.exe').is_file()
assert (folder/'workspace'/'main.py').read_bytes()==(ROOT/'workspace'/'main.py').read_bytes()
print('PASS: all application/runtime files installed; existing code imported.',flush=True)

env=dict(os.environ,LOCAL_COMPILER_HOME=str(folder),PYTHONIOENCODING='utf-8')
server=subprocess.Popen([str(runtime/'python.exe'),'-u',str(runtime/'server.py'),'--port','0'],
    cwd=folder,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',
    creationflags=subprocess.CREATE_NO_WINDOW)
try:
    line=server.stdout.readline().strip()
    assert line.startswith('Local Python compiler: '),line
    url=line.split(': ',1)[1]
    def api(path,data=None):
        request=Request(url+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json','X-Local-Compiler':'1'})
        with urlopen(request,timeout=10) as response:return json.load(response)
    assert api('/api/health')['app']=='programiz-local'
    assert Path(api('/api/languages')['directory'])==folder/'workspace'
    run_id=api('/api/runs',{'code':'print("Installed Python works")','language':'python'})['id']
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        result=api('/api/runs/'+run_id)
        if result['status']!='running':break
        time.sleep(.1)
    assert 'Installed Python works' in ''.join(event.get('text','') for event in result['events'])
    assert result['events'][-1]['exit_code']==0
    api('/api/shutdown',{})
    server.wait(timeout=10)
    print('PASS: installed bundled Python runs code and saves to installed workspace.',flush=True)
finally:
    if server.poll() is None:server.kill();server.wait()

saved=folder/'workspace'/'main.py'
saved.write_text('print("Keep my saved code")\n',encoding='utf-8')
(folder/'data'/'keep-user-data.txt').write_text('preserve this')
install()
assert saved.read_text(encoding='utf-8')=='print("Keep my saved code")\n'
assert (folder/'data'/'keep-user-data.txt').read_text()=='preserve this'
print('PASS: reinstall/upgrade preserves existing code and app data.',flush=True)

subprocess.run([str(UNINSTALL),'--remove-root',str(folder),'--test'],check=True)
assert not (folder/'Local Code Compiler.exe').exists()
assert not (folder/'Uninstall.exe').exists()
assert not (folder/'.desktop-runtime').exists()
assert not (folder/'.installation.json').exists()
assert saved.read_text(encoding='utf-8')=='print("Keep my saved code")\n'
assert (folder/'data'/'keep-user-data.txt').read_text()=='preserve this'
print('PASS: uninstall removes program files and keeps saved code/data.',flush=True)
print('Installer checks passed. Retained test workspace:',folder,flush=True)
