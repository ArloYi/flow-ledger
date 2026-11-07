# 流量手账 · Flow Ledger

[English](README.md) | **简体中文**

一个安静待在菜单栏或系统托盘里的网络用量工具：看看今天用了多少流量、分别记住 Wi-Fi 和手机热点，再按需测一次网速。

**[下载安装包](https://github.com/ArloYi/flow-ledger/releases/tag/v1.5.0-beta.1)** · [安装与卸载](docs/INSTALL.zh-CN.md) · [隐私说明](docs/PRIVACY.zh-CN.md) · [开发与验证](docs/DEVELOPMENT.zh-CN.md)

这是 **1.5 预览版**。安装包自带 Python 运行环境，不需要用户另装开发工具。应用尚无发布者数字签名或 macOS 公证，系统可能阻止运行或显示未知发布者。

| 平台 | 包 | 状态 |
|---|---|---|
| macOS 13+，Apple Silicon | `.dmg`，拖入 Applications | 本机构建与采集验证；Intel Mac 尚未提供 |
| Windows 10/11，x64 | `Setup.exe`，另提供便携 ZIP | 跨平台实现与安装包已构建；Windows 自动检查见 Actions，真实 Wi-Fi/热点切换仍待验收 |

## 能做什么

- **今日用了多少**：下载与上传合计；Mac 菜单栏只占一小块，保留一位小数 G。Windows 托盘悬停显示今日总用量。
- **每分钟的变化**：上传、下载两条线共用刻度，查看指定分钟和历史，导出 CSV。
- **Wi-Fi 与热点分账**：识别到一个网络后，可给它命名并选择类型；下次沿用。无法确定归属的用量会保留为未分类。
- **一眼看懂速度档位**：🐢 → 🚲 → ✈️ → 🚀 分布在横向等级尺上，标记上次测速的位置；上下行数值与完整测试时间可查。
- **后台安静记录**：关闭主窗口仍继续记录，退出托盘/菜单栏则停止。登录启动可在菜单中开启或关闭。

## 使用方式

安装后打开应用。第一次遇到网络时，在“设置网络类型”里选择普通 Wi-Fi、手机热点或其他。热点同样可能通过 Wi-Fi 接入，因此不会只按无线接口自动判断手机热点。

“重测”需要再次确认：每次下载 16 MiB、上传 4 MiB，加协议开销约 22 MB，可取消。它使用 Cloudflare 节点，能反映当前路径的轻量吞吐估计；不会后台自动测速。空闲时流量很小，也不会让上次测速等级降低。

Windows 主窗口使用系统 Edge 的独立应用窗口；没有 Edge 时打开默认浏览器。托盘程序、采集程序和本机数据独立于浏览器页面。

## 准确性边界

统计物理 Wi-Fi/有线网卡，包含局域网传输和物理链路上的 VPN 开销，排除常见虚拟接口以避免重复。**这不是运营商账单**。工具未运行期间不补算，休眠或切换边界无法精确归属时会标记。Mac 与 Windows 都需要真实切换、不同硬件和长时运行的进一步验证。

速度等级采用本工具的分档，非行业标准；短样本可能低估高速宽带，延迟是 HTTP 节点响应而非游戏 ping。

## Privacy / English summary

A local-first network usage ledger for macOS and Windows. It records physical-adapter byte counters and per-network history locally. No accounts, telemetry, cloud synchronization, packet contents, or browsing history are collected. A speed test only runs after explicit confirmation and connects to Cloudflare, which can observe the connection IP. See [privacy details](docs/PRIVACY.zh-CN.md).

## 源码与许可证

```text
app/core/           共享采集、统计、存储与测速
app/ui/             中文界面
platforms/macos/    AppKit 菜单栏与窗口
platforms/windows/  Windows 托盘与安装程序
scripts/            构建、测试与发布前检查
third_party/        依赖来源、校验值与许可证
```

本项目代码使用 [MIT License](LICENSE)。随安装包分发的 Python 及依赖保留各自许可证。缺陷反馈请使用仓库 Issues，**不要粘贴真实 Wi-Fi 名、网络地址、数据库、日志或个人目录路径**。
