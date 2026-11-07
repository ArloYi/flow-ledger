import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from datetime import datetime, timezone
import sqlite3
from server import Meter as RealMeter, read_interfaces, difference
from networks import attribution

def Meter(path):
    return RealMeter(path, probe=lambda _: {})

SAMPLE = '''Name Mtu Network Address Ipkts Ierrs Ibytes Opkts Oerrs Obytes Coll
lo0 16384 <Link#1> 1 0 999 1 0 999 0
en0 1500 <Link#2> aa:bb:cc:dd:ee:ff 10 0 1000 20 0 2000 0
en0 1500 192.168.1 192.0.2.1 10 - 1000 20 - 2000 -
en1 1500 <Link#3> 10 0 300 20 0 400 0
utun7 1500 <Link#4> 10 0 1000 20 0 2000 0
'''

@unittest.skipIf(sys.platform == "win32", "macOS collector fixtures")
class MeterTests(unittest.TestCase):
    def test_network_switch_boundary_and_profile_correction(self):
        self.assertEqual(attribution({'en0': {'id':'home'}}, {'en0': {'id':'phone'}}, 'en0'), 'switch')
        self.assertEqual(attribution({'en0': {'id':'phone'}}, {'en0': {'id':'phone'}}, 'en0'), 'phone')
        meter = Meter(':memory:')
        meter.db.execute("INSERT INTO networks VALUES ('home','家里','unknown')")
        meter.db.execute("INSERT INTO networks VALUES ('phone','手机','unknown')")
        meter.db.execute("INSERT INTO network_usage VALUES (60,'2026-11-07','home',100,200)")
        meter.db.execute("INSERT INTO network_usage VALUES (60,'2026-11-07','phone',300,400)")
        meter.db.execute("INSERT INTO network_usage VALUES (60,'2026-11-07','switch',5,6)")
        meter.set_network('home','家里','wifi')
        meter.set_network('phone','手机','hotspot')
        rows=meter.network_breakdown(day='2026-11-07', total={'down':455,'up':656})
        totals={r['kind']:r['down']+r['up'] for r in rows if r['kind']!='unknown'}
        self.assertEqual(totals, {'wifi':300,'hotspot':700})
        self.assertEqual(sum(r['down']+r['up'] for r in rows),1111)
        self.assertEqual(sum(r['down']+r['up'] for r in rows if r['kind']=='unknown'),111)
        with self.assertRaises(ValueError): meter.set_network('switch','猜测','hotspot')
        meter.db.close()

    def test_minute_buckets_and_gap_marker(self):
        meter = Meter(':memory:')
        first = datetime(2026, 11, 7, 11, 29, 58, tzinfo=timezone.utc)
        second = datetime(2026, 11, 7, 11, 30, 0, tzinfo=timezone.utc)
        with meter.lock:
            meter.save_minute(first, 100, 50, 2)
            meter.save_minute(first, 200, 75, 2)
            meter.save_minute(second, 400, 100, 2)
            meter.save_minute(second, 500, 200, 120)
            meter.db.commit()
        rows = meter.history('2026-11-07')['minutes']
        self.assertEqual([(r['label'], r['down'], r['up']) for r in rows], [('11:30', 900, 300), ('11:29', 300, 125)])
        self.assertEqual(rows[0]['gap'], 1)
        self.assertEqual(rows[0]['seconds'], 2)
        self.assertEqual(rows[1]['samples'], 2)
        self.assertEqual(meter.history('2026-11-06')['minutes'], [])
        self.assertIn('11:30', meter.minute_csv().decode('utf-8-sig'))
        meter.db.close()

    def test_daily_migration_never_invents_minutes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'old.sqlite3'
            conn = sqlite3.connect(path)
            conn.execute('CREATE TABLE daily (day TEXT PRIMARY KEY, down INTEGER NOT NULL, up INTEGER NOT NULL)')
            conn.execute('INSERT INTO daily VALUES (?,?,?)', ('2026-11-06', 9000, 5000))
            conn.commit()
            conn.close()
            meter = Meter(path)
            self.assertEqual(meter.snapshot()['days'][0]['down'], 9000)
            self.assertEqual(meter.history('2026-11-06')['minutes'], [])
            self.assertIsNone(meter.snapshot()['minute_started'])
            meter.db.close()

    def test_link_rows_only_no_vpn_duplicates(self):
        self.assertEqual(read_interfaces(SAMPLE), {'en0': (1000, 2000), 'en1': (300, 400)})

    def test_resets_new_and_missing_interfaces(self):
        self.assertEqual(difference({'en0': (100, 300), 'en1': (50, 60)}, {'en0': (20, 400), 'en2': (999, 999)}), (0, 100))

    def test_persistence_and_restart_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.sqlite3'
            with patch('server.subprocess.run', return_value=SimpleNamespace(stdout=SAMPLE)):
                first = Meter(path)
                first.sample()
                self.assertEqual(first.snapshot()['days'][0]['down'], 0)
                first.previous = {'en0': (900, 1800), 'en1': (250, 300)}
                first.sample()
                self.assertEqual(first.snapshot()['days'][0]['down'], 150)
                self.assertEqual(first.snapshot()['days'][0]['up'], 300)
                first.db.close()
                second = Meter(path)
                second.sample()
                self.assertEqual(second.snapshot()['days'][0]['down'], 150)
                self.assertEqual(second.snapshot()['days'][0]['up'], 300)
                second.db.close()

if __name__ == '__main__':
    unittest.main()
