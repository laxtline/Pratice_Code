# Local Code Compiler

Version 1.2.0 adds independent Output font zoom (click Output, then Ctrl+= / Ctrl+- / Ctrl+0) and disables wrapping for editor/output lines. Long lines scroll horizontally. Output text size is saved separately from the editor.

## Downloads

- [Windows installer](https://github.com/laxtline/Pratice_Code/releases/latest/download/Local-Code-Compiler-Setup.exe)
- [Portable Windows app](https://github.com/laxtline/Pratice_Code/releases/latest/download/Local-Code-Compiler.exe)
- [Offline Windows bundle](https://github.com/laxtline/Pratice_Code/releases/latest/download/Local-Code-Compiler-Windows-x64.zip)
- [Release notes and checksums](https://github.com/laxtline/Pratice_Code/releases/latest)
- [GitHub Packages](https://github.com/users/laxtline/packages?repo_name=Pratice_Code)

## Windows app

### Install like a Windows program

Run **`Local-Code-Compiler-Setup.exe`** and choose **Install**. The default location is `%LOCALAPPDATA%\Programs\LocalCodeCompiler`, matching the per-user Programs folder used by the Practice Code installer. The setup installs the app, embedded Python, frontend assets and worker files, creates Start Menu and optional Desktop shortcuts, and adds a Windows Installed Apps entry with an uninstaller. It does not require administrator access at the default location.

When the setup EXE is beside the existing `workspace`, the import option copies saved source files to the installed app's workspace. Existing installed source files are never overwritten during upgrades. Uninstall removes program files and shortcuts while keeping `workspace` and `data`.

`python build_installer.py` rebuilds Setup using the current native app EXE. `python test_installer.py` verifies installation, bundled execution, importing source files, upgrade preservation and uninstall preservation in an isolated build folder. The setup payload contains no personal workspace code or databases.

Double-click **`Local Code Compiler.exe`**. It opens its own Windows window with the same local editor, terminal, language switching and preview. No browser tab or terminal window is needed. The app includes its own Python 3.14.10 runtime. Code files remain in `workspace` beside the EXE; closing and reopening the app preserves them. The browser version and the Windows app use the same workspace when the EXE stays in this project folder.

The app starts its own loopback server at `127.0.0.1:8123` and stops it when the window closes. F11 toggles full screen. The first launch extracts bundled program files to `.desktop-runtime`; do not edit those extracted files. User code is stored separately in `workspace`, and app settings/logs are in `data`. The EXE is approximately 13 MB. It uses the Microsoft Edge WebView2 and .NET Framework runtimes already installed on this computer. Additional language runtimes such as Node.js are still required for those languages.

Verified: the packaged Python backend passed all nine integration checks; Python code also ran successfully in the actual native app window. Closing the window stopped its backend and preserved the source file bytes.

To rebuild after source edits, run `python build_exe.py --runtime <embedded-python-folder> --webview <folder-with-WebView2-DLLs>`. The native source is `windows/Desktop.cs`; the build includes static assets and worker scripts but never includes your workspace files or saved data.

A local recreation of the Programiz compiler layout and core Python behavior. The entire top logo/title/PRO panel is removed; the editor and output use the full window height. All 18 language choices open in the same tab, show editable starter/saved code, and have separate local source files.

## Start

Double-click `start.cmd`. It starts the server in the background and opens **http://127.0.0.1:8000**. Reusing it does not start a second server. Double-click `stop.cmd` to stop it and all owned code runs.

Or run `python server.py` in this directory. Python 3.10+ is required; no Python dependencies or frontend build is needed. Assets and the CodeMirror editor are included locally. Stop the server with Ctrl+C.

## Features

- Python syntax highlighting, line numbers, indentation, matching/closing brackets, undo/redo, comments and saved editor contents.
- Real local Python execution, streaming output, exceptions, interactive `input()` / `sys.stdin`, Stop and EOF (Ctrl+D).
- Visualize execution with up to 500 trace steps, line highlighting, globals, function call frames, lists, tuples, sets, dictionaries and output at each step. Previous/next, slider and playback controls.
- Dark/light themes, persistent font size and draggable split panes.
- Download a runnable ZIP, open a `.py` file, reset code, clear output, full screen, mobile editor/output tabs and keyboard shortcuts.
- Saved local code links backed by SQLite. Links remain available after restarting the server and work on this computer only.
- Automatic saving to real source files in the app's local `workspace/` directory (500 ms after editing, also before switching or running). Ctrl+S saves the current source file. Each language restores its saved code when revisited. You can edit these files in an external editor, then reload or switch languages to load those changes.
- All language choices switch within the current tab. Python, JavaScript (Node.js), TypeScript (Node.js native type stripping), SQL (SQLite), and HTML/CSS with inline JavaScript live preview work using the runtimes already installed on this computer.
- Local runtime adapters for R, Java, Kotlin, C, C++, C#, Go, Rust, Scala, Dart, Ruby, PHP and Swift. Their code editing, highlighting, saving and download work; execution requires the matching compiler/interpreter on PATH. Missing runtimes are identified clearly in the output. Restart the server after installing one. No external compiler service is used.

PRO subscriptions, advertising, external support and Programiz's private server implementation are not reproduced. The frontend and execution backend are independent implementations. The original public language icons are retained for visual matching; CodeMirror's license is in `static/vendor/CODEMIRROR-LICENSE`. No top promotional header is displayed, and selecting a language never opens Programiz or another tab.

## Execution model

This is a **personal local tool**, not a hosted code execution service. Programs run in a temporary working directory with your Windows account's permissions and can access local files and networks. Isolation flags do not provide a security sandbox. Do not expose this server to other users or run untrusted code. The server binds only to `127.0.0.1`, validates Host/Origin, and requires a custom header for changes.

Runs stop after 20 seconds of active execution, waiting for interactive input is limited to 10 minutes, output is limited to 1 MB, and at most four programs run concurrently. Stop terminates the owned process tree. The tracer previews supported builtin containers; it does not emulate Python Tutor heap identity, arbitrary custom object internals, native extensions or threads.

SQL uses a fresh in-memory SQLite database for each run and displays the first 1000 rows of each result. HTML preview uses a sandboxed iframe. TypeScript uses Node's native type stripping, so TypeScript syntax requiring transpilation (such as enums) needs a separate compiler. Non-Python terminals accept input while a program runs; the 20-second wall deadline includes their input wait.

## Verification

Run `python test_server.py` while the server is running. Nine integration checks cover real Python/JS/TS/SQL execution, Unicode, input/EOF, syntax/runtime errors, Stop/timeout/output limits, trace call frames, local disk saving, sharing, ZIP export, static assets and cross-origin request rejection. Browser checks also cover the header-free layout, same-tab switching, file restoration, interactive Python input, visualization and the HTML preview button.

## GitHub Packages

The Maven package is `com.github.laxtline:pratice-code-editor-windows:1.2.0` with type `exe`. It contains the same Windows installer as the release. GitHub Packages requires authentication for Maven downloads.

## Source checkout

The checkout includes the browser app, Windows sources and executables, build scripts, and tests. The app creates a fresh workspace and database on first launch. Installed frontend dependencies can be restored with `npm ci --prefix frontend-deps` when refreshing the bundled CodeMirror assets.
