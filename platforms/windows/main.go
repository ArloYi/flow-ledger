//go:build windows

package main

import (
	"archive/zip"
	"bufio"
	"bytes"
	_ "embed"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"syscall"
	"time"
	"unicode/utf16"
	"unsafe"
)

//go:embed payload.bin
var payload []byte
var setup = "false"
var user = syscall.NewLazyDLL("user32.dll")
var shell = syscall.NewLazyDLL("shell32.dll")
var kernel = syscall.NewLazyDLL("kernel32.dll")
var url string
var child *exec.Cmd
var window uintptr
var mu sync.Mutex
var today = "正在记录"
var executable, appDir, dataDir string

func wide(s string) *uint16 { p, _ := syscall.UTF16PtrFromString(s); return p }
func ptr(s string) uintptr  { return uintptr(unsafe.Pointer(wide(s))) }
func call(d *syscall.LazyDLL, n string, args ...uintptr) uintptr {
	r, _, _ := d.NewProc(n).Call(args...)
	return r
}
func message(text string, flags uintptr) uintptr {
	return call(user, "MessageBoxW", 0, ptr(text), ptr("流量手账"), flags)
}
func command(name string, args ...string) *exec.Cmd {
	c := exec.Command(name, args...)
	c.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	return c
}
func startDetached(name string, args ...string) error {
	c := command(name, args...)
	if err := c.Start(); err != nil {
		return err
	}
	go c.Wait()
	return nil
}
func openPath(path string) { call(shell, "ShellExecuteW", 0, ptr("open"), ptr(path), 0, 0, 1) }
func openWindow() {
	if !strings.HasPrefix(url, "http://127.0.0.1:") {
		return
	}
	for _, root := range []string{os.Getenv("ProgramFiles(x86)"), os.Getenv("ProgramFiles"), os.Getenv("LOCALAPPDATA")} {
		edge := filepath.Join(root, "Microsoft", "Edge", "Application", "msedge.exe")
		if _, err := os.Stat(edge); err == nil {
			if startDetached(edge, "--app="+url, "--user-data-dir="+filepath.Join(dataDir, "WebView"), "--no-first-run") == nil {
				return
			}
		}
	}
	openPath(url)
}
func desktopFolder() string {
	var buffer [260]uint16
	if call(shell, "SHGetFolderPathW", 0, 0x10, 0, 0, uintptr(unsafe.Pointer(&buffer[0]))) == 0 {
		return syscall.UTF16ToString(buffer[:])
	}
	return filepath.Join(os.Getenv("USERPROFILE"), "Desktop")
}
func startupFile() string {
	return filepath.Join(os.Getenv("APPDATA"), "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "FlowLedger.lnk")
}
func psQuote(s string) string { return "'" + strings.ReplaceAll(s, "'", "''") + "'" }
func powershell(script string) error {
	values := utf16.Encode([]rune(script))
	raw := make([]byte, len(values)*2)
	for i, v := range values {
		binary.LittleEndian.PutUint16(raw[i*2:], v)
	}
	output, err := command("powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", base64.StdEncoding.EncodeToString(raw)).CombinedOutput()
	if err != nil {
		return fmt.Errorf("shortcut setup failed: %w (%s)", err, strings.TrimSpace(string(output)))
	}
	return nil
}
func shortcut(path, target, args string) error {
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return err
	}
	return powershell("$s=(New-Object -ComObject WScript.Shell).CreateShortcut(" + psQuote(path) + ");$s.TargetPath=" + psQuote(target) + ";$s.Arguments=" + psQuote(args) + ";$s.WorkingDirectory=" + psQuote(filepath.Dir(target)) + ";$s.IconLocation=" + psQuote(filepath.Join(filepath.Dir(target), "AppIcon.ico")) + ";$s.Save()")
}
func autoStart() bool { _, err := os.Stat(startupFile()); return err == nil }
func toggleStartup() {
	var err error
	if autoStart() {
		err = os.Remove(startupFile())
	} else {
		err = shortcut(startupFile(), executable, "--background")
	}
	if err != nil {
		message("修改登录启动失败："+err.Error(), 0x10)
	}
}
func install() error {
	if !hasArg("--silent") && message("安装流量手账 Windows 预览版？\n\n将安装到当前用户的应用目录，创建桌面和开始菜单快捷方式。无需管理员权限。\n已有流量记录保留。Windows 实机验收尚未完成。", 0x24) != 6 {
		return nil
	}
	target := filepath.Join(os.Getenv("LOCALAPPDATA"), "Programs", "FlowLedger")
	if running() {
		return fmt.Errorf("请先从托盘退出正在运行的流量手账，再安装或升级")
	}
	reader, err := zip.NewReader(bytes.NewReader(payload), int64(len(payload)))
	if err != nil {
		return err
	}
	stage := target + ".installing"
	if _, err := os.Stat(stage); err == nil {
		return fmt.Errorf("存在未完成安装目录，请检查 %s", stage)
	}
	if err := os.MkdirAll(stage, 0755); err != nil {
		return err
	}
	success := false
	defer func() {
		if !success {
			os.RemoveAll(stage)
		}
	}()
	for _, f := range reader.File {
		clean := filepath.Clean(filepath.FromSlash(f.Name))
		if clean == "." || filepath.IsAbs(clean) || clean == ".." || strings.HasPrefix(clean, ".."+string(os.PathSeparator)) {
			return fmt.Errorf("安装包路径无效")
		}
		dest := filepath.Join(stage, clean)
		if f.FileInfo().IsDir() {
			if err := os.MkdirAll(dest, 0755); err != nil {
				return err
			}
			continue
		}
		if err := os.MkdirAll(filepath.Dir(dest), 0755); err != nil {
			return err
		}
		r, err := f.Open()
		if err != nil {
			return err
		}
		w, err := os.Create(dest)
		if err != nil {
			r.Close()
			return err
		}
		_, err = io.Copy(w, r)
		r.Close()
		w.Close()
		if err != nil {
			return err
		}
	}
	old := target + ".previous"
	if _, err := os.Stat(old); err == nil {
		return fmt.Errorf("请先检查之前的备份目录 %s", old)
	}
	hadOld := false
	if _, err := os.Stat(target); err == nil {
		if _, err := os.Stat(filepath.Join(target, ".flow-ledger-install")); err != nil {
			return fmt.Errorf("目标目录不是本工具的安装目录")
		}
		if err := os.Rename(target, old); err != nil {
			return err
		}
		hadOld = true
	}
	if err := os.Rename(stage, target); err != nil {
		if hadOld {
			os.Rename(old, target)
		}
		return err
	}
	success = true
	exe := filepath.Join(target, "FlowLedger.exe")
	if err := shortcut(filepath.Join(desktopFolder(), "Flow Ledger.lnk"), exe, ""); err != nil {
		return err
	}
	if err := shortcut(filepath.Join(os.Getenv("APPDATA"), "Microsoft", "Windows", "Start Menu", "Programs", "Flow Ledger.lnk"), exe, ""); err != nil {
		return err
	}
	key := `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\FlowLedger`
	for name, value := range map[string]string{"DisplayName": "流量手账（Windows 预览版）", "DisplayVersion": "1.5.0-beta.1", "Publisher": "ArloYi", "InstallLocation": target, "UninstallString": "\"" + exe + "\" --uninstall", "DisplayIcon": filepath.Join(target, "AppIcon.ico")} {
		if err := command("reg.exe", "add", key, "/v", name, "/t", "REG_SZ", "/d", value, "/f").Run(); err != nil {
			return err
		}
	}
	if hadOld {
		os.RemoveAll(old)
	}
	if !hasArg("--silent") && message("安装完成。现在打开流量手账？\n\n登录自动启动可在托盘菜单中开启。", 0x24) == 6 {
		return startDetached(exe)
	}
	return nil
}
func uninstall() error {
	if running() {
		return fmt.Errorf("请先从托盘菜单退出流量手账")
	}
	expected := filepath.Join(os.Getenv("LOCALAPPDATA"), "Programs", "FlowLedger")
	if !strings.EqualFold(appDir, expected) {
		return fmt.Errorf("请从 Windows 设置中的已安装应用卸载")
	}
	if !hasArg("--silent") && message("卸载流量手账？\n应用和快捷方式会移除，本机流量历史保留。", 0x24) != 6 {
		return nil
	}
	os.Remove(startupFile())
	os.Remove(filepath.Join(desktopFolder(), "Flow Ledger.lnk"))
	os.Remove(filepath.Join(os.Getenv("APPDATA"), "Microsoft", "Windows", "Start Menu", "Programs", "Flow Ledger.lnk"))
	if err := command("reg.exe", "delete", `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\FlowLedger`, "/f").Run(); err != nil {
		return err
	}
	// Powershell waits for this process, then removes only this marked installation.
	script := fmt.Sprintf("Wait-Process -Id %d -ErrorAction SilentlyContinue; if (Test-Path -LiteralPath %s) { Remove-Item -LiteralPath %s -Recurse -Force }", os.Getpid(), psQuote(filepath.Join(expected, ".flow-ledger-install")), psQuote(expected))
	values := utf16.Encode([]rune(script))
	raw := make([]byte, len(values)*2)
	for i, v := range values {
		binary.LittleEndian.PutUint16(raw[i*2:], v)
	}
	return startDetached("powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", base64.StdEncoding.EncodeToString(raw))
}
func running() bool {
	h := call(kernel, "OpenMutexW", 0x100000, 0, ptr(`Local\ArloFlowLedger`))
	if h != 0 {
		call(kernel, "CloseHandle", h)
		return true
	}
	return false
}

type point struct{ X, Y int32 }
type msg struct {
	Window         uintptr
	Message        uint32
	WParam, LParam uintptr
	Time           uint32
	Point          point
	Private        uint32
}
type wndclass struct {
	Style                              uint32
	Proc                               uintptr
	ClsExtra, WndExtra                 int32
	Instance, Icon, Cursor, Background uintptr
	Menu, Class                        *uint16
}
type notify struct {
	Size                uint32
	Window              uintptr
	ID, Flags, Callback uint32
	Icon                uintptr
	Tip                 [128]uint16
	State, StateMask    uint32
	Info                [256]uint16
	Version             uint32
	Title               [64]uint16
	InfoFlags           uint32
	Guid                [16]byte
	Balloon             uintptr
}

var icon notify

func setTip(s string) {
	for i := range icon.Tip {
		icon.Tip[i] = 0
	}
	copy(icon.Tip[:], utf16.Encode([]rune(s)))
	call(shell, "Shell_NotifyIconW", 1, uintptr(unsafe.Pointer(&icon)))
}
func popup() {
	menu := call(user, "CreatePopupMenu")
	defer call(user, "DestroyMenu", menu)
	mu.Lock()
	title := today
	mu.Unlock()
	call(user, "AppendMenuW", menu, 3, 0, ptr(title))
	call(user, "AppendMenuW", menu, 0x800, 0, 0)
	for _, item := range []struct {
		id   uintptr
		name string
	}{{1, "打开流量手账"}, {2, "打开数据文件夹"}, {3, "登录 Windows 后自动记录"}, {4, "退出并停止记录"}} {
		flags := uintptr(0)
		if item.id == 3 && autoStart() {
			flags = 8
		}
		call(user, "AppendMenuW", menu, flags, item.id, ptr(item.name))
	}
	var p point
	call(user, "GetCursorPos", uintptr(unsafe.Pointer(&p)))
	call(user, "SetForegroundWindow", window)
	choice := call(user, "TrackPopupMenu", menu, 0x100|2, uintptr(p.X), uintptr(p.Y), 0, window, 0)
	switch choice {
	case 1:
		openWindow()
	case 2:
		openPath(dataDir)
	case 3:
		toggleStartup()
	case 4:
		call(user, "DestroyWindow", window)
	}
	call(user, "PostMessageW", window, 0, 0, 0)
}
func proc(hwnd uintptr, message uint32, wparam, lparam uintptr) uintptr {
	switch message {
	case 0x8001:
		if lparam == 0x202 {
			openWindow()
		} else if lparam == 0x205 {
			popup()
		}
		return 0
	case 0x8002:
		mu.Lock()
		value := today
		mu.Unlock()
		setTip(value)
		return 0
	case 2:
		call(shell, "Shell_NotifyIconW", 2, uintptr(unsafe.Pointer(&icon)))
		call(user, "PostQuitMessage", 0)
		return 0
	}
	return call(user, "DefWindowProcW", hwnd, uintptr(message), wparam, lparam)
}
func tray() error {
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	instance := call(kernel, "GetModuleHandleW", 0)
	name := wide("FlowLedgerTray")
	cls := wndclass{Proc: syscall.NewCallback(proc), Instance: instance, Class: name}
	if call(user, "RegisterClassW", uintptr(unsafe.Pointer(&cls))) == 0 {
		return fmt.Errorf("注册托盘窗口失败")
	}
	window = call(user, "CreateWindowExW", 0, uintptr(unsafe.Pointer(name)), ptr("流量手账"), 0, 0, 0, 0, 0, 0, 0, instance, 0)
	if window == 0 {
		return fmt.Errorf("创建托盘窗口失败")
	}
	hicon := call(user, "LoadImageW", 0, ptr(filepath.Join(appDir, "AppIcon.ico")), 1, 32, 32, 0x10)
	if hicon == 0 {
		hicon = call(user, "LoadIconW", 0, 32512)
	}
	icon = notify{Window: window, ID: 1, Flags: 1 | 2 | 4, Callback: 0x8001, Icon: hicon}
	icon.Size = uint32(unsafe.Sizeof(icon))
	copy(icon.Tip[:], utf16.Encode([]rune("流量手账 · 正在记录")))
	if call(shell, "Shell_NotifyIconW", 0, uintptr(unsafe.Pointer(&icon))) == 0 {
		return fmt.Errorf("添加托盘图标失败")
	}
	go poll()
	var m msg
	for {
		r := call(user, "GetMessageW", uintptr(unsafe.Pointer(&m)), 0, 0, 0)
		if int32(r) <= 0 {
			break
		}
		call(user, "TranslateMessage", uintptr(unsafe.Pointer(&m)))
		call(user, "DispatchMessageW", uintptr(unsafe.Pointer(&m)))
	}
	return nil
}
func poll() {
	client := http.Client{Timeout: 4 * time.Second}
	for {
		text := "流量手账 · 采集连接中断"
		response, err := client.Get(url + "/api/stats")
		if err == nil {
			var state struct {
				Today string  `json:"today"`
				Error *string `json:"error"`
				Days  []struct {
					Day      string `json:"day"`
					Down, Up float64
				} `json:"days"`
			}
			err = json.NewDecoder(response.Body).Decode(&state)
			response.Body.Close()
			if err == nil && state.Error == nil {
				for _, d := range state.Days {
					if d.Day == state.Today {
						text = fmt.Sprintf("今日总流量 %.1fG · 流量手账", (d.Down+d.Up)/1e9)
					}
				}
			}
		}
		mu.Lock()
		today = text
		mu.Unlock()
		call(user, "PostMessageW", window, 0x8002, 0, 0)
		time.Sleep(2 * time.Second)
	}
}
func run() error {
	mutex, _, err := kernel.NewProc("CreateMutexW").Call(0, 0, ptr(`Local\ArloFlowLedger`))
	if mutex == 0 {
		return err
	}
	defer call(kernel, "CloseHandle", mutex)
	if err == syscall.Errno(183) {
		if !hasArg("--background") {
			data, _ := os.ReadFile(filepath.Join(dataDir, "endpoint"))
			url = strings.TrimSpace(string(data))
			openWindow()
		}
		return nil
	}
	if err := os.MkdirAll(dataDir, 0700); err != nil {
		return err
	}
	child = command(filepath.Join(appDir, "runtime", "python.exe"), "-B", filepath.Join(appDir, "resources", "server.py"), "--port", "0", "--data-dir", dataDir, "--parent-pid", fmt.Sprint(os.Getpid()))
	child.Env = append(os.Environ(), "PYTHONDONTWRITEBYTECODE=1", "PYTHONNOUSERSITE=1", "PYTHONIOENCODING=utf-8")
	pipe, err := child.StdoutPipe()
	if err != nil {
		return err
	}
	child.Stderr = io.Discard
	if err := child.Start(); err != nil {
		return err
	}
	defer func() { child.Process.Kill(); child.Wait(); os.Remove(filepath.Join(dataDir, "endpoint")) }()
	ready := make(chan string, 1)
	go func() {
		scanner := bufio.NewScanner(pipe)
		for scanner.Scan() {
			line := scanner.Text()
			if start := strings.Index(line, "http://127.0.0.1:"); start >= 0 {
				candidate := line[start:]
				end := len("http://127.0.0.1:")
				for end < len(candidate) && candidate[end] >= '0' && candidate[end] <= '9' {
					end++
				}
				select {
				case ready <- candidate[:end]:
				default:
				}
			}
		}
	}()
	select {
	case url = <-ready:
	case <-time.After(15 * time.Second):
		return fmt.Errorf("采集启动超时，请重试或检查安装是否完整")
	}
	os.WriteFile(filepath.Join(dataDir, "endpoint"), []byte(url), 0600)
	if hasArg("--self-test") {
		time.Sleep(4 * time.Second)
		client := http.Client{Timeout: 5 * time.Second}
		response, err := client.Get(url + "/api/stats")
		if err != nil {
			return err
		}
		defer response.Body.Close()
		var state map[string]any
		if err := json.NewDecoder(response.Body).Decode(&state); err != nil {
			return err
		}
		if state["error"] != nil {
			return fmt.Errorf("collector error: %v", state["error"])
		}
		if _, ok := state["days"].([]any); !ok {
			return fmt.Errorf("invalid stats response")
		}
		return nil
	}
	if !hasArg("--background") {
		openWindow()
	}
	return tray()
}
func hasArg(s string) bool {
	for _, a := range os.Args[1:] {
		if a == s {
			return true
		}
	}
	return false
}
func main() {
	executable, _ = os.Executable()
	appDir = filepath.Dir(executable)
	dataDir = filepath.Join(os.Getenv("LOCALAPPDATA"), "FlowLedger")
	if hasArg("--self-test") {
		temporary, err := os.MkdirTemp("", "flow-ledger-check-")
		if err != nil {
			os.Exit(1)
		}
		dataDir = temporary
		defer os.RemoveAll(temporary)
	}
	var err error
	if setup == "true" {
		err = install()
	} else if hasArg("--uninstall") {
		err = uninstall()
	} else {
		err = run()
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err.Error())
		if !hasArg("--silent") && !hasArg("--self-test") {
			message(err.Error(), 0x10)
		}
		os.Exit(1)
	}
}
