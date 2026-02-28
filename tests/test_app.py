import json
import os
import sqlite3
import threading
import time
import unittest
from urllib import parse, request
from wsgiref.simple_server import make_server

os.environ['DB_PATH'] = 'test.sqlite3'

from app.db import migrate, seed, get_conn
from app.server import app


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.exists('test.sqlite3'):
            os.remove('test.sqlite3')
        migrate()
        seed()
        cls.server = make_server('127.0.0.1', 0, app)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        if os.path.exists('test.sqlite3'):
            os.remove('test.sqlite3')

    def url(self, p):
        return f'http://127.0.0.1:{self.port}{p}'

    def test_create_request_status_new(self):
        data = parse.urlencode({
            'clientName': 'Test',
            'phone': '+70000',
            'address': 'Street',
            'problemText': 'Problem',
        }).encode()
        req = request.Request(self.url('/requests'), data=data, method='POST')
        opener = request.build_opener(request.HTTPRedirectHandler())
        resp = opener.open(req)
        self.assertEqual(resp.status, 200)
        with get_conn() as conn:
            row = conn.execute("SELECT status FROM requests WHERE clientName='Test'").fetchone()
            self.assertEqual(row['status'], 'new')

    def test_race_take_only_one_success(self):
        with get_conn() as conn:
            master_id = conn.execute("SELECT id FROM users WHERE role='master' ORDER BY id LIMIT 1").fetchone()['id']
            req_id = conn.execute("""INSERT INTO requests (clientName, phone, address, problemText, status, assignedTo)
                VALUES ('Race', '+1', 'addr', 'race', 'assigned', ?)""", (master_id,)).lastrowid

        results = []

        def do_take():
            req = request.Request(self.url(f'/master/requests/{req_id}/take'), method='POST', headers={
                'Accept': 'application/json',
                'Cookie': f'userId={master_id}'
            })
            try:
                with request.urlopen(req) as resp:
                    results.append(resp.status)
            except Exception as e:
                results.append(getattr(e, 'code', 500))

        t1 = threading.Thread(target=do_take)
        t2 = threading.Thread(target=do_take)
        t1.start(); t2.start(); t1.join(); t2.join()

        self.assertEqual(sorted(results), [200, 409])
        with get_conn() as conn:
            row = conn.execute('SELECT status FROM requests WHERE id=?', (req_id,)).fetchone()
            self.assertEqual(row['status'], 'in_progress')


if __name__ == '__main__':
    unittest.main()
