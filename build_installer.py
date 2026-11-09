"""Build the offline per-user Windows setup and uninstaller."""
from pathlib import Path
import hashlib
import json
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parent
BUILD=ROOT/'build'/'installer'
CSC=Path(r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe')

def build():
    BUILD.mkdir(parents=True,exist_ok=True)
    common=[str(CSC),'/nologo','/target:winexe','/platform:x64','/optimize+',
        '/r:System.dll','/r:System.Core.dll','/r:System.Drawing.dll','/r:System.Windows.Forms.dll',
        '/r:System.IO.Compression.dll','/r:System.IO.Compression.FileSystem.dll','/r:System.Web.Extensions.dll',
        '/win32icon:'+str(ROOT/'windows'/'app.ico'),'/win32manifest:'+str(ROOT/'windows'/'app.manifest')]
    uninstall=BUILD/'Uninstall.exe'
    subprocess.run(common+['/define:UNINSTALLER','/out:'+str(uninstall),str(ROOT/'windows'/'Installer.cs')],check=True)
    payload=BUILD/'setup.zip'
    with zipfile.ZipFile(payload,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        archive.write(ROOT/'Local Code Compiler.exe','Local Code Compiler.exe')
        archive.write(uninstall,'Uninstall.exe')
        archive.write(ROOT/'INSTALL.txt','INSTALL.txt')
    setup=ROOT/'Local-Code-Compiler-Setup.exe'
    subprocess.run(common+['/out:'+str(setup),'/resource:'+str(payload)+',setup.zip',str(ROOT/'windows'/'Installer.cs')],check=True)
    report={'installer':str(setup),'version':'1.2.0','size_mb':round(setup.stat().st_size/1048576,2),
        'sha256':hashlib.sha256(setup.read_bytes()).hexdigest(),
        'default_install_folder':r'%LOCALAPPDATA%\Programs\LocalCodeCompiler',
        'includes':['Windows app','Python runtime','editor assets','Desktop and Start Menu shortcuts','Windows uninstall entry','uninstaller'],
        'user_workspace_embedded':False}
    (BUILD/'build.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (ROOT/'Local-Code-Compiler-Setup.sha256').write_text(report['sha256']+'  '+setup.name+'\n',encoding='ascii')
    print(json.dumps(report,indent=2))

if __name__=='__main__':build()
