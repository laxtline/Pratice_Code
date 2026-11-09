## Output-only zoom and no word wrap

- Click the Output panel, then use **Ctrl+=** to enlarge output text, **Ctrl+-** to shrink it, and **Ctrl+0** to reset it to 14 px.
- Editor text and the page layout stay unchanged when using Output's zoom shortcuts.
- Output size is saved independently of the editor and restored after reopening.
- Long editor/output lines scroll horizontally instead of wrapping. Explicit line breaks are preserved.
- The Windows app disables built-in page zoom so it cannot intercept Output's shortcuts.

These changes are included in the local web source, portable EXE and Windows installer. Existing installed code files are preserved by the upgrade.

### Verification

Verified zoom in/out/reset, editor independence, font-size persistence after refresh, and long-line scrolling in the browser. Verified the same shortcuts in the actual rebuilt Windows app. Installer install/reinstall/uninstall tests passed. The installed update preserved all 18 saved source files.

### Downloads

- **Local-Code-Compiler-Setup.exe** — recommended installer/updater.
- **Local-Code-Compiler.exe** — portable Windows app.
- **Local-Code-Compiler-Windows-x64.zip** — both EXEs, guide and notices.
- **SHA256SUMS.txt** — release checksums.

Windows x64, .NET Framework 4.7.2+ and Microsoft Edge WebView2 are required. Python is bundled; other execution languages may require their corresponding installed runtimes.

GitHub package: `com.github.laxtline:pratice-code-editor-windows:1.2.0`.
