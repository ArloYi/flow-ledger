# Development and validation

**English** | [简体中文](DEVELOPMENT.zh-CN.md)

No npm or pip packages are required. The shared core uses the Python standard library, the Mac shell uses Swift/AppKit, and the Windows shell and installer use Go/Win32.

## Tests

With Python 3.9 or later:

```sh
python3 scripts/test.py
python3 scripts/privacy_scan.py . --source
```

The Mac test suite covers 24 accounting, network-boundary, speed-test and native-structure checks. Windows skips Mac-specific fixtures and the POSIX parent-process test; its CI job builds and exercises installation, the bundled runtime/native collector, and uninstallation. These checks do not establish real hotspot handovers, midnight transitions or every VPN combination.

## Build for Mac

Use an Apple Silicon Mac with Xcode Command Line Tools and Python 3.12+ (the download script uses safe tar extraction APIs).

```sh
python3 scripts/fetch_runtime.py macos --dest .build/macos
python3 scripts/build_macos.py --runtime .build/macos/python
```

Outputs `dist/流量手账.app` and an arm64 DMG with a bundled runtime. The build script applies ad-hoc signatures only. A production distribution needs a Developer ID and notarization.

## Build for Windows

Use Go 1.25+ and Python 3.12+ on Windows or Mac:

```sh
python3 scripts/fetch_runtime.py windows --dest .build/windows
python3 scripts/build_windows.py --runtime .build/windows --icon docs/icon.png
```

Outputs an x64 Setup EXE and portable ZIP. Both use the same verified Python embeddable runtime and shared core. The installer embeds the ZIP and never reads the developer's database or settings.

Windows collection uses `GetIfTable2` hardware adapter byte counters, plus routing and neighbor tables for gateway identity. IPv6-only or unavailable gateway identities remain unclassified. The tray uses Win32 APIs; the window uses Edge app mode.

## Run from source

```sh
python3 app/core/server.py --open --data-dir .data
```

Requires physical adapter access on Mac or Windows. This mode starts collection and a browser page, without the native tray shell. Do not commit `.data` or exported personal records.

## Privacy review

`privacy_scan.py` accepts `--known-private private-values.json`, an external JSON array of strings to reject. It reports only matched rule types and filenames. Keep that file outside the source tree. Also review the Git file list, commit metadata and extracted packages before publishing.
