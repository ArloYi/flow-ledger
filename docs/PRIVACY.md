# Privacy and release checks

**English** | [简体中文](PRIVACY.zh-CN.md)

The app stores daily and minute usage, physical interface identifiers, hashed network identities, network names/types you enter, and confirmed speed-test results locally. It does not collect browsing contents, packet payloads, account passwords or contacts. Hashing does not make these records anonymous; treat the database as private.

Normal recording does not upload usage to a server. An explicitly confirmed speed test connects to public Cloudflare endpoints, which can see your connection IP. The USTC speed-test link opens an independent website with its own data and usage policies; the app does not automatically run its test or import its results.

The public repository contains source, general documentation, synthetic test fixtures and dependency licenses. Databases, logs, real network names, private document links, local screenshots and history backups are excluded from source and installers. Test addresses and identifiers are synthetic.

Release review covers three layers:

1. Source and the Git file list: inspect secret patterns, private paths, actual network identifiers and files outside the release scope. Check author and committer email metadata as well.
2. Extracted packages: inspect Mac app resources and Windows portable contents; verify that the installer embeds the same ZIP payload. Exclude databases and runtime logs.
3. Published files: verify the remote tree and downloaded asset checksums against the reviewed local packages.

Automated scans help identify problems; they cannot prove that all privacy risks are absent. Never attach your database, real screenshots, logs or personal system paths directly to a public issue.
