# -*- coding: utf-8 -*-
"""Explicitly requested, bounded transfer estimate; never run on startup."""
import http.client
import statistics
import threading
import time
from datetime import datetime

PAYLOAD_BYTES = 20 * 1024 * 1024

def grade(mbps):
    for limit, label in [(10, '基础'), (50, '流畅'), (100, '高速')]:
        if mbps < limit:
            return label
    return '很快'


class SpeedCheck:
    def __init__(self, identity, save, connection_factory=None):
        self.identity, self.save = identity, save
        self.connection_factory = connection_factory or (lambda: http.client.HTTPSConnection('speed.cloudflare.com', timeout=10))
        self.lock = threading.Lock()
        self.cancelled = threading.Event()
        self.connection = None
        self.worker = None
        self.state = {'status': 'idle', 'message': '', 'bytes': 0}

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def update(self, **values):
        with self.lock:
            self.state.update(values)

    def start(self, expected):
        with self.lock:
            if self.worker and self.worker.is_alive():
                raise ValueError('测速正在进行')
            key, token = self.identity()
            if not key or key != expected:
                raise ValueError('网络已变化或无法唯一识别，请确认当前网络后重试')
            self.cancelled.clear()
            self.state = {'status': 'running', 'message': '正在连接测速节点…', 'bytes': 0, 'network_id': key}
            self.worker = threading.Thread(target=self.run, args=(key, token), daemon=True)
            self.worker.start()

    def cancel(self):
        self.cancelled.set()
        connection = self.connection
        if connection:
            connection.close()

    def guard(self, key, token, deadline):
        if self.cancelled.is_set():
            raise InterruptedError('已取消，本次不评级')
        if self.identity() != (key, token):
            raise InterruptedError('网络连接发生变化，本次不评级')
        if time.monotonic() >= deadline:
            raise TimeoutError('测速超时，请稍后重试')

    def run(self, key, token):
        connection = self.connection_factory()
        self.connection = connection
        deadline = time.monotonic() + 55
        try:
            def transfer(size, upload=False):
                self.guard(key, token, deadline)
                started = time.monotonic()
                if upload:
                    body = b'0' * size
                    connection.request('POST', '/__up', body=body, headers={'Content-Type': 'application/octet-stream'})
                    self.update(bytes=self.snapshot()['bytes'] + size)
                else:
                    connection.request('GET', '/__down?bytes=' + str(size), headers={'Cache-Control': 'no-cache'})
                response = connection.getresponse()
                response_time = time.monotonic() - started
                if response.status != 200:
                    raise ValueError('测速节点暂时不可用')
                # Bound response size even when the endpoint misbehaves. Never retry.
                cap = 65536 if upload else size
                received = 0
                while True:
                    self.guard(key, token, deadline)
                    chunk = response.read(min(65536, cap - received + 1))
                    if not chunk:
                        break
                    received += len(chunk)
                    self.update(bytes=self.snapshot()['bytes'] + len(chunk))
                    if received > cap:
                        raise ValueError('测速节点返回的数据量异常')
                if not upload and received != size:
                    raise ValueError('下载未完成，本次不评级')
                return max(time.monotonic() - started, 0.000001), response_time

            # First zero-byte request warms TLS. The next three measure HTTP response time.
            transfer(0)
            latency = [transfer(0)[1] * 1000 for _ in range(3)]
            values = {}
            for direction, size in [('down', 8*1024*1024), ('up', 2*1024*1024)]:
                self.update(message='正在测试下载…' if direction == 'down' else '正在测试上传…')
                durations = [transfer(size, direction == 'up')[0] for _ in range(2)]
                values[direction] = size * 2 * 8 / sum(durations) / 1_000_000
            self.guard(key, token, deadline)
            result = dict(values, network_id=key, stamp=datetime.now().astimezone().isoformat(), latency=statistics.median(latency), jitter=statistics.mean(abs(b-a) for a,b in zip(latency,latency[1:])), grade=grade(values['down']), bytes=self.snapshot()['bytes'], source='Cloudflare', method='bounded-20MiB-v1')
            self.save(result, token)
            self.update(status='done', message='测速完成', result=result)
        except Exception as exc:
            self.update(status='cancelled' if self.cancelled.is_set() or isinstance(exc, InterruptedError) else 'error', message='已取消，本次不评级' if self.cancelled.is_set() else str(exc)[:120])
        finally:
            connection.close()
            self.connection = None
