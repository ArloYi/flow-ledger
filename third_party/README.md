# Bundled runtimes and licenses

Runtime download URLs and SHA-256 hashes are pinned in `runtime-lock.json`.

- macOS Python: Astral python-build-standalone, release 20261026, CPython 3.13.18, aarch64-apple-darwin install-only distribution.
- Windows Python: python.org, CPython 3.13.17 x64 embeddable distribution. The original `LICENSE.txt` is retained in the runtime.
- Windows launcher: built with the official Go toolchain. It contains no third-party Go modules; Go runtime license is included separately.

`LICENSE*` files are preserved from the python-build-standalone 20261026 source tree, including relevant runtime dependency notices. Their presence does not imply every optional library is used by this application. Original runtime licenses remain in the bundle as well.

Sources: https://github.com/astral-sh/python-build-standalone/tree/20261026 and https://www.python.org/downloads/release/python-31317/
