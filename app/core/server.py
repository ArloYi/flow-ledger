#!/usr/bin/env python3
"""Local macOS and Windows network meter. Python standard library only."""
import argparse
import sys
import os
import csv
import io
import json
import re
import sqlite3
import subprocess
import threading
import time
import webbrowser
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from networks import probe_networks, attribution
from speedcheck import SpeedCheck
from process_support import acquire_lock, parent_alive

ROOT = Path(__file__).resolve().parent

class LocalHTTPServer(ThreadingHTTPServer):
    def server_bind(self):
        # Local UI does not need reverse DNS; it can stall on disconnected hosts.
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]



def read_interfaces(output):
    result = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 10 or not re.fullmatch(r'en\d+\*?', parts[0]) or not parts[2].startswith('<Link#'):
            continue
        # The address column is absent on some interfaces; the last seven are stable.
        tail = parts[-7:]
        result[parts[0].rstrip('*')] = (int(tail[2]), int(tail[5]))
    if not result:
        raise ValueError('没有找到可统计的 Wi-Fi / 有线网卡')
    return result


def difference(previous, current):
    down = up = 0
    for name, values in current.items():
        old = previous.get(name)
        if old is not None:
            down += max(0, values[0] - old[0])
            up += max(0, values[1] - old[1])
    return down, up


class Meter:
    def __init__(self, db_path, probe=None):
        self.lock = threading.Lock()
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS daily (day TEXT PRIMARY KEY, down INTEGER NOT NULL, up INTEGER NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS minutes (stamp INTEGER PRIMARY KEY, day TEXT NOT NULL, label TEXT NOT NULL, down INTEGER NOT NULL, up INTEGER NOT NULL, samples INTEGER NOT NULL, seconds REAL NOT NULL, gap INTEGER NOT NULL)')
        self.db.execute('CREATE INDEX IF NOT EXISTS minute_day ON minutes(day)')
        self.db.execute("CREATE TABLE IF NOT EXISTS networks (id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'unknown')")
        self.db.execute('CREATE TABLE IF NOT EXISTS network_usage (stamp INTEGER, day TEXT, network_id TEXT, down INTEGER, up INTEGER, PRIMARY KEY(stamp,network_id))')
        self.db.execute('CREATE INDEX IF NOT EXISTS usage_day ON network_usage(day)')
        for key, name in [('unknown', '未分类'), ('switch', '切换期间')]:
            self.db.execute('INSERT OR IGNORE INTO networks(id,name) VALUES (?,?)', (key, name))
        self.db.execute('CREATE TABLE IF NOT EXISTS speed_tests (id INTEGER PRIMARY KEY, network_id TEXT, result TEXT)')
        self.db.commit()
        self.previous = None
        self.last_time = None
        self.points = deque(maxlen=90)
        self.interfaces = []
        self.error = None
        self.updated = None
        self.started = datetime.now().astimezone().isoformat()
        self.stop = threading.Event()
        self.probe = probe or probe_networks
        self.networks = {}
        self.previous_networks = {}
        self.network_generation = 0
        self.speedcheck = SpeedCheck(self.speed_identity, self.save_speed)

    def sample(self):
        if sys.platform == 'win32':
            from windows_networks import collect
            current, network_map = collect()
        else:
            raw = subprocess.run(['/usr/sbin/netstat', '-ibn'], capture_output=True, text=True, timeout=5, check=True)
            current = read_interfaces(raw.stdout)
            network_map = self.probe(current)
        now = time.monotonic()
        wall = datetime.now().astimezone()
        with self.lock:
            down, up = difference(self.previous or {}, current)
            elapsed = now - self.last_time if self.last_time is not None else 0
            day = wall.date().isoformat()
            self.db.execute('INSERT INTO daily VALUES (?, ?, ?) ON CONFLICT(day) DO UPDATE SET down=down+excluded.down, up=up+excluded.up', (day, down, up))
            if self.previous is not None:
                self.save_minute(wall, down, up, elapsed)
                for interface, counters in current.items():
                    old = self.previous.get(interface)
                    if old is None:
                        continue
                    received, sent = max(0, counters[0]-old[0]), max(0, counters[1]-old[1])
                    key = attribution(self.previous_networks, network_map, interface)
                    if elapsed > 10:
                        key = 'switch'
                    self.db.execute('INSERT INTO network_usage VALUES (?,?,?,?,?) ON CONFLICT(stamp,network_id) DO UPDATE SET down=down+excluded.down, up=up+excluded.up', (int(wall.timestamp())//60*60, day, key, received, sent))
            for profile in network_map.values():
                self.db.execute('INSERT OR IGNORE INTO networks(id,name) VALUES (?,?)', (profile['id'], profile['name']))
            if {k:v['id'] for k,v in self.networks.items()} != {k:v['id'] for k,v in network_map.items()} or elapsed > 10:
                self.network_generation += 1
            self.networks = network_map
            self.previous_networks = network_map
            self.db.commit()
            self.previous, self.last_time = current, now
            self.interfaces = sorted(current)
            self.updated = wall.isoformat()
            self.error = None
            self.points.append({'time': wall.strftime('%H:%M:%S'), 'stamp': wall.timestamp(), 'down': down / elapsed if elapsed else 0, 'up': up / elapsed if elapsed else 0})

    def speed_identity(self):
        with self.lock:
            return self._speed_identity()

    def _speed_identity(self):
        ids = [p['id'] for p in self.networks.values()]
        fresh = self.last_time is not None and time.monotonic() - self.last_time < 10
        key = ids[0] if len(ids) == 1 and ids[0] != 'unknown' and not self.error and fresh else None
        return key, self.network_generation

    def save_speed(self, result, token):
        with self.lock:
            if self._speed_identity() != (result['network_id'], token):
                raise InterruptedError('网络已变化，本次不评级')
            self.db.execute('INSERT INTO speed_tests(network_id,result) VALUES (?,?)', (result['network_id'], json.dumps(result)))
            self.db.commit()

    def save_minute(self, wall, down, up, elapsed):
        # Deltas belong to the sampling end minute. Do not invent intervening
        # samples when the computer sleeps; mark the first resumed bucket.
        stamp = int(wall.timestamp()) // 60 * 60
        self.db.execute('''INSERT INTO minutes VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(stamp) DO UPDATE SET down=down+excluded.down,
            up=up+excluded.up, samples=samples+1, seconds=seconds+excluded.seconds,
            gap=MAX(gap, excluded.gap)''',
            (stamp, wall.date().isoformat(), wall.strftime('%H:%M'), down, up,
             elapsed if elapsed <= 10 else 0, int(elapsed > 10)))

    def minute_rows(self, day=None, all_rows=False):
        query = 'SELECT stamp, day, label, down, up, samples, seconds, gap FROM minutes'
        if day:
            cursor = self.db.execute(query + ' WHERE day=? ORDER BY stamp DESC', (day,))
        elif all_rows:
            cursor = self.db.execute(query + ' ORDER BY stamp DESC')
        else:
            cursor = self.db.execute(query + ' WHERE stamp >= ? ORDER BY stamp DESC', (int(time.time()) // 60 * 60 - 59 * 60,))
        keys = ['stamp', 'day', 'label', 'down', 'up', 'samples', 'seconds', 'gap']
        return [dict(zip(keys, row)) for row in cursor]

    def network_breakdown(self, day=None, stamp=None, total=None):
        where, args = ('u.stamp=?', (stamp,)) if stamp is not None else ('u.day=?', (day,))
        rows = [dict(zip(['id', 'name', 'kind', 'down', 'up'], r)) for r in self.db.execute('SELECT n.id,n.name,n.kind,SUM(u.down),SUM(u.up) FROM network_usage u JOIN networks n ON n.id=u.network_id WHERE '+where+' GROUP BY n.id ORDER BY SUM(u.down+u.up) DESC', args)]
        if total:
            down = max(0, total['down']-sum(r['down'] for r in rows))
            up = max(0, total['up']-sum(r['up'] for r in rows))
            if down or up:
                rows.append({'id': 'legacy', 'name': '升级前的记录', 'kind': 'unknown', 'down': down, 'up': up})
        return rows

    def set_network(self, key, name, kind):
        if kind not in ('wifi', 'hotspot', 'other', 'unknown') or not isinstance(name, str) or not 1 <= len(name.strip()) <= 40:
            raise ValueError('网络名称或类型无效')
        with self.lock:
            if key in ('unknown', 'switch') or not self.db.execute('SELECT 1 FROM networks WHERE id=?', (key,)).fetchone():
                raise ValueError('无法识别此网络，暂时不能保存分类')
            self.db.execute('UPDATE networks SET name=?,kind=? WHERE id=?', (name.strip(), kind, key))
            self.db.commit()

    def history(self, day):
        with self.lock:
            rows = self.minute_rows(day)
            for row in rows:
                row['networks'] = self.network_breakdown(stamp=row['stamp'], total=row)
            return {'day': day, 'minutes': rows}

    def minute_csv(self):
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(['日期', '分钟（本机时区）', '网络名称', '网络类型', '下载 (bytes)', '上传 (bytes)', '合计 (bytes)'])
        with self.lock:
            for row in self.minute_rows(all_rows=True):
                for net in self.network_breakdown(stamp=row['stamp'], total=row):
                    writer.writerow([row['day'], row['label'], net['name'], {'wifi':'普通 Wi-Fi','hotspot':'手机热点','other':'其他网络','unknown':'未分类'}[net['kind']], net['down'], net['up'], net['down']+net['up']])
        return stream.getvalue().encode('utf-8-sig')

    def run(self):
        while not self.stop.is_set():
            try:
                self.sample()
            except Exception as exc:
                with self.lock:
                    self.error = '读取网卡失败，请检查本地采集程序。' + str(exc)[:180]
                    self.previous = None
                    self.last_time = None
            self.stop.wait(2)

    def snapshot(self):
        with self.lock:
            rows = [{'day': d, 'down': r, 'up': t} for d, r, t in self.db.execute('SELECT day, down, up FROM daily ORDER BY day DESC')]
            today = datetime.now().astimezone().date().isoformat()
            first = self.db.execute('SELECT MIN(stamp) FROM minutes').fetchone()[0]
            profiles = [dict(zip(['id','name','kind'], r)) for r in self.db.execute('SELECT id,name,kind FROM networks WHERE id NOT IN (?,?)', ('unknown','switch'))]
            active_ids = {p['id'] for p in self.networks.values()}
            active = [p for p in profiles if p['id'] in active_ids]
            if 'unknown' in active_ids:
                active.append({'id':'unknown','name':'无法识别的网络','kind':'unknown'})
            for row in rows:
                row['networks'] = self.network_breakdown(day=row['day'], total=row)
            speed_results = [json.loads(r[0]) for r in self.db.execute('SELECT result FROM speed_tests WHERE id IN (SELECT MAX(id) FROM speed_tests GROUP BY network_id)')]
            return {'speed_results': speed_results, 'days': rows, 'today': today, 'interfaces': self.interfaces, 'points': list(self.points), 'minutes': self.minute_rows(), 'minute_started': first, 'started': self.started, 'error': self.error, 'updated': self.updated, 'active_networks':active, 'network_profiles':profiles}


def handler_for(meter):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}') or self.headers.get('Content-Type') != 'application/json':
                self.send_error(403)
                return
            if self.path not in ('/api/network', '/api/speed/start', '/api/speed/cancel'):
                self.send_error(404)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096:
                    raise ValueError()
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError()
                if self.path == '/api/network':
                    meter.set_network(payload['id'], payload['name'], payload['kind'])
                elif self.path == '/api/speed/start':
                    if payload.get('consent') is not True:
                        raise ValueError('需要确认测速用量')
                    meter.speedcheck.start(payload['id'])
                else:
                    meter.speedcheck.cancel()
            except (ValueError, KeyError, TypeError):
                self.send_error(400)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def do_GET(self):
            if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
                self.send_error(403)
                return
            parsed = urlparse(self.path)
            path = parsed.path
            if path == '/api/stats':
                snapshot = meter.snapshot()
                snapshot['speed_check'] = meter.speedcheck.snapshot()
                body = json.dumps(snapshot, ensure_ascii=False).encode()
                mime = 'application/json; charset=utf-8'
            elif path == '/api/history':
                day = parse_qs(parsed.query).get('day', [''])[0]
                try:
                    datetime.strptime(day, '%Y-%m-%d')
                except ValueError:
                    self.send_error(400)
                    return
                body = json.dumps(meter.history(day), ensure_ascii=False).encode()
                mime = 'application/json; charset=utf-8'
            elif path == '/export-minutes.csv':
                body = meter.minute_csv()
                mime = 'text/csv; charset=utf-8'
            elif path == '/export.csv':
                stream = io.StringIO()
                writer = csv.writer(stream)
                writer.writerow(['日期', '网络名称', '网络类型', '下载 (bytes)', '上传 (bytes)', '合计 (bytes)'])
                for row in meter.snapshot()['days']:
                    for net in row['networks']:
                        writer.writerow([row['day'],net['name'],{'wifi':'普通 Wi-Fi','hotspot':'手机热点','other':'其他网络','unknown':'未分类'}[net['kind']],net['down'],net['up'],net['down']+net['up']])
                body = stream.getvalue().encode('utf-8-sig')
                mime = 'text/csv; charset=utf-8'
            elif path == '/':
                page = ROOT / 'index.html'
                if not page.exists():
                    page = ROOT.parent / 'ui/index.html'
                body = page.read_bytes()
                mime = 'text/html; charset=utf-8'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(body)))
            if path in ('/export.csv', '/export-minutes.csv'):
                self.send_header('Content-Disposition', 'attachment; filename="network-usage.csv"')
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--parent-pid', type=int)
    parser.add_argument('--data-dir', type=Path)
    args = parser.parse_args()
    data = args.data_dir or ROOT / '.data'
    data.mkdir(parents=True, exist_ok=True)
    try:
        collector_lock = acquire_lock(data / 'collector.lock')
    except BlockingIOError:
        raise SystemExit('同一个数据文件夹已有采集程序运行，已阻止重复记账。')
    meter = Meter(data / 'usage.sqlite3')
    try:
        server = LocalHTTPServer(('127.0.0.1', args.port), handler_for(meter))
    except OSError:
        print(f'端口 {args.port} 已被占用。如果工具已运行，请打开 http://127.0.0.1:{args.port}；否则使用 --port 更换端口。')
        return
    args.port = server.server_port
    worker = threading.Thread(target=meter.run, daemon=True)
    worker.start()
    if args.parent_pid:
        def watch_parent():
            while not meter.stop.wait(1):
                if not parent_alive(args.parent_pid):
                    meter.speedcheck.cancel()
                    server.shutdown()
                    return
        threading.Thread(target=watch_parent, daemon=True).start()
    print(f'流量手账已启动：http://127.0.0.1:{args.port}，按 Ctrl+C 停止记录。', flush=True)
    if args.open:
        webbrowser.open(f'http://127.0.0.1:{args.port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        meter.stop.set()
        meter.speedcheck.cancel()
        if meter.speedcheck.worker:
            meter.speedcheck.worker.join(timeout=12)
        worker.join(timeout=7)
        server.server_close()
        meter.db.close()


if __name__ == '__main__':
    main()
