import sys
import csv
import io
import json
import random
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from server import LocalHTTPServer as ThreadingHTTPServer
from server import Meter, handler_for, difference
from networks import probe_networks

def output(down,up):
    return f'en0 1500 <Link#2> aa:bb:cc:dd:ee:ff 10 0 {down} 20 0 {up} 0\n'

@unittest.skipIf(sys.platform == "win32", "macOS collector fixtures")
class NetworkTests(unittest.TestCase):
    def test_cached_system_signature_when_arp_is_unavailable_in_app(self):
        def run(args, input_text=None):
            if args[0].endswith('scutil'):
                return 'InterfaceName : en0\nARPResolvedHardwareAddress : aa:bb:cc:dd:ee:01'
            if args[1]=='getifaddr':return '192.0.2.10'
            if args[1]=='getoption':return '192.0.2.1'
            if args[1]=='getsummary':return 'ServiceID : 00000000-0000-4000-8000-000000000001'
            return '192.0.2.1 -- no entry'
        with patch('networks.command',side_effect=run):
            result=probe_networks(['en0'])
            self.assertNotEqual(result['en0']['id'],'unknown')
        with patch('networks.command',side_effect=lambda args,input_text=None: 'InterfaceName : en1\nARPResolvedHardwareAddress : aa:bb:cc:dd:ee:01' if args[0].endswith('scutil') else run(args,input_text)):
            self.assertEqual(probe_networks(['en0'])['en0']['id'],'unknown')

    def test_sleep_gap_is_not_assigned_to_current_hotspot(self):
        meter=Meter(':memory:',probe=lambda _: {'en0':{'id':'phone','name':'手机'}})
        with patch('server.time.monotonic',side_effect=[100,220]):
            with patch('server.subprocess.run',return_value=SimpleNamespace(stdout=output(100,200))):meter.sample()
            with patch('server.subprocess.run',return_value=SimpleNamespace(stdout=output(1100,2200))):meter.sample()
        rows=meter.snapshot()['days'][0]['networks']
        self.assertEqual([(r['id'],r['down']+r['up']) for r in rows if r['down']+r['up']], [('switch',3000)])
        self.assertEqual(meter.snapshot()['minutes'][0]['gap'],1)
        meter.db.close()

    def test_interface_counter_reset_never_creates_negative_usage(self):
        meter=Meter(':memory:',probe=lambda _: {'en0':{'id':'home','name':'家里'}})
        for down,up in [(9000,8000),(100,200),(150,260)]:
            with patch('server.subprocess.run',return_value=SimpleNamespace(stdout=output(down,up))):meter.sample()
        row=meter.snapshot()['days'][0]
        self.assertEqual((row['down'],row['up']),(50,60))
        self.assertEqual(sum(n['down']+n['up'] for n in row['networks']),110)
        meter.db.close()

    def test_realistic_switch_accounting_restart_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.sqlite3'
            profiles=[{'en0':{'id':'home','name':'家里'}},{'en0':{'id':'home','name':'家里'}},{'en0':{'id':'phone','name':'手机'}},{'en0':{'id':'phone','name':'手机'}},{'en0':{'id':'home','name':'家里'}},{'en0':{'id':'home','name':'家里'}}]
            readings=[(1000,2000),(1100,2200),(1110,2210),(1410,2610),(1420,2620),(1920,3220)]
            meter=Meter(path,probe=lambda _:profiles.pop(0))
            for down,up in readings:
                with patch('server.subprocess.run',return_value=SimpleNamespace(stdout=output(down,up))):meter.sample()
            meter.set_network('home','家里','wifi');meter.set_network('phone','手机','hotspot')
            state=meter.snapshot();day=state['days'][0]
            self.assertEqual((day['down'],day['up']),(920,1220))
            totals={r['id']:r['down']+r['up'] for r in day['networks']}
            self.assertEqual(totals,{'home':1400,'phone':700,'switch':40})
            minute_rows=list(csv.DictReader(io.StringIO(meter.minute_csv().decode('utf-8-sig'))))
            self.assertEqual(sum(int(r['合计 (bytes)']) for r in minute_rows),2140)
            self.assertEqual({r['网络类型'] for r in minute_rows},{'普通 Wi-Fi','手机热点','未分类'})
            meter.db.close()
            restarted=Meter(path,probe=lambda _: {'en0':{'id':'home','name':'网络 HOME'}})
            with patch('server.subprocess.run',return_value=SimpleNamespace(stdout=output(5000,9000))):restarted.sample()
            self.assertEqual(sum(r['down']+r['up'] for r in restarted.snapshot()['days']),2140)
            self.assertEqual(next(p for p in restarted.snapshot()['network_profiles'] if p['id']=='home')['kind'],'wifi')
            restarted.db.close()

    def test_unknown_identity_never_inherits_phone(self):
        def run(args):
            if args[1]=='getifaddr':return '192.0.2.122'
            if args[1]=='getoption':return '192.0.2.1'
            return '? (192.0.2.1) at (incomplete) on en0'
        with patch('networks.command',side_effect=run):
            self.assertEqual(probe_networks(['en0'])['en0']['id'],'unknown')

    def test_same_router_fingerprint_stable_different_router_changes(self):
        def run(mac):
            def command(args):
                if args[1]=='getifaddr':return '192.0.2.10'
                if args[1]=='getoption':return '192.0.2.1'
                return f'? (192.0.2.1) at {mac} on en0 ifscope [ethernet]'
            with patch('networks.command',side_effect=command):return probe_networks(['en0'])['en0']['id']
        self.assertEqual(run('aa:bb:cc:dd:ee:01'),run('aa:bb:cc:dd:ee:01'))
        self.assertNotEqual(run('aa:bb:cc:dd:ee:01'),run('aa:bb:cc:dd:ee:02'))

    def test_randomized_interface_sum_invariant(self):
        rng=random.Random(42)
        for _ in range(1000):
            old={f'en{i}':(rng.randrange(100000),rng.randrange(100000)) for i in range(4)}
            new={f'en{i}':(rng.randrange(100000),rng.randrange(100000)) for i in range(5)}
            expected=tuple(sum(max(0,new[k][i]-old[k][i]) for k in old) for i in range(2))
            self.assertEqual(difference(old,new),expected)

    def test_http_classification_validation(self):
        meter=Meter(':memory:',probe=lambda _: {})
        meter.db.execute("INSERT INTO networks VALUES ('test','测试网络','unknown')");meter.db.commit()
        server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(meter));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            payload=json.dumps({'id':'test','name':'我的手机','kind':'hotspot'}).encode()
            request=urllib.request.Request(base+'/api/network',data=payload,headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request) as response:self.assertEqual(response.status,200)
            with urllib.request.urlopen(base+'/api/stats') as response:state=json.load(response)
            self.assertEqual(state['network_profiles'][0]['kind'],'hotspot')
            request=urllib.request.Request(base+'/api/network',data=payload,headers={'Content-Type':'text/plain'})
            with self.assertRaises(urllib.error.HTTPError) as err:urllib.request.urlopen(request)
            self.assertEqual(err.exception.code,403)
        finally:
            server.shutdown();server.server_close();thread.join();meter.db.close()

if __name__=='__main__':unittest.main()
