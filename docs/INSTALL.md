# Installation, upgrades and removal

**English** | [简体中文](INSTALL.zh-CN.md)

## macOS

Download the arm64 DMG, open it and drag the app to Applications. Requires Apple Silicon and macOS 13 or later. The app is named “流量手账” in Finder. Quit the old version from its menu before replacing it.

History is stored in your user `Library/Application Support/流量手账` directory and survives app replacement. The menu's “登录 Mac 后自动记录” option controls login startup. Login startup opens only the menu bar item; closing the main window keeps recording.

To uninstall, disable login startup, quit the app and move it to Trash. History is preserved by default. Use the app's data-folder command to find and back up your records before deleting them yourself.

## Windows

Requires Windows 10/11 x64. Run `FlowLedger-1.5.0-beta.1-Windows-x64-Setup.exe` and confirm installation. It installs into `%LOCALAPPDATA%\Programs\FlowLedger`, creates desktop and Start menu shortcuts named Flow Ledger, and registers an uninstall entry in Windows Settings. No administrator access or separate Python installation is needed.

The app runs in the system tray. Left-click to open the window; right-click for its menu. The login-startup option uses the current user's Startup folder and is disabled by default on first installation.

The window uses system Edge in app mode or falls back to your default browser. It connects only to the app's randomly assigned `127.0.0.1` port. Collection continues when the browser window is closed.

Quit the tray app before upgrading. Run the new installer to replace program files. History lives separately in `%LOCALAPPDATA%\FlowLedger` and is not overwritten by the installer.

To uninstall, quit the tray app and use Windows Settings → Apps → Installed apps → 流量手账. This removes program files and shortcuts, including login startup. Usage history is preserved. The portable ZIP can also be extracted and launched directly; it still stores data in the same user data directory.

## Preview limitations

Both packages lack publisher certificate signatures; the Mac build is ad-hoc signed but not notarized. Your system may warn about or block them. Do not disable system-wide security protections. Publisher signing, notarization and more hardware validation remain future work.
