# Flow Ledger

**English** | [简体中文](README.zh-CN.md)

A small menu bar and system tray app that tracks network usage on your computer. See today's total, explore minute-by-minute uploads and downloads, and keep Wi-Fi and mobile hotspot usage separate with saved network labels.

**[Download for Mac or Windows](https://github.com/ArloYi/flow-ledger/releases/tag/v1.5.0-beta.1)** · [Installation](docs/INSTALL.md) · [Privacy](docs/PRIVACY.md) · [Development](docs/DEVELOPMENT.md)

## Preview status

Version **1.5.0-beta.1** bundles its Python runtime; no developer tools are needed to use it. The application interface is currently in Simplified Chinese. This repository provides English and Chinese documentation.

The packages do not have publisher certificates or macOS notarization. Your operating system may warn about or block them.

| Platform | Package | Verification |
|---|---|---|
| macOS 13+, Apple Silicon | Drag-to-install `.dmg` | Built and checked on a local Mac; no Intel build yet |
| Windows 10/11, x64 | `Setup.exe` and portable ZIP | Installation, native collector self-test and uninstallation passed on a Windows CI runner |

Real Wi-Fi/hotspot handovers, extended sleep and a wider range of devices still need validation. CI does not replace testing on your own hardware.

## Features

- **Daily usage at a glance.** Uploads and downloads combined. The Mac menu bar shows a compact total such as `1.2G`; the Windows tray tooltip shows today's usage.
- **Minute history.** Compare upload and download lines on the same scale, inspect specific times, browse previous days and export CSV.
- **Saved network labels.** Name a detected network and classify it as Wi-Fi, mobile hotspot or another type. Uncertain attribution stays unclassified.
- **Speed levels.** A compact 🐢 → 🚲 → ✈️ → 🚀 scale marks your last confirmed speed test, with upload/download results and a timestamp.
- **Background recording.** Closing the main window keeps recording; quitting the tray/menu bar app stops it. Login startup is optional.

## Getting started

Install and launch the app, then use the network settings to label your current connection. A phone hotspot can use the same wireless interface as ordinary Wi-Fi, so wireless transport alone is not treated as proof of a hotspot.

Speed tests run only after confirmation. Each test downloads 16 MiB and uploads 4 MiB (about 22 MB including protocol overhead), connects to Cloudflare, and can be cancelled. An idle connection does not lower the saved speed level.

On Windows, the main window uses the installed Edge browser in app mode, with the default browser as a fallback. The collector runs independently of that window and serves the interface on loopback only.

## What the numbers mean

The app counts bytes on physical Wi-Fi and Ethernet adapters, including local-network traffic and VPN overhead carried by those adapters. Common virtual interfaces are excluded to avoid double counting. **This is not a carrier billing meter.** Usage while the app is not running cannot be recovered. Sleep and network-switch boundaries may be marked as uncertain.

Speed levels are this app's own thresholds, not an industry standard. Short tests can underestimate fast connections. The latency result measures an HTTP endpoint response, not game ping.

## Privacy

History stays on your computer. No accounts, telemetry, cloud synchronization, browsing history or packet contents are collected. Network hashes and user-entered names are still private data. A confirmed speed test connects to Cloudflare, which can observe your connection IP. Read the [privacy details](docs/PRIVACY.md).

## Source and license

```text
app/core/           Shared collection, accounting, storage and speed tests
app/ui/             Application interface
platforms/macos/    AppKit menu bar and window
platforms/windows/  Windows tray app and installer
scripts/            Build, test and pre-release checks
third_party/        Dependency provenance, checksums and licenses
```

Project code is licensed under [MIT](LICENSE). Bundled Python and its dependencies retain their own licenses. When filing an issue, **do not attach real network names, addresses, databases, logs, personal paths or screenshots of private usage history**.
