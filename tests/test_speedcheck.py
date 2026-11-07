# -*- coding: utf-8 -*-
import sys
if sys.platform != "win32":
    import fcntl
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from server import LocalHTTPServer as ThreadingHTTPServer
from speedcheck import SpeedCheck, grade, PAYLOAD_BYTES
from server import Meter, handler_for

class Response:
    status=200
    def __init__(self,size,hook=None):self.left=size;self.hook=hook
    def read(self,n):
        if self.hook:self.hook()
        n=min(n,self.left);self.left-=n
        return b'0'*n

class Connection:
    def __init__(self):self.calls=[];self.size=0;self.hook=None;self.bad=False
    def request(self,method,path,body=None,headers=None):
        self.calls.append((method,path,len(body or b'')))
        self.size=int(path.split('=')[1]) if method=='GET' else 0
    def getresponse(self):
        response=Response(self.size,self.hook)
        if self.bad:response.status=503
        return response
    def close(self):pass

class SpeedTests(unittest.TestCase):
    def make(self):
        self.identity=['home',1];self.saved=[];self.connection=Connection()
        return SpeedCheck(lambda:tuple(self.identity),lambda result,token:self.saved.append(result),lambda:self.connection)
    def test_explicit_start_budget_result_and_thresholds(self):
        check=self.make();self.assertEqual(self.connection.calls,[])
        check.start('home');check.worker.join(3)
        self.assertFalse(check.worker.is_alive());self.assertEqual(check.snapshot()['status'],'done')
        self.assertEqual(check.snapshot()['bytes'],PAYLOAD_BYTES)
        self.assertEqual(len(self.saved),1)
        self.assertEqual(self.saved[0]['network_id'],'home')
        self.assertEqual([grade(n) for n in [0,9.99,10,49.99,50,99.99,100]],['基础','基础','流畅','流畅','高速','高速','很快'])
        self.assertEqual(len(self.connection.calls),8)
    def test_switch_and_cancel_never_save(self):
        for cancel in [False,True]:
            check=self.make()
            def change():
                if cancel:check.cancel()
                else:self.identity[:]=['phone',2]
            self.connection.hook=change
            check.start('home');check.worker.join(3)
            self.assertEqual(self.saved,[]);self.assertEqual(check.snapshot()['status'],'cancelled')
    def test_error_never_grades_or_retries(self):
        check=self.make();self.connection.bad=True
        check.start('home');check.worker.join(3)
        self.assertEqual(check.snapshot()['status'],'error');self.assertEqual(self.saved,[])
        self.assertEqual(len(self.connection.calls),1)
    def test_duplicate_start_and_stale_identity(self):
        check=self.make()
        with self.assertRaises(ValueError):check.start('old-network')
        entered=threading.Event();release=threading.Event()
        self.connection.hook=lambda:(entered.set(),release.wait(2))
        check.start('home');self.assertTrue(entered.wait(1))
        with self.assertRaises(ValueError):check.start('home')
        check.cancel();release.set();check.worker.join(3);self.assertEqual(self.saved,[])
    def test_results_persist_per_network_and_switch_back_invalidates(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Path(directory)/'meter.sqlite3';meter=Meter(db)
            meter.networks={'en0':{'id':'home'}};meter.last_time=time.monotonic()
            result={'network_id':'home','down':40,'up':10,'grade':'流畅'}
            meter.save_speed(result,0)
            meter.network_generation=2
            with self.assertRaises(InterruptedError):meter.save_speed(result,0)
            meter.db.close();meter=Meter(db)
            self.assertEqual(meter.snapshot()['speed_results'],[result]);meter.db.close()
    def test_start_endpoint_requires_explicit_consent(self):
        meter=Meter(':memory:');calls=[];meter.speedcheck.start=lambda key:calls.append(key)
        server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(meter));thread=threading.Thread(target=server.serve_forever);thread.start()
        try:
            url=f'http://127.0.0.1:{server.server_port}/api/speed/start'
            for consent in [None,False,'true',True]:
                request=urllib.request.Request(url,data=json.dumps({'id':'home','consent':consent}).encode(),headers={'Content-Type':'application/json'})
                if consent is True:
                    with urllib.request.urlopen(request) as response:self.assertEqual(response.status,200)
                else:
                    with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
                    self.assertEqual(error.exception.code,400)
            self.assertEqual(calls,['home'])
        finally:server.shutdown();server.server_close();thread.join();meter.db.close()
    @unittest.skipIf(sys.platform == "win32", "POSIX lock and reparent fixture")
    def test_duplicate_collector_lock_and_parent_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            with (Path(directory)/'collector.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                result=subprocess.run([sys.executable,'-B','server.py','--port','0','--data-dir',directory],capture_output=True,timeout=5)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('阻止重复记账',result.stderr.decode())
            process=subprocess.Popen([sys.executable,'-B','server.py','--port','0','--data-dir',directory,'--parent-pid','1'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                output,error=process.communicate(timeout=12)
                self.assertEqual(process.returncode,0,error.decode())
                self.assertIn(b'http://127.0.0.1:',output)
            finally:
                if process.poll() is None:process.kill();process.wait()

if __name__=='__main__':unittest.main()
