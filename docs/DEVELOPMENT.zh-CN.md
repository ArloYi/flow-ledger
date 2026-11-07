[English](DEVELOPMENT.md) | **简体中文**

# 开发和验证

项目不需要 npm 或 pip 依赖。核心为 Python 标准库，Mac 外壳为 Swift/AppKit，Windows 外壳和安装器为 Go/Win32。

运行测试（需要 Python 3.9+）：

```sh
python3 scripts/test.py
python3 scripts/privacy_scan.py . --source
```

Mac 环境执行 24 项核心与布局测试；Windows 跳过 Mac 专属采集夹具与 POSIX 父进程测试，另外通过 Actions 构建并执行安装、随包运行时启动、卸载检查。上述自动检查不代表真实手机热点切换、跨午夜或多个 VPN 组合已验证。

## 构建 Mac

在 Apple Silicon Mac 上，需要 Xcode Command Line Tools 与 Python 3.12+（下载脚本使用安全 tar 提取 API）。

```sh
python3 scripts/fetch_runtime.py macos --dest .build/macos
python3 scripts/build_macos.py --runtime .build/macos/python
```

得到 `dist/流量手账.app` 与 arm64 DMG。运行时随包携带，最终用户不需要 Command Line Tools 或 Python。当前构建脚本只提供 ad-hoc 签名，正式发行需要另行配置 Developer ID 和公证。

## 构建 Windows

可在 Windows 或 Mac 上使用 Go 1.25+ 和 Python 3.12+ 交叉编译：

```sh
python3 scripts/fetch_runtime.py windows --dest .build/windows
python3 scripts/build_windows.py --runtime .build/windows --icon docs/icon.png
```

得到 x64 Setup EXE 和便携 ZIP。构建会将经过校验的 Python embeddable runtime 和共享核心放入相同载荷；Setup 内嵌便携 ZIP，不读取当前开发机的数据库或设置。

Windows 使用 `GetIfTable2` 的硬件接口累计字节计数；路由与邻居表识别网关。IPv6-only 或网关地址不可取得时保留“未分类”，不猜热点类型。原生托盘通过 Win32 API 实现，主界面由系统 Edge 应用窗口承载。

## 本地源码运行

```sh
python3 app/core/server.py --open --data-dir .data
```

需要 Mac 或 Windows 的真实网卡接口。使用该开发模式只启动本地采集与浏览器页面，不包含原生托盘。不要把 `.data` 或本机导出记录提交到仓库。

## 隐私审查

`privacy_scan.py` 可额外接受仓库外的 `--known-private private-values.json`，文件内容为需要拒绝出现的字符串数组。它只报告匹配规则和文件名，不打印匹配内容。私有规则文件不应放进源码树。发布时还需检查 Git 清单和解包产物。
