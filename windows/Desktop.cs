using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

[assembly: AssemblyTitle("Local Code Compiler")]
[assembly: AssemblyDescription("Offline local code editor, compiler and live preview")]
[assembly: AssemblyCompany("Local Tools")]
[assembly: AssemblyProduct("Local Code Compiler")]
[assembly: AssemblyVersion("1.2.0.0")]

internal static class Program
{
    internal static string Home;
    internal static string Runtime;
    private static Mutex singleton;
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern bool SetDllDirectory(string path);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr FindWindow(string className, string title);
    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr handle);
    [DllImport("user32.dll")]
    private static extern bool ShowWindow(IntPtr handle, int command);

    [STAThread]
    private static void Main()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Home = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        try
        {
            string identity;
            using (SHA256 sha = SHA256.Create())
                identity = BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(Home.ToLowerInvariant()))).Replace("-", "").Substring(0, 16);
            bool created;
            singleton = new Mutex(true, "Local\\LocalCodeCompiler-" + identity, out created);
            if (!created)
            {
                IntPtr existing = FindWindow(null, "Local Code Compiler");
                if (existing != IntPtr.Zero) { ShowWindow(existing, 9); SetForegroundWindow(existing); }
                return;
            }
            PrepareRuntime();
            SetDllDirectory(Runtime);
            AppDomain.CurrentDomain.AssemblyResolve += delegate(object sender, ResolveEventArgs args)
            {
                string name = new AssemblyName(args.Name).Name;
                if (!name.StartsWith("Microsoft.Web.WebView2.", StringComparison.Ordinal)) return null;
                string file = Path.Combine(Runtime, name + ".dll");
                return File.Exists(file) ? Assembly.LoadFrom(file) : null;
            };
            RunWindow();
        }
        catch (Exception error)
        {
            try { Directory.CreateDirectory(Path.Combine(Home, "data")); File.WriteAllText(Path.Combine(Home, "data", "desktop-error.log"), error.ToString()); } catch { }
            MessageBox.Show("The app could not start.\n\n" + error.Message + "\n\nKeep this EXE in a writable folder. Details are in data\\desktop-error.log.", "Local Code Compiler", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally { if (singleton != null) singleton.Dispose(); }
    }

    private static void PrepareRuntime()
    {
        Assembly assembly = Assembly.GetExecutingAssembly();
        string version;
        using (StreamReader reader = new StreamReader(assembly.GetManifestResourceStream("payload.sha256"))) version = reader.ReadToEnd().Trim();
        Runtime = Path.Combine(Home, ".desktop-runtime", version.Substring(0, 16));
        string marker = Path.Combine(Runtime, ".ready");
        if (File.Exists(marker) && File.ReadAllText(marker).Trim() == version) return;
        Directory.CreateDirectory(Runtime);
        using (Stream stream = assembly.GetManifestResourceStream("payload.zip"))
        using (ZipArchive zip = new ZipArchive(stream, ZipArchiveMode.Read))
        {
            foreach (ZipArchiveEntry entry in zip.Entries)
            {
                string file = Path.GetFullPath(Path.Combine(Runtime, entry.FullName));
                if (!file.StartsWith(Path.GetFullPath(Runtime) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("Invalid bundled path.");
                Directory.CreateDirectory(Path.GetDirectoryName(file));
                if (entry.Name.Length > 0)
                    using (Stream input = entry.Open())
                    using (FileStream output = File.Create(file)) input.CopyTo(output);
            }
        }
        File.WriteAllText(marker, version);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void RunWindow() { Application.Run(new CompilerWindow()); }
}

internal sealed class CompilerWindow : Form
{
    private WebView2 browser;
    private Process server;
    private string serverUrl;
    private readonly Label loading;
    private bool closing;
    private bool canClose;
    private bool fullscreen;
    private Rectangle savedBounds;
    private FormWindowState savedState;
    private TaskCompletionSource<bool> savedForClose;
    private Task<string> serverStartTask;
    private readonly string dataFolder;
    private readonly object logLock = new object();

    internal CompilerWindow()
    {
        Text = "Local Code Compiler";
        BackColor = Color.FromArgb(31, 32, 35);
        ForeColor = Color.White;
        MinimumSize = new Size(760, 500);
        Size = new Size(1280, 820);
        StartPosition = FormStartPosition.CenterScreen;
        WindowState = FormWindowState.Maximized;
        Icon = Icon.ExtractAssociatedIcon(Assembly.GetExecutingAssembly().Location);
        dataFolder = Path.Combine(Program.Home, "data");
        Directory.CreateDirectory(dataFolder);
        loading = new Label { Dock = DockStyle.Fill, Text = "Starting Local Code Compiler…", TextAlign = ContentAlignment.MiddleCenter, Font = new Font("Segoe UI", 14) };
        Controls.Add(loading);
        Shown += StartApp;
        FormClosing += CloseApp;
    }

    private void Log(string text)
    {
        if (String.IsNullOrEmpty(text)) return;
        lock (logLock) { try { File.AppendAllText(Path.Combine(dataFolder, "desktop.log"), text + Environment.NewLine); } catch { } }
    }

    private async void StartApp(object sender, EventArgs args)
    {
        try
        {
            serverStartTask = Task.Run(() => StartServer());
            serverUrl = await serverStartTask;
            if (closing) return;
            browser = new WebView2 { Dock = DockStyle.Fill, DefaultBackgroundColor = BackColor };
            Controls.Add(browser);
            browser.BringToFront();
            CoreWebView2Environment environment = await CoreWebView2Environment.CreateAsync(null, Path.Combine(dataFolder, "webview"));
            await browser.EnsureCoreWebView2Async(environment);
            browser.CoreWebView2.Settings.IsStatusBarEnabled = false;
            browser.CoreWebView2.Settings.IsZoomControlEnabled = false;
            browser.CoreWebView2.Settings.AreDefaultContextMenusEnabled = true;
            browser.CoreWebView2.WebMessageReceived += delegate(object s, CoreWebView2WebMessageReceivedEventArgs e)
            {
                string message = e.TryGetWebMessageAsString();
                if (message == "saved-for-close" && savedForClose != null) savedForClose.TrySetResult(true);
                if (message == "fullscreen-toggle") BeginInvoke((Action)(() => SetFullscreen(!fullscreen)));
                if (message == "fullscreen-exit") BeginInvoke((Action)(() => SetFullscreen(false)));
            };
            browser.CoreWebView2.NewWindowRequested += delegate(object s, CoreWebView2NewWindowRequestedEventArgs e)
            {
                e.Handled = true;
                if (e.Uri.StartsWith(serverUrl, StringComparison.OrdinalIgnoreCase)) browser.CoreWebView2.Navigate(e.Uri);
                else if (e.Uri.StartsWith("https://", StringComparison.OrdinalIgnoreCase)) Process.Start(new ProcessStartInfo(e.Uri) { UseShellExecute = true });
            };
            browser.CoreWebView2.ContainsFullScreenElementChanged += delegate { SetFullscreen(browser.CoreWebView2.ContainsFullScreenElement); };
            await browser.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync("document.addEventListener('keydown',e=>{if(e.key==='F11'){e.preventDefault();chrome.webview.postMessage('fullscreen-toggle');}if(e.key==='Escape')chrome.webview.postMessage('fullscreen-exit');},true);");
            browser.CoreWebView2.NavigationCompleted += delegate { loading.Visible = false; };
            browser.CoreWebView2.Navigate(serverUrl + "/?lang=python");
            File.WriteAllText(Path.Combine(dataFolder, "desktop-session.json"), "{\"state\":\"ready\",\"pid\":" + Process.GetCurrentProcess().Id + ",\"serverPid\":" + server.Id + ",\"url\":\"" + serverUrl + "\"}");
        }
        catch (Exception error)
        {
            Log(error.ToString());
            loading.Text = "Could not start the desktop window.\n\n" + error.Message + "\n\nSee data\\desktop.log.";
            ThreadPool.QueueUserWorkItem(delegate { StopServer(); });
        }
    }

    private string StartServer()
    {
        ProcessStartInfo info = new ProcessStartInfo(Path.Combine(Program.Runtime, "python.exe"));
        info.Arguments = "-u \"" + Path.Combine(Program.Runtime, "server.py") + "\" --port 8123";
        info.WorkingDirectory = Program.Home;
        info.UseShellExecute = false;
        info.CreateNoWindow = true;
        info.RedirectStandardOutput = true;
        info.RedirectStandardError = true;
        info.EnvironmentVariables["LOCAL_COMPILER_HOME"] = Program.Home;
        info.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
        info.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
        server = new Process { StartInfo = info };
        server.ErrorDataReceived += delegate(object s, DataReceivedEventArgs e) { Log(e.Data); };
        server.Start();
        server.BeginErrorReadLine();
        Task<string> firstLine = server.StandardOutput.ReadLineAsync();
        if (!firstLine.Wait(15000)) throw new TimeoutException("The local server did not start within 15 seconds.");
        string line = firstLine.Result;
        Log(line);
        const string prefix = "Local Python compiler: ";
        if (line == null || !line.StartsWith(prefix, StringComparison.Ordinal)) throw new InvalidOperationException("The local server could not start.");
        string url = line.Substring(prefix.Length).Trim();
        Task.Run(async delegate { while (!server.HasExited) { string output = await server.StandardOutput.ReadLineAsync(); if (output == null) break; Log(output); } });
        return url;
    }

    private void SetFullscreen(bool value)
    {
        if (fullscreen == value) return;
        fullscreen = value;
        if (value) { savedBounds = Bounds; savedState = WindowState; WindowState = FormWindowState.Normal; FormBorderStyle = FormBorderStyle.None; Bounds = Screen.FromControl(this).Bounds; }
        else { FormBorderStyle = FormBorderStyle.Sizable; Bounds = savedBounds; WindowState = savedState; }
    }

    private async void CloseApp(object sender, FormClosingEventArgs args)
    {
        if (canClose) return;
        args.Cancel = true;
        if (closing) return;
        closing = true;
        try
        {
            if (serverStartTask != null && !serverStartTask.IsCompleted) await Task.WhenAny(serverStartTask, Task.Delay(16000));
            if (browser != null && browser.CoreWebView2 != null)
            {
                savedForClose = new TaskCompletionSource<bool>();
                await browser.CoreWebView2.ExecuteScriptAsync("(async()=>{try{if(typeof saveLocal==='function')await saveLocal();}finally{chrome.webview.postMessage('saved-for-close');}})()");
                await Task.WhenAny(savedForClose.Task, Task.Delay(3000));
            }
            await Task.Run(() => StopServer());
            if (browser != null) browser.Dispose();
            File.WriteAllText(Path.Combine(dataFolder, "desktop-session.json"), "{\"state\":\"closed\"}");
        }
        catch (Exception error) { Log(error.ToString()); }
        finally { canClose = true; Close(); }
    }

    private void StopServer()
    {
        if (server == null) return;
        try
        {
            if (!server.HasExited && serverUrl != null)
            {
                HttpWebRequest request = (HttpWebRequest)WebRequest.Create(serverUrl + "/api/shutdown");
                request.Method = "POST";
                request.ContentType = "application/json";
                request.Headers["X-Local-Compiler"] = "1";
                request.ContentLength = 2;
                request.Timeout = 3000;
                using (Stream stream = request.GetRequestStream()) { byte[] data = Encoding.UTF8.GetBytes("{}"); stream.Write(data, 0, data.Length); }
                using (WebResponse response = request.GetResponse()) { }
            }
            if (!server.HasExited && !server.WaitForExit(5000)) server.Kill();
        }
        catch (Exception error) { Log(error.ToString()); try { if (!server.HasExited) server.Kill(); } catch { } }
    }
}
