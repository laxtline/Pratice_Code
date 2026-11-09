"""Bundle the existing embedded Python runtime and build a native WinForms EXE."""
from pathlib import Path
import argparse
import hashlib
import shutil
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parent
BUILD=ROOT/'build'/'desktop'

def build(runtime, webview):
    BUILD.mkdir(parents=True,exist_ok=True)
    payload=BUILD/'payload.zip'
    with zipfile.ZipFile(payload,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for file in sorted(runtime.iterdir()):
            if file.is_file():
                archive.write(file,file.name)
        for name in ('server.py','worker.py','polyglot_worker.py','languages.py'):
            archive.write(ROOT/name,name)
        for file in sorted((ROOT/'static').rglob('*')):
            if file.is_file():archive.write(file,file.relative_to(ROOT).as_posix())
        for name in ('Microsoft.Web.WebView2.Core.dll','Microsoft.Web.WebView2.WinForms.dll','WebView2Loader.dll'):
            archive.write(webview/name,name)
        license=webview/'windows'/'WebView2-LICENSE.txt'
        if license.exists():archive.write(license,'WEBVIEW2-LICENSE.txt')
    digest=hashlib.sha256(payload.read_bytes()).hexdigest()
    digest_file=BUILD/'payload.sha256'
    digest_file.write_text(digest)
    output=ROOT/'Local Code Compiler.exe'
    compiler=Path(r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe')
    command=[str(compiler),'/nologo','/target:winexe','/platform:x64','/optimize+',
             '/out:'+str(output),'/win32manifest:'+str(ROOT/'windows'/'app.manifest'),
             '/resource:'+str(payload)+',payload.zip','/resource:'+str(digest_file)+',payload.sha256',
             '/r:System.dll','/r:System.Core.dll','/r:System.Drawing.dll','/r:System.Windows.Forms.dll',
             '/r:System.IO.Compression.dll','/r:System.IO.Compression.FileSystem.dll',
             '/r:'+str(webview/'Microsoft.Web.WebView2.Core.dll'),
             '/r:'+str(webview/'Microsoft.Web.WebView2.WinForms.dll'),str(ROOT/'windows'/'Desktop.cs')]
    icon=ROOT/'windows'/'app.ico'
    if icon.exists():command.insert(-1,'/win32icon:'+str(icon))
    subprocess.run(command,check=True)
    print('Built:',output)
    print('Size:',round(output.stat().st_size/1024/1024,1),'MB')
    print('Payload SHA256:',digest)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--webview',type=Path,required=True)
    args=parser.parse_args()
    build(args.runtime.resolve(),args.webview.resolve())
