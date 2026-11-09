using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("Local Code Compiler Setup")]
[assembly: AssemblyDescription("Offline Windows app installer")]
[assembly: AssemblyVersion("1.2.0.0")]

internal sealed class InstallationRecord
{
    public string app {get;set;}
    public string version {get;set;}
    public string root {get;set;}
    public bool registered {get;set;}
    public bool desktop {get;set;}
    public string[] files {get;set;}
}

internal static class Setup
{
    internal const string AppName = "Local Code Compiler";
    internal const string AppId = "LocalCodeCompiler";
    internal const string Version = "1.2.0";
    internal const string ExeName = "Local Code Compiler.exe";
    internal const string RegistryPath = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\LocalCodeCompiler";
    internal static string SourceHome = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
    internal static string DefaultFolder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", AppId);
    internal static JavaScriptSerializer Json = new JavaScriptSerializer();

    [STAThread]
    private static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        try
        {
#if UNINSTALLER
            string root = Option(args, "--remove-root", null);
            bool test = Array.IndexOf(args,"--test") >= 0;
            if (root != null) { Remove(root, test); return 0; }
            root = SourceHome;
            ReadManifest(root);
            if (MessageBox.Show("Uninstall Local Code Compiler?\n\nYour saved code in the workspace folder and app data will be kept.", AppName, MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return 0;
            RequireClosed(root);
            string temporary = Path.Combine(Path.GetTempPath(), "LocalCodeCompiler-Uninstall-" + Guid.NewGuid().ToString("N") + ".exe");
            File.Copy(Assembly.GetExecutingAssembly().Location, temporary);
            Process.Start(new ProcessStartInfo(temporary, "--remove-root \"" + root + "\"") { UseShellExecute = true });
            return 0;
#else
            if (Array.IndexOf(args,"--silent") >= 0)
            {
                string root = Option(args,"--target",null);
                if (root == null) throw new ArgumentException("Silent installation requires --target.");
                bool test = Array.IndexOf(args,"--test") >= 0;
                Install(root, !test, !test, Array.IndexOf(args,"--import-code") >= 0, delegate(int p) {});
                return 0;
            }
            Application.Run(new SetupForm());
            return 0;
#endif
        }
        catch (Exception error)
        {
            if (Array.IndexOf(args,"--silent") < 0 && Array.IndexOf(args,"--test") < 0)
                MessageBox.Show(error.Message,"Setup could not finish",MessageBoxButtons.OK,MessageBoxIcon.Error);
            try { File.WriteAllText(Path.Combine(Path.GetTempPath(),"LocalCodeCompiler-Setup-error.log"),error.ToString()); } catch {}
            return 1;
        }
    }

    internal static string Option(string[] args, string name, string fallback)
    {
        int index=Array.IndexOf(args,name);
        return index>=0 && index+1<args.Length ? args[index+1] : fallback;
    }
    internal static string RootPath(string folder)
    {
        string root=Path.GetFullPath(folder).TrimEnd(Path.DirectorySeparatorChar);
        if (root.Length < 5 || root.Equals(Path.GetPathRoot(root).TrimEnd(Path.DirectorySeparatorChar),StringComparison.OrdinalIgnoreCase))
            throw new IOException("Choose a dedicated application folder.");
        return root;
    }
    internal static string Inside(string root, string relative)
    {
        string file=Path.GetFullPath(Path.Combine(root,relative.Replace('/',Path.DirectorySeparatorChar)));
        if (!file.StartsWith(root+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)) throw new IOException("Invalid installation file path.");
        return file;
    }
    internal static void RequireClosed(string root)
    {
        foreach (Process process in Process.GetProcessesByName("Local Code Compiler"))
        {
            try { if (String.Equals(process.MainModule.FileName,Path.Combine(root,ExeName),StringComparison.OrdinalIgnoreCase))
                throw new IOException("Close Local Code Compiler before installing or uninstalling, then try again."); }
            catch (Win32Exception) {} catch (InvalidOperationException) {}
            finally { process.Dispose(); }
        }
    }

    internal static void Extract(ZipArchive zip, string root, string prefix, List<string> files, Action<int> progress, int start, int end)
    {
        int i=0;
        foreach (ZipArchiveEntry entry in zip.Entries)
        {
            if (entry.Name.Length==0) continue;
            string relative=prefix+entry.FullName;
            string file=Inside(root,relative);
            Directory.CreateDirectory(Path.GetDirectoryName(file));
            using (Stream input=entry.Open()) using (FileStream output=File.Create(file)) input.CopyTo(output);
            files.Add(relative.Replace('\\','/'));
            i++;
            progress(start+(end-start)*i/Math.Max(1,zip.Entries.Count));
        }
    }
    internal static void Install(string folder, bool register, bool desktop, bool importCode, Action<int> progress)
    {
        string root=RootPath(folder);
        RequireClosed(root);
        if (Directory.Exists(root) && Directory.EnumerateFileSystemEntries(root).Any() && !File.Exists(Path.Combine(root,".installation.json")))
            throw new IOException("This folder already contains other files. Choose an empty folder or the existing Local Code Compiler installation.");
        string[] previousFiles=File.Exists(Path.Combine(root,".installation.json"))?ReadManifest(root).files:new string[0];
        Directory.CreateDirectory(root);
        List<string> files=new List<string>();
        using (Stream payload=Assembly.GetExecutingAssembly().GetManifestResourceStream("setup.zip"))
        {
            if (payload==null) throw new IOException("The installer content is missing.");
            using (ZipArchive zip=new ZipArchive(payload,ZipArchiveMode.Read)) Extract(zip,root,"",files,progress,0,35);
        }
        string app=Path.Combine(root,ExeName);
        Assembly package=Assembly.ReflectionOnlyLoadFrom(app);
        string version;
        using (StreamReader reader=new StreamReader(package.GetManifestResourceStream("payload.sha256"))) version=reader.ReadToEnd().Trim();
        string runtimePrefix=".desktop-runtime/"+version.Substring(0,16)+"/";
        using (Stream payload=package.GetManifestResourceStream("payload.zip"))
        using (ZipArchive zip=new ZipArchive(payload,ZipArchiveMode.Read)) Extract(zip,root,runtimePrefix,files,progress,35,90);
        string marker=runtimePrefix+".ready";
        File.WriteAllText(Inside(root,marker),version);
        files.Add(marker);
        foreach(string previous in previousFiles)if(!files.Contains(previous))files.Add(previous);
        // Code is copied from the local source folder only at installation time.
        // No user's source files or database are embedded in the installer.
        string sourceWorkspace=Path.Combine(SourceHome,"workspace");
        string workspace=Path.Combine(root,"workspace");
        Directory.CreateDirectory(workspace);
        if (importCode && Directory.Exists(sourceWorkspace) && !String.Equals(Path.GetFullPath(sourceWorkspace),workspace,StringComparison.OrdinalIgnoreCase))
            foreach (string file in Directory.GetFiles(sourceWorkspace))
            {
                string destination=Path.Combine(workspace,Path.GetFileName(file));
                if (!File.Exists(destination)) File.Copy(file,destination);
            }
        Dictionary<string,object> manifest=new Dictionary<string,object> {
            {"app",AppId},{"version",Version},{"root",root},{"registered",register},{"desktop",desktop},{"files",files.ToArray()}
        };
        File.WriteAllText(Path.Combine(root,".installation.json"),Json.Serialize(manifest),Encoding.UTF8);
        if (register)
        {
            using (RegistryKey key=Registry.CurrentUser.CreateSubKey(RegistryPath))
            {
                key.SetValue("DisplayName",AppName); key.SetValue("DisplayVersion",Version); key.SetValue("Publisher","Local Tools");
                key.SetValue("InstallLocation",root); key.SetValue("DisplayIcon",app+",0");
                key.SetValue("UninstallString","\""+Path.Combine(root,"Uninstall.exe")+"\"");
                key.SetValue("NoModify",1,RegistryValueKind.DWord); key.SetValue("NoRepair",1,RegistryValueKind.DWord);
                key.SetValue("EstimatedSize",(int)(files.Where(file=>File.Exists(Inside(root,file))).Sum(file=>new FileInfo(Inside(root,file)).Length)/1024),RegistryValueKind.DWord);
            }
            string menu=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs),AppName);
            Directory.CreateDirectory(menu);
            Shortcut(Path.Combine(menu,AppName+".lnk"),app,root);
            Shortcut(Path.Combine(menu,"Uninstall "+AppName+".lnk"),Path.Combine(root,"Uninstall.exe"),root);
            if (desktop) Shortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),AppName+".lnk"),app,root);
        }
        progress(100);
    }

    internal static void Shortcut(string path, string target, string root)
    {
        Type shellType=Type.GetTypeFromProgID("WScript.Shell");
        object shell=Activator.CreateInstance(shellType);
        object link=null;
        try
        {
            link=shellType.InvokeMember("CreateShortcut",BindingFlags.InvokeMethod,null,shell,new object[]{path});
            Type type=link.GetType();
            type.InvokeMember("TargetPath",BindingFlags.SetProperty,null,link,new object[]{target});
            type.InvokeMember("WorkingDirectory",BindingFlags.SetProperty,null,link,new object[]{root});
            type.InvokeMember("IconLocation",BindingFlags.SetProperty,null,link,new object[]{Path.Combine(root,ExeName)+",0"});
            type.InvokeMember("Description",BindingFlags.SetProperty,null,link,new object[]{AppName+" — local code editor and compiler"});
            type.InvokeMember("Save",BindingFlags.InvokeMethod,null,link,null);
        }
        finally { if(link!=null)Marshal.FinalReleaseComObject(link); Marshal.FinalReleaseComObject(shell); }
    }
    internal static InstallationRecord ReadManifest(string root)
    {
        root=RootPath(root);
        string path=Path.Combine(root,".installation.json");
        if (!File.Exists(path)) throw new IOException("The installation record is missing. No files were removed.");
        InstallationRecord manifest=Json.Deserialize<InstallationRecord>(File.ReadAllText(path));
        if (manifest==null || manifest.app!=AppId || manifest.files==null || !String.Equals(manifest.root,root,StringComparison.OrdinalIgnoreCase))
            throw new IOException("The installation record does not match this folder. No files were removed.");
        return manifest;
    }
    internal static void Remove(string folder, bool test)
    {
        string root=RootPath(folder);
        InstallationRecord manifest=ReadManifest(root);
        RequireClosed(root);
        string[] files=manifest.files;
        // Verify every recorded path before deleting any program file.
        foreach (string file in files)
        {
            Inside(root,file);
            if (file.StartsWith("workspace/",StringComparison.OrdinalIgnoreCase) || file.StartsWith("data/",StringComparison.OrdinalIgnoreCase))
                throw new IOException("The installation record includes user data. No files were removed.");
        }
        foreach (string file in files) { string path=Inside(root,file); if(File.Exists(path))File.Delete(path); }
        string runtime=Inside(root,".desktop-runtime");
        if(Directory.Exists(runtime))
        {
            foreach(string cache in Directory.GetFiles(runtime,"*.pyc",SearchOption.AllDirectories))File.Delete(cache);
            foreach(string directory in Directory.GetDirectories(runtime,"*",SearchOption.AllDirectories).OrderByDescending(path=>path.Length))
                if(!Directory.EnumerateFileSystemEntries(directory).Any())Directory.Delete(directory);
            if(!Directory.EnumerateFileSystemEntries(runtime).Any())Directory.Delete(runtime);
        }
        if (!test && manifest.registered)
        {
            using(RegistryKey key=Registry.CurrentUser.OpenSubKey(RegistryPath))
            { if(key!=null && String.Equals((string)key.GetValue("InstallLocation"),root,StringComparison.OrdinalIgnoreCase))Registry.CurrentUser.DeleteSubKeyTree(RegistryPath); }
            string menu=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs),AppName);
            foreach(string name in new[]{AppName+".lnk","Uninstall "+AppName+".lnk"})RemoveShortcut(Path.Combine(menu,name),root);
            if(Directory.Exists(menu) && !Directory.EnumerateFileSystemEntries(menu).Any())Directory.Delete(menu);
            if(manifest.desktop)RemoveShortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),AppName+".lnk"),root);
        }
        File.Delete(Path.Combine(root,".installation.json"));
        if(!Directory.EnumerateFileSystemEntries(root).Any())Directory.Delete(root);
        if(!test)MessageBox.Show("Local Code Compiler was uninstalled.\n\nYour saved code and app data remain in:\n"+root,AppName,MessageBoxButtons.OK,MessageBoxIcon.Information);
    }
    internal static void RemoveShortcut(string path,string root)
    {
        if(!File.Exists(path))return;
        Type type=Type.GetTypeFromProgID("WScript.Shell");object shell=Activator.CreateInstance(type);object link=null;
        try { link=type.InvokeMember("CreateShortcut",BindingFlags.InvokeMethod,null,shell,new object[]{path});
            string target=(string)link.GetType().InvokeMember("TargetPath",BindingFlags.GetProperty,null,link,null);
            if(target.StartsWith(root+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))File.Delete(path);
        }finally{if(link!=null)Marshal.FinalReleaseComObject(link);Marshal.FinalReleaseComObject(shell);}
    }
}

#if !UNINSTALLER
internal sealed class SetupForm:Form
{
    TextBox folder;Button browse,install;CheckBox desktop,launch,import;ProgressBar progress;Label status;bool busy,finished;
    internal SetupForm()
    {
        Text="Local Code Compiler Setup";ClientSize=new Size(640,470);FormBorderStyle=FormBorderStyle.FixedDialog;
        MaximizeBox=false;StartPosition=FormStartPosition.CenterScreen;BackColor=Color.FromArgb(28,34,48);ForeColor=Color.White;Font=new Font("Segoe UI",10);
        Icon=Icon.ExtractAssociatedIcon(Assembly.GetExecutingAssembly().Location);
        Controls.Add(new Label{Text="Local Code Compiler",Font=new Font("Segoe UI",23,FontStyle.Bold),Location=new Point(28,24),Size=new Size(585,48)});
        Controls.Add(new Label{Text="Install your offline Windows coding app",ForeColor=Color.LightSteelBlue,Location=new Point(31,79),Size=new Size(580,26)});
        Controls.Add(new Label{Text="Includes Python, the editor, live preview and app files.\nYour code stays in local files. Existing saved code is preserved.",Location=new Point(31,118),Size=new Size(580,52)});
        Controls.Add(new Label{Text="Installation folder",Location=new Point(31,186),Size=new Size(560,23)});
        folder=new TextBox{Text=Setup.DefaultFolder,Location=new Point(31,213),Size=new Size(463,28)};Controls.Add(folder);
        browse=new Button{Text="Browse…",Location=new Point(504,210),Size=new Size(104,32)};Controls.Add(browse);
        browse.Click+=delegate{using(FolderBrowserDialog dialog=new FolderBrowserDialog{Description="Choose a dedicated application folder",SelectedPath=folder.Text})if(dialog.ShowDialog(this)==DialogResult.OK)folder.Text=dialog.SelectedPath;};
        desktop=new CheckBox{Text="Create a Desktop shortcut",Checked=true,Location=new Point(31,260),Size=new Size(570,24)};Controls.Add(desktop);
        import=new CheckBox{Text="Keep code from the current local workspace, if found",Checked=true,Location=new Point(31,291),Size=new Size(570,24)};Controls.Add(import);
        launch=new CheckBox{Text="Open Local Code Compiler after installation",Checked=true,Location=new Point(31,322),Size=new Size(570,24)};Controls.Add(launch);
        progress=new ProgressBar{Location=new Point(31,367),Size=new Size(577,9)};Controls.Add(progress);
        status=new Label{Text="Installs for your Windows account. Start Menu and uninstall included.\nNo administrator access or internet download needed.",ForeColor=Color.LightSteelBlue,Location=new Point(31,394),Size=new Size(432,55),Font=new Font("Segoe UI",9)};Controls.Add(status);
        install=new Button{Text="Install",Location=new Point(495,401),Size=new Size(113,37),BackColor=Color.FromArgb(5,86,243),ForeColor=Color.White,FlatStyle=FlatStyle.Flat};Controls.Add(install);install.Click+=ClickInstall;
        FormClosing+=delegate(object s,FormClosingEventArgs e){if(busy)e.Cancel=true;};
    }
    private void ClickInstall(object sender,EventArgs args)
    {
        if(finished){Close();return;}
        string destination;try{destination=Setup.RootPath(folder.Text);}catch(Exception error){MessageBox.Show(this,error.Message);return;}
        bool makeDesktop=desktop.Checked,open=launch.Checked,keep=import.Checked;
        busy=true;install.Enabled=browse.Enabled=folder.Enabled=desktop.Enabled=launch.Enabled=import.Enabled=false;
        status.Text="Installing the Windows app and its bundled runtime…";
        BackgroundWorker worker=new BackgroundWorker{WorkerReportsProgress=true};
        worker.DoWork+=delegate{Setup.Install(destination,true,makeDesktop,keep,p=>worker.ReportProgress(p));};
        worker.ProgressChanged+=delegate(object s,ProgressChangedEventArgs e){progress.Value=Math.Min(100,e.ProgressPercentage);};
        worker.RunWorkerCompleted+=delegate(object s,RunWorkerCompletedEventArgs e)
        {
            busy=false;install.Enabled=true;
            if(e.Error!=null){status.Text="Installation did not finish.";MessageBox.Show(this,e.Error.Message,"Setup",MessageBoxButtons.OK,MessageBoxIcon.Error);browse.Enabled=folder.Enabled=desktop.Enabled=launch.Enabled=import.Enabled=true;return;}
            progress.Value=100;finished=true;install.Text="Finish";status.Text="Installed. Find Local Code Compiler in Start Menu.\nSaved files: "+Path.Combine(destination,"workspace");
            if(open)Process.Start(new ProcessStartInfo(Path.Combine(destination,Setup.ExeName)){WorkingDirectory=destination,UseShellExecute=true});
        };
        worker.RunWorkerAsync();
    }
}
#endif
