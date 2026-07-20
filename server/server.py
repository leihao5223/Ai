"""FaceMagic 账号验证服务器 — 零依赖，极致轻量"""
import json, os, hashlib, secrets, time, re
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_FILE = os.path.join(BASE_DIR, "accounts.json")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin888")

# ─── 数据存储 ──────────────────────────────────────────────────────────────────

_accounts_cache = None
_accounts_mtime = 0

def load_data():
    global _accounts_cache, _accounts_mtime
    try:
        mtime = os.path.getmtime(ACCOUNTS_FILE) if os.path.exists(ACCOUNTS_FILE) else 0
        if _accounts_cache is not None and mtime <= _accounts_mtime:
            return _accounts_cache
        if not os.path.exists(ACCOUNTS_FILE):
            _accounts_cache = {"users": {}, "admin_password_hash": None, "sessions": {}}
            _accounts_mtime = time.time()
            return _accounts_cache
        with open(ACCOUNTS_FILE, "r") as f:
            _accounts_cache = json.load(f)
            _accounts_mtime = mtime
            return _accounts_cache
    except Exception:
        _accounts_cache = {"users": {}, "admin_password_hash": None, "sessions": {}}
        return _accounts_cache

def save_data(data):
    global _accounts_cache, _accounts_mtime
    _accounts_cache = data
    _accounts_mtime = time.time()
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ─── 密码工具 ──────────────────────────────────────────────────────────────────

def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${h}"

def check_password(password, stored):
    if not stored or "$" not in stored:
        return False
    salt, h = stored.split("$", 1)
    return hash_password(password, salt) == stored

def make_token():
    return secrets.token_hex(32)

# ─── 响应工具 ──────────────────────────────────────────────────────────────────

def json_resp(data, status=200):
    body = json.dumps(data, ensure_ascii=False).encode()
    return (status, {"Content-Type": "application/json; charset=utf-8"}, body)

def html_resp(html, status=200):
    body = html.encode("utf-8")
    return (status, {"Content-Type": "text/html; charset=utf-8"}, body)

def redirect(path):
    return (302, {"Location": path}, b"")

def set_cookie(resp, name, value, path="/", max_age=None):
    h = f"{name}={value}; Path={path}; HttpOnly; SameSite=Lax"
    if max_age:
        h += f"; Max-Age={max_age}"
    resp[1]["Set-Cookie"] = h

# ─── HTML 页面 ─────────────────────────────────────────────────────────────────

ADMIN_LOGIN_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FaceMagic 管理面板 - 登录</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#1a1a2e;display:flex;justify-content:center;align-items:center;height:100vh}
.card{background:#16213e;padding:40px;border-radius:12px;width:360px;box-shadow:0 8px 32px rgba(0,0,0,.3)}
h1{color:#e94560;text-align:center;margin-bottom:8px;font-size:20px}
p{color:#888;text-align:center;margin-bottom:24px;font-size:13px}
input{width:100%;padding:12px;background:#0f3460;border:1px solid #1a3a6b;border-radius:6px;color:#e0e0e0;font-size:14px;margin-bottom:16px}
input:focus{outline:none;border-color:#e94560}
button{width:100%;padding:12px;background:#e94560;color:#fff;border:none;border-radius:6px;font-size:15px;font-weight:bold;cursor:pointer}
button:hover{background:#ff6b81}
.error{color:#ff6b6b;text-align:center;margin-bottom:12px;font-size:13px}
</style></head>
<body>
<div class="card">
<h1>FaceMagic 管理面板</h1>
<p>请输入管理员密码</p>
{error}
<form method="post">
<input type="password" name="password" placeholder="管理员密码" autofocus required>
<button type="submit">登 录</button>
</form>
</div>
</body></html>"""

ADMIN_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FaceMagic 管理面板</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#1a1a2e;color:#e0e0e0;padding:20px;font-size:14px}
.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;padding-bottom:16px;border-bottom:1px solid #0f3460}
h1{color:#e94560;font-size:22px}
.header-right{display:flex;gap:12px;align-items:center;color:#888;font-size:13px}
.btn{padding:8px 16px;border-radius:6px;border:none;cursor:pointer;font-size:13px;font-weight:bold;text-decoration:none;display:inline-block}
.btn-danger{background:#e94560;color:#fff}.btn-danger:hover{background:#ff6b81}
.btn-sm{padding:4px 10px;font-size:12px}
.btn-warn{background:#ffd93d;color:#1a1a2e}
.btn-ok{background:#6bcb77;color:#1a1a2e}
.btn-outline{background:transparent;border:1px solid #0f3460;color:#e0e0e0;cursor:pointer}.btn-outline:hover{border-color:#e94560}
.btn-sml{background:#0f3460;color:#e0e0e0;border:1px solid #1a3a6b;padding:4px 8px;font-size:11px;border-radius:4px;cursor:pointer}
.stats{display:flex;gap:16px;margin-bottom:24px}
.stat-card{background:#16213e;padding:16px 20px;border-radius:8px;flex:1;text-align:center}
.stat-card .num{font-size:28px;font-weight:bold;color:#e94560}
.stat-card .label{font-size:12px;color:#888;margin-top:4px}
.form-row{display:flex;gap:12px;margin-bottom:24px;align-items:center;background:#16213e;padding:16px;border-radius:8px;flex-wrap:wrap}
.form-row input{padding:8px 12px;background:#0f3460;border:1px solid #1a3a6b;border-radius:6px;color:#e0e0e0;font-size:13px}
.form-row input:focus{outline:none;border-color:#e94560}
table{width:100%;border-collapse:collapse;background:#16213e;border-radius:8px;overflow:hidden}
th{background:#0f3460;color:#888;font-size:12px;padding:12px 16px;text-align:left;font-weight:normal;white-space:nowrap}
td{padding:12px 16px;border-top:1px solid #0f3460;font-size:13px}
tr:hover{background:rgba(233,69,96,.05)}
.status-on{color:#6bcb77;font-weight:bold}
.status-off{color:#ff6b6b;font-weight:bold}
.actions{display:flex;gap:6px;flex-wrap:wrap}
.empty{text-align:center;padding:40px;color:#555;font-size:14px}
.alert{display:none;padding:10px 16px;border-radius:6px;margin-bottom:16px;font-size:13px}
.alert-success{display:block;background:rgba(107,203,119,.15);color:#6bcb77;border:1px solid rgba(107,203,119,.3)}
.alert-error{display:block;background:rgba(255,107,107,.15);color:#ff6b6b;border:1px solid rgba(255,107,107,.3)}
.modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.6);justify-content:center;align-items:center;z-index:100}
.modal.show{display:flex}
.modal-content{background:#16213e;padding:24px;border-radius:12px;width:380px;max-width:90%}
.modal-content h3{color:#e94560;margin-bottom:16px;font-size:16px}
.modal-content p{color:#888;margin-bottom:16px}
.modal-content input{width:100%;padding:10px;background:#0f3460;border:1px solid #1a3a6b;border-radius:6px;color:#e0e0e0;font-size:14px;margin-bottom:12px}
.modal-content input:focus{outline:none;border-color:#e94560}
.modal-btns{display:flex;gap:10px;justify-content:flex-end;align-items:center}
.duration-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px}
.duration-btn{padding:10px;background:#0f3460;border:1px solid #1a3a6b;border-radius:6px;color:#e0e0e0;font-size:13px;cursor:pointer;text-align:center}
.duration-btn:hover{border-color:#e94560}
.duration-btn.active{border-color:#6bcb77;background:rgba(107,203,119,.1);color:#6bcb77}
</style></head>
<body>
<div class="header">
<h1>FaceMagic 管理面板</h1>
<div class="header-right"><span id="totalUsers">{total} 个用户</span><a href="/admin/logout" class="btn btn-outline btn-sm">退出</a></div>
</div>
<div id="alert" class="alert"></div>
<div class="stats">
<div class="stat-card"><div class="num">{total}</div><div class="label">总用户</div></div>
<div class="stat-card"><div class="num">{enabled}</div><div class="label">已启用</div></div>
<div class="stat-card"><div class="num">{disabled}</div><div class="label">已禁用</div></div>
</div>
<div class="form-row">
<input type="text" id="newUsername" placeholder="用户名" style="flex:1;min-width:120px">
<input type="text" id="newPassword" placeholder="密码" style="flex:1;min-width:120px">
<button class="btn btn-ok" onclick="createUser()">添加用户</button>
</div>
<table><thead><tr><th>用户名</th><th>状态</th><th>创建时间</th><th>有效期</th><th>最后登录</th><th>操作</th></tr></thead><tbody>
{rows}
</tbody></table>
<div id="passwordModal" class="modal"><div class="modal-content"><h3>修改密码</h3><p id="pwdUser"></p><input type="text" id="newPwdInput" placeholder="新密码（至少4字符）"><div class="modal-btns"><button class="btn btn-outline" onclick="closePwdModal()">取消</button><button class="btn btn-danger" onclick="confirmPwd()">确认修改</button></div></div></div>
<div id="expiryModal" class="modal"><div class="modal-content"><h3>设置有效期</h3><p id="expUser"></p><div class="duration-grid"><div class="duration-btn" data-d="7" onclick="selDur(this)">7天</div><div class="duration-btn" data-d="30" onclick="selDur(this)">30天</div><div class="duration-btn" data-d="90" onclick="selDur(this)">90天</div><div class="duration-btn" data-d="365" onclick="selDur(this)">1年</div></div><div class="modal-btns" style="justify-content:space-between"><button class="btn btn-ok" onclick="confirmExp(-1)">永久有效</button><div><button class="btn btn-outline" onclick="closeExpModal()">取消</button><button class="btn btn-danger" onclick="confirmExp(0)">确认</button></div></div></div></div>
<script>
let pwdUser=null,expUser=null,selDays=null;
function qs(s){return document.querySelector(s)}
function show(m,t){const e=qs('#alert');e.textContent=m;e.className='alert alert-'+t}
function api(p,o){return fetch(p,{...o,headers:{'Content-Type':'application/json',...o?.headers}}).then(r=>r.json())}
function createUser(){const u=qs('#newUsername').value.trim(),p=qs('#newPassword').value.trim();if(!u||!p){show('请填写用户名和密码','error');return}
api('/api/admin/users',{method:'POST',body:JSON.stringify({username:u,password:p})}).then(r=>{show(r.msg,r.success?'success':'error');if(r.success)location.reload()})}
function delUser(u){if(!confirm('确定删除 '+u+' ？'))return;api('/api/admin/users/'+u,{method:'DELETE'}).then(r=>{show(r.msg,r.success?'success':'error');if(r.success)location.reload()})}
function toggleUser(u){api('/api/admin/users/'+u+'/toggle',{method:'POST'}).then(r=>{show(r.msg,r.success?'success':'error');if(r.success)location.reload()})}
function showPwd(u){pwdUser=u;qs('#pwdUser').textContent='用户: '+u;qs('#newPwdInput').value='';qs('#passwordModal').classList.add('show')}
function closePwdModal(){qs('#passwordModal').classList.remove('show');pwdUser=null}
function confirmPwd(){const p=qs('#newPwdInput').value.trim();if(!p||p.length<4){show('密码至少4字符','error');return}
api('/api/admin/users/'+pwdUser+'/password',{method:'PUT',body:JSON.stringify({password:p})}).then(r=>{show(r.msg,r.success?'success':'error');closePwdModal()})}
function showExp(u){expUser=u;selDays=null;qs('#expUser').textContent='用户: '+u;document.querySelectorAll('.duration-btn').forEach(b=>b.classList.remove('active'));qs('#expiryModal').classList.add('show')}
function closeExpModal(){qs('#expiryModal').classList.remove('show');expUser=null;selDays=null}
function selDur(el){document.querySelectorAll('.duration-btn').forEach(b=>b.classList.remove('active'));el.classList.add('active');selDays=parseInt(el.dataset.d)}
function confirmExp(d){if(d>=0&&selDays===null){show('请选择期限','error');return}
api('/api/admin/users/'+expUser+'/expiry',{method:'PUT',body:JSON.stringify({duration_days:d>=0?d:selDays})}).then(r=>{show(r.msg,r.success?'success':'error');if(r.success)location.reload();closeExpModal()})}
document.querySelectorAll('.modal').forEach(m=>{m.addEventListener('click',function(e){if(e.target===this)this.classList.remove('show')})})
</script></body></html>"""

# ─── 路由处理 ──────────────────────────────────────────────────────────────────

def route(method, path, body, cookies):
    """主路由，返回 (status_code, headers_dict, body_bytes)"""

    # ─── 静态文件 ───
    if path == "/favicon.ico":
        return (204, {}, b"")

    # ─── API: 服务器信息 ───
    if method == "GET" and path == "/":
        return json_resp({"name": "FaceMagic Auth", "version": "2.0", "status": "running"})

    # ─── API: 用户登录 ───
    if method == "POST" and path == "/api/login":
        data = json.loads(body)
        username = data.get("username", "").strip()
        password = data.get("password", "")

        if not username or not password:
            return json_resp({"success": False, "msg": "用户名和密码不能为空"}, 400)

        ac = load_data()
        user = ac.get("users", {}).get(username)
        if not user or not check_password(password, user.get("password_hash", "")):
            return json_resp({"success": False, "msg": "用户名或密码错误"}, 401)

        if not user.get("enabled", True):
            return json_resp({"success": False, "msg": "账号已被禁用"}, 403)

        if user.get("expires_at"):
            expires = datetime.fromisoformat(user["expires_at"])
            if datetime.now() > expires:
                return json_resp({"success": False, "msg": "账号已过期"}, 403)

        token = make_token()
        if "sessions" not in ac:
            ac["sessions"] = {}
        ac["sessions"][token] = {
            "username": username, "role": "user",
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=7)).isoformat()
        }
        user["last_login"] = datetime.now().isoformat()
        save_data(ac)

        remaining_days = 0
        if user.get("expires_at"):
            remaining = datetime.fromisoformat(user["expires_at"]) - datetime.now()
            remaining_days = max(1, remaining.days)
            msg = f"登录成功，账号剩余 {remaining_days} 天"
        else:
            msg = "登录成功（永久有效）"

        return json_resp({
            "success": True, "msg": msg, "token": token,
            "username": username, "remaining_days": remaining_days,
            "expires_at": ac["sessions"][token]["expires_at"]
        })

    # ─── API: 验证 token ───
    if method == "POST" and path == "/api/verify":
        data = json.loads(body)
        token = data.get("token", "")
        if not token:
            return json_resp({"success": False, "msg": "token 不能为空"}, 400)

        ac = load_data()
        s = ac.get("sessions", {}).get(token)
        if not s:
            return json_resp({"success": False, "valid": False, "msg": "token 无效"}, 401)

        if s.get("expires_at", "") < datetime.now().isoformat():
            del ac["sessions"][token]
            save_data(ac)
            return json_resp({"success": False, "valid": False, "msg": "token 已过期"}, 401)

        return json_resp({"success": True, "valid": True, "username": s["username"]})

    # ─── 管理 API ──────────────────────────────────────────────────────────

    # 验证管理员 token
    def check_admin():
        auth = cookies.get("admin_token", "")
        if not auth:
            return False
        ac = load_data()
        s = ac.get("sessions", {}).get(auth, {})
        return s.get("role") == "admin" and s.get("expires_at", "") > datetime.now().isoformat()

    # API: 管理员登录
    if path == "/api/admin/login" and method == "POST":
        data = json.loads(body)
        pwd = data.get("password", "")
        ac = load_data()
        if not check_password(pwd, ac.get("admin_password_hash", "")):
            return json_resp({"success": False, "msg": "管理员密码错误"}, 401)

        token = make_token()
        if "sessions" not in ac:
            ac["sessions"] = {}
        ac["sessions"][token] = {
            "role": "admin",
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(hours=8)).isoformat()
        }
        save_data(ac)
        resp = json_resp({"success": True, "token": token})
        set_cookie(resp, "admin_token", token, max_age=28800)
        return resp

    # 以下 API 需要管理员权限
    admin_paths = [
        ("GET", "/api/admin/users", "list"),
        ("POST", "/api/admin/users", "create"),
        ("GET", "/api/admin/stats", "stats"),
    ]
    is_admin_api = any(method == m and path == p for m, p, _ in admin_paths)
    is_admin_api = is_admin_api or (method == "DELETE" and path.startswith("/api/admin/users/"))
    is_admin_api = is_admin_api or (method == "POST" and path.startswith("/api/admin/users/") and path.endswith("/toggle"))
    is_admin_api = is_admin_api or (method == "PUT" and ("/password" in path or "/expiry" in path))

    if is_admin_api and not check_admin():
        return json_resp({"success": False, "msg": "未授权"}, 401)

    # GET /api/admin/users
    if method == "GET" and path == "/api/admin/users":
        ac = load_data()
        users = []
        for name, info in ac.get("users", {}).items():
            users.append({
                "username": name,
                "enabled": info.get("enabled", True),
                "created_at": info.get("created_at", ""),
                "expires_at": info.get("expires_at", "") or None,
                "last_login": info.get("last_login", ""),
            })
        return json_resp({"success": True, "users": users})

    # POST /api/admin/users （创建用户）
    if method == "POST" and path == "/api/admin/users":
        data = json.loads(body)
        username = data.get("username", "").strip().lower()
        password = data.get("password", "")
        if not username or not password:
            return json_resp({"success": False, "msg": "用户名和密码不能为空"}, 400)
        if len(username) < 3:
            return json_resp({"success": False, "msg": "用户名至少3字符"}, 400)
        if len(password) < 4:
            return json_resp({"success": False, "msg": "密码至少4字符"}, 400)

        ac = load_data()
        if username in ac.get("users", {}):
            return json_resp({"success": False, "msg": "用户名已存在"}, 409)

        if "users" not in ac:
            ac["users"] = {}
        ac["users"][username] = {
            "password_hash": hash_password(password),
            "enabled": True, "created_at": datetime.now().isoformat(),
            "expires_at": None, "last_login": None
        }
        save_data(ac)
        return json_resp({"success": True, "msg": f"用户 {username} 创建成功"})

    # DELETE /api/admin/users/<username>
    if method == "DELETE" and path.startswith("/api/admin/users/"):
        username = path[len("/api/admin/users/"):]
        ac = load_data()
        if username not in ac.get("users", {}):
            return json_resp({"success": False, "msg": "用户不存在"}, 404)
        del ac["users"][username]
        save_data(ac)
        return json_resp({"success": True, "msg": f"用户 {username} 已删除"})

    # POST /api/admin/users/<username>/toggle
    if method == "POST" and path.endswith("/toggle"):
        username = path.split("/")[4]
        ac = load_data()
        if username not in ac.get("users", {}):
            return json_resp({"success": False, "msg": "用户不存在"}, 404)
        ac["users"][username]["enabled"] = not ac["users"][username].get("enabled", True)
        save_data(ac)
        s = "启用" if ac["users"][username]["enabled"] else "禁用"
        return json_resp({"success": True, "msg": f"用户 {username} 已{s}"})

    # PUT /api/admin/users/<username>/password
    if method == "PUT" and "/password" in path:
        username = path.split("/")[4]
        data = json.loads(body)
        new_pwd = data.get("password", "")
        if not new_pwd or len(new_pwd) < 4:
            return json_resp({"success": False, "msg": "密码至少4字符"}, 400)
        ac = load_data()
        if username not in ac.get("users", {}):
            return json_resp({"success": False, "msg": "用户不存在"}, 404)
        ac["users"][username]["password_hash"] = hash_password(new_pwd)
        save_data(ac)
        return json_resp({"success": True, "msg": f"用户 {username} 密码已修改"})

    # PUT /api/admin/users/<username>/expiry
    if method == "PUT" and "/expiry" in path:
        username = path.split("/")[4]
        data = json.loads(body)
        days = data.get("duration_days")
        ac = load_data()
        if username not in ac.get("users", {}):
            return json_resp({"success": False, "msg": "用户不存在"}, 404)
        if days is None or days < 0:
            ac["users"][username]["expires_at"] = None
            save_data(ac)
            return json_resp({"success": True, "msg": f"用户 {username} 已设置为永久有效"})
        expires = (datetime.now() + timedelta(days=days)).isoformat()
        ac["users"][username]["expires_at"] = expires
        save_data(ac)
        return json_resp({"success": True, "msg": f"用户 {username} 有效期已设为 {days} 天"})

    # GET /api/admin/stats
    if method == "GET" and path == "/api/admin/stats":
        ac = load_data()
        users = ac.get("users", {})
        total = len(users)
        enabled = sum(1 for u in users.values() if u.get("enabled", True))
        return json_resp({"success": True, "stats": {"total": total, "enabled": enabled, "disabled": total - enabled}})

    # ─── Web 管理面板 ─────────────────────────────────────────────────────

    # GET /admin/logout
    if method == "GET" and path == "/admin/logout":
        resp = redirect("/admin/login")
        set_cookie(resp, "admin_token", "", max_age=0)
        return resp

    # GET /admin/login, POST /admin/login
    if path == "/admin/login":
        if method == "GET":
            err = ""
            if cookies.get("admin_error"):
                err = f'<div class="error">密码错误</div>'
            return html_resp(ADMIN_LOGIN_HTML.replace("{error}", err))

        if method == "POST":
            pwd = parse_form_body(body).get("password", [""])[0]
            ac = load_data()
            if check_password(pwd, ac.get("admin_password_hash", "")):
                token = make_token()
                if "sessions" not in ac:
                    ac["sessions"] = {}
                ac["sessions"][token] = {
                    "role": "admin",
                    "created_at": datetime.now().isoformat(),
                    "expires_at": (datetime.now() + timedelta(hours=8)).isoformat()
                }
                save_data(ac)
                resp = redirect("/admin/")
                set_cookie(resp, "admin_token", token, max_age=28800)
                return resp
            resp = redirect("/admin/login")
            set_cookie(resp, "admin_error", "1", max_age=5)
            return resp

    # GET /admin/
    if method == "GET" and (path == "/admin/" or path == "/admin"):
        if not check_admin():
            return redirect("/admin/login")

        ac = load_data()
        rows_html = ""
        total = enabled = disabled = 0
        for name, info in sorted(ac.get("users", {}).items()):
            total += 1
            if info.get("enabled", True):
                enabled += 1
            else:
                disabled += 1
            status_cls = "status-on" if info.get("enabled", True) else "status-off"
            status_txt = "启用" if info.get("enabled", True) else "禁用"
            created = (info.get("created_at", "") or "")[:10] or "-"
            expires = info.get("expires_at", "") or "永久"
            last_login = (info.get("last_login", "") or "")[:16] or "从未登录"
            toggle_action = "禁用" if info.get("enabled", True) else "启用"
            toggle_cls = "btn-warn" if info.get("enabled", True) else "btn-ok"

            rows_html += f"""<tr><td><strong>{name}</strong></td>
<td class="{status_cls}">{status_txt}</td>
<td>{created}</td>
<td>{expires}</td>
<td>{last_login}</td>
<td class="actions">
<button class="btn btn-sm {toggle_cls}" onclick="toggleUser('{name}')">{toggle_action}</button>
<button class="btn btn-sm btn-outline" onclick="showPwd('{name}')">改密</button>
<button class="btn btn-sm btn-outline" onclick="showExp('{name}')">期限</button>
<button class="btn btn-sm btn-danger" onclick="delUser('{name}')">删除</button>
</td></tr>"""

        if not rows_html:
            rows_html = '<tr><td colspan="6" class="empty">暂无用户，在上方添加</td></tr>'

        page = ADMIN_DASHBOARD_HTML.format(
            total=total, enabled=enabled, disabled=disabled, rows=rows_html
        )
        return html_resp(page)

    return json_resp({"error": "Not Found"}, 404)


def parse_form_body(body):
    """解析 URL-encoded form body"""
    result = {}
    if not body:
        return result
    for part in body.decode().split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            from urllib.parse import unquote_plus
            result.setdefault(k, []).append(unquote_plus(v))
    return result


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_DELETE(self):
        self._handle("DELETE")

    def _handle(self, method):
        try:
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len > 0 else b""

            # 解析 cookies
            cookies = {}
            for c in self.headers.get("Cookie", "").split(";"):
                c = c.strip()
                if "=" in c:
                    k, v = c.split("=", 1)
                    cookies[k.strip()] = v.strip()

            status, headers, resp_body = route(method, self.path, body, cookies)
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(resp_body)
        except Exception as e:
            try:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
            except Exception:
                pass

    def log_message(self, format, *args):
        pass  # 不输出请求日志，省电省IO


def ensure_admin():
    os.makedirs(BASE_DIR, exist_ok=True)
    data = load_data()
    if not data.get("admin_password_hash"):
        data["admin_password_hash"] = hash_password(ADMIN_PASSWORD)
        save_data(data)
        print(f"  管理员密码: {ADMIN_PASSWORD}")
    # 清理过期 sessions
    now = datetime.now().isoformat()
    expired = [k for k, v in data.get("sessions", {}).items()
               if v.get("expires_at", "") < now]
    for k in expired:
        del data["sessions"][k]
    if expired:
        save_data(data)


if __name__ == "__main__":
    ensure_admin()
    print("=" * 48)
    print("  FaceMagic 账号验证服务器 v2.0")
    print("  零依赖 | 极致轻量")
    print("=" * 48)
    print(f"  数据文件: {ACCOUNTS_FILE}")
    print(f"  管理面板: http://127.0.0.1:5000/admin/")
    print(f"  管理员密码: {ADMIN_PASSWORD}")
    print()
    print(f"  修改密码: export ADMIN_PASSWORD=你的密码")
    print(f"  然后重新启动")
    print("=" * 48)

    server = HTTPServer(("0.0.0.0", 5000), Handler)
    server.serve_forever()
