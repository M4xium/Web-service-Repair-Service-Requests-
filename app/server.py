import json
import os
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

from app.db import get_conn, migrate, seed


def html_page(title, body):
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{title}</title>
    <style>body{{font-family:Arial;background:#fafafa}}main{{max-width:1000px;margin:20px auto;background:#fff;padding:20px;border-radius:8px}}table{{width:100%;border-collapse:collapse}}td,th{{border:1px solid #ddd;padding:8px}}form.inline{{display:inline-block;margin-right:6px}}input,textarea,select{{width:100%;padding:6px;margin-top:4px}}button{{margin-top:6px;padding:6px 10px}}</style>
    </head><body><main>{body}</main></body></html>"""


def parse_post(environ):
    try:
        size = int(environ.get('CONTENT_LENGTH') or 0)
    except ValueError:
        size = 0
    data = environ['wsgi.input'].read(size).decode('utf-8')
    return {k: v[0] for k, v in parse_qs(data).items()}


def cookies(environ):
    raw = environ.get('HTTP_COOKIE', '')
    out = {}
    for item in raw.split(';'):
        if '=' in item:
            k, v = item.strip().split('=', 1)
            out[k] = v
    return out


def redirect(start_response, location='/', headers=None):
    hs = [('Location', location)] + (headers or [])
    start_response('302 Found', hs)
    return [b'']


def app(environ, start_response):
    path = environ['PATH_INFO']
    method = environ['REQUEST_METHOD']
    query = parse_qs(environ.get('QUERY_STRING', ''))
    ck = cookies(environ)
    user_id = ck.get('userId')

    with get_conn() as conn:
        current_user = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone() if user_id else None

        if path == '/' and method == 'GET':
            users = conn.execute('SELECT * FROM users ORDER BY role, name').fetchall()
            opts = ''.join([f"<option value='{u['id']}'>{u['name']} ({u['role']})</option>" for u in users])
            user_info = f"<p>Текущий: <b>{current_user['name']}</b></p>" if current_user else ''
            body = f"<h1>Заявки в ремонтную службу</h1><p><a href='/requests/new'>Создать заявку</a></p>{user_info}<form method='post' action='/auth/select-user'><select name='userId' required><option value=''>--выберите--</option>{opts}</select><button>Войти</button></form><form method='post' action='/auth/logout'><button>Выйти</button></form>"
            start_response('200 OK', [('Content-Type', 'text/html; charset=utf-8')])
            return [html_page('Главная', body).encode('utf-8')]

        if path == '/auth/select-user' and method == 'POST':
            form = parse_post(environ)
            user = conn.execute('SELECT * FROM users WHERE id=?', (form.get('userId'),)).fetchone()
            if not user:
                start_response('400 Bad Request', [('Content-Type', 'text/plain; charset=utf-8')])
                return [b'Unknown user']
            target = '/dispatcher' if user['role'] == 'dispatcher' else '/master'
            return redirect(start_response, target, [('Set-Cookie', f"userId={user['id']}; HttpOnly; Path=/")])

        if path == '/auth/logout' and method == 'POST':
            return redirect(start_response, '/', [('Set-Cookie', 'userId=; Max-Age=0; Path=/')])

        if path == '/requests/new' and method == 'GET':
            msg = '<p style="color:green">Заявка создана</p>' if query.get('created') else ''
            body = f"<h1>Создание заявки</h1><p><a href='/'>На главную</a></p>{msg}<form method='post' action='/requests'><label>Клиент<input name='clientName' required></label><label>Телефон<input name='phone' required></label><label>Адрес<input name='address' required></label><label>Описание<textarea name='problemText' required></textarea></label><button>Создать</button></form>"
            start_response('200 OK', [('Content-Type', 'text/html; charset=utf-8')])
            return [html_page('Создать', body).encode('utf-8')]

        if path == '/requests' and method == 'POST':
            form = parse_post(environ)
            if not all(form.get(k) for k in ['clientName', 'phone', 'address', 'problemText']):
                start_response('400 Bad Request', [('Content-Type', 'text/plain; charset=utf-8')])
                return ['Все поля обязательны'.encode()]
            conn.execute("INSERT INTO requests (clientName, phone, address, problemText, status) VALUES (?, ?, ?, ?, 'new')",
                         (form['clientName'], form['phone'], form['address'], form['problemText']))
            return redirect(start_response, '/requests/new?created=1')

        if path == '/dispatcher' and method == 'GET':
            if not current_user or current_user['role'] != 'dispatcher':
                start_response('403 Forbidden', [('Content-Type', 'text/plain')])
                return [b'Forbidden']
            status = (query.get('status') or ['all'])[0]
            masters = conn.execute("SELECT id, name FROM users WHERE role='master'").fetchall()
            if status == 'all':
                reqs = conn.execute('SELECT r.*, u.name assignedName FROM requests r LEFT JOIN users u ON r.assignedTo=u.id ORDER BY r.id DESC').fetchall()
            else:
                reqs = conn.execute('SELECT r.*, u.name assignedName FROM requests r LEFT JOIN users u ON r.assignedTo=u.id WHERE r.status=? ORDER BY r.id DESC', (status,)).fetchall()
            rows = ''
            for r in reqs:
                opts = ''.join([f"<option value='{m['id']}' {'selected' if r['assignedTo']==m['id'] else ''}>{m['name']}</option>" for m in masters])
                rows += f"<tr><td>{r['id']}</td><td>{r['clientName']}</td><td>{r['problemText']}</td><td>{r['status']}</td><td>{r['assignedName'] or '-'}</td><td><form class='inline' method='post' action='/dispatcher/requests/{r['id']}/assign'><select name='masterId'>{opts}</select><button>Назначить</button></form><form class='inline' method='post' action='/dispatcher/requests/{r['id']}/cancel'><button>Отменить</button></form></td></tr>"
            status_opts = ''.join([f"<option value='{s}' {'selected' if s==status else ''}>{s}</option>" for s in ['all','new','assigned','in_progress','done','canceled']])
            body = f"<h1>Панель диспетчера: {current_user['name']}</h1><p><a href='/'>На главную</a></p><form method='get'><select name='status'>{status_opts}</select><button>Фильтр</button></form><table><tr><th>ID</th><th>Клиент</th><th>Проблема</th><th>Статус</th><th>Мастер</th><th>Действия</th></tr>{rows}</table>"
            start_response('200 OK', [('Content-Type', 'text/html; charset=utf-8')])
            return [html_page('Диспетчер', body).encode()]

        if path.startswith('/dispatcher/requests/') and method == 'POST':
            if not current_user or current_user['role'] != 'dispatcher':
                start_response('403 Forbidden', [('Content-Type', 'text/plain')])
                return [b'Forbidden']
            form = parse_post(environ)
            parts = path.strip('/').split('/')
            req_id, action = parts[2], parts[3]
            if action == 'assign':
                cur = conn.execute("UPDATE requests SET assignedTo=?, status='assigned' WHERE id=? AND status IN ('new','assigned')", (form.get('masterId'), req_id))
            else:
                cur = conn.execute("UPDATE requests SET status='canceled' WHERE id=? AND status IN ('new','assigned')", (req_id,))
            if cur.rowcount == 0:
                start_response('409 Conflict', [('Content-Type', 'text/plain; charset=utf-8')])
                return ['Недоступный переход статуса'.encode()]
            return redirect(start_response, '/dispatcher')

        if path == '/master' and method == 'GET':
            if not current_user or current_user['role'] != 'master':
                start_response('403 Forbidden', [('Content-Type', 'text/plain')])
                return [b'Forbidden']
            reqs = conn.execute('SELECT * FROM requests WHERE assignedTo=? ORDER BY id DESC', (current_user['id'],)).fetchall()
            rows = ''
            for r in reqs:
                rows += f"<tr><td>{r['id']}</td><td>{r['clientName']}</td><td>{r['problemText']}</td><td>{r['status']}</td><td><form class='inline' method='post' action='/master/requests/{r['id']}/take'><button>Взять в работу</button></form><form class='inline' method='post' action='/master/requests/{r['id']}/complete'><button>Завершить</button></form></td></tr>"
            body = f"<h1>Панель мастера: {current_user['name']}</h1><p><a href='/'>На главную</a></p><table><tr><th>ID</th><th>Клиент</th><th>Проблема</th><th>Статус</th><th>Действия</th></tr>{rows}</table>"
            start_response('200 OK', [('Content-Type', 'text/html; charset=utf-8')])
            return [html_page('Мастер', body).encode()]

        if path.startswith('/master/requests/') and method == 'POST':
            if not current_user or current_user['role'] != 'master':
                start_response('403 Forbidden', [('Content-Type', 'text/plain')])
                return [b'Forbidden']
            parts = path.strip('/').split('/')
            req_id, action = parts[2], parts[3]
            if action == 'take':
                cur = conn.execute("UPDATE requests SET status='in_progress' WHERE id=? AND assignedTo=? AND status='assigned'", (req_id, current_user['id']))
                if cur.rowcount == 0:
                    if 'application/json' in (environ.get('HTTP_ACCEPT') or ''):
                        start_response('409 Conflict', [('Content-Type', 'application/json')])
                        return [json.dumps({'message': 'Заявка уже взята или недоступна'}).encode()]
                    start_response('409 Conflict', [('Content-Type', 'text/plain; charset=utf-8')])
                    return ['Заявка уже взята или недоступна'.encode()]
            else:
                cur = conn.execute("UPDATE requests SET status='done' WHERE id=? AND assignedTo=? AND status='in_progress'", (req_id, current_user['id']))
                if cur.rowcount == 0:
                    start_response('409 Conflict', [('Content-Type', 'text/plain; charset=utf-8')])
                    return ['Недоступный переход статуса'.encode()]
            if 'application/json' in (environ.get('HTTP_ACCEPT') or ''):
                start_response('200 OK', [('Content-Type', 'application/json')])
                return [json.dumps({'message': 'ok'}).encode()]
            return redirect(start_response, '/master')

        if path == '/api/requests' and method == 'GET':
            rows = [dict(r) for r in conn.execute('SELECT * FROM requests ORDER BY id').fetchall()]
            start_response('200 OK', [('Content-Type', 'application/json')])
            return [json.dumps(rows, ensure_ascii=False).encode('utf-8')]

    start_response('404 Not Found', [('Content-Type', 'text/plain')])
    return [b'Not found']


def main():
    migrate()
    seed()
    port = int(os.environ.get('PORT', '3000'))
    with make_server('0.0.0.0', port, app) as server:
        print(f'Listening on http://localhost:{port}')
        server.serve_forever()


if __name__ == '__main__':
    main()
