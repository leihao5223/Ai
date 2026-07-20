"""FaceMagic 账号验证服务器 — Vercel 版"""
import json, os, hashlib, secrets
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, redirect
from functools import wraps

app = Flask(__name__)

# ─── Vercel KV 存储 ───────────────────────────────────────────────────────────
redis = None
if os.environ.get("KV_REST_API_URL") and os.environ.get("KV_REST_API_TOKEN"):
    from upstash_redis import Redis
    redis = Redis(
        url=os.environ["KV_REST_API_URL"],
        token=os.environ["KV_REST_API_TOKEN"]
    )

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin888")
DATA_KEY = "facemagic:accounts"

def get_default_data():
    return {
        "users": {},
        "admin_password_hash": hash_password(ADMIN_PASSWORD),
        "sessions": {}
    }

def load_data():
    if redis is None:
        return get_default_data()
    try:
        raw = redis.get(DATA_KEY)
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return get_default_data()

def save_data(data):
    if redis is None:
        return
    try:
        redis.set(DATA_KEY, json.dumps(data, ensure_ascii=False))
    except Exception:
        pass

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

# ─── 辅助 ──────────────────────────────────────────────────────────────────────

def json_resp(data, status=200):
    return jsonify(data), status

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get("X-Admin-Token", "") or request.cookies.get("admin_token", "")
        if not token:
            return json_resp({"success": False, "msg": "未授权"}, 401)
        ac = load_data()
        s = ac.get("sessions", {}).get(token, {})
        if s.get("role") != "admin" or s.get("expires_at", "") < datetime.now().isoformat():
            return json_resp({"success": False, "msg": "未授权"}, 401)
        return f(*args, **kwargs)
    return wrapper

# ─── 客户端 API ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return json_resp({"name": "FaceMagic Auth", "version": "2.0", "status": "running"})

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True)
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

@app.route("/api/verify", methods=["POST"])
def api_verify():
    data = request.get_json(force=True)
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

# ─── 管理 API ──────────────────────────────────────────────────────────────────

@app.route("/api/admin/login", methods=["POST"])
def api_admin_login():
    data = request.get_json(force=True)
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
    return resp

@app.route("/api/admin/users", methods=["GET"])
@admin_required
def api_list_users():
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

@app.route("/api/admin/users", methods=["POST"])
@admin_required
def api_create_user():
    data = request.get_json(force=True)
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

@app.route("/api/admin/users/<username>", methods=["DELETE"])
@admin_required
def api_delete_user(username):
    ac = load_data()
    if username not in ac.get("users", {}):
        return json_resp({"success": False, "msg": "用户不存在"}, 404)
    del ac["users"][username]
    save_data(ac)
    return json_resp({"success": True, "msg": f"用户 {username} 已删除"})

@app.route("/api/admin/users/<username>/toggle", methods=["POST"])
@admin_required
def api_toggle_user(username):
    ac = load_data()
    if username not in ac.get("users", {}):
        return json_resp({"success": False, "msg": "用户不存在"}, 404)
    ac["users"][username]["enabled"] = not ac["users"][username].get("enabled", True)
    save_data(ac)
    s = "启用" if ac["users"][username]["enabled"] else "禁用"
    return json_resp({"success": True, "msg": f"用户 {username} 已{s}"})

@app.route("/api/admin/users/<username>/password", methods=["PUT"])
@admin_required
def api_set_password(username):
    data = request.get_json(force=True)
    new_pwd = data.get("password", "")
    if not new_pwd or len(new_pwd) < 4:
        return json_resp({"success": False, "msg": "密码至少4字符"}, 400)
    ac = load_data()
    if username not in ac.get("users", {}):
        return json_resp({"success": False, "msg": "用户不存在"}, 404)
    ac["users"][username]["password_hash"] = hash_password(new_pwd)
    save_data(ac)
    return json_resp({"success": True, "msg": f"用户 {username} 密码已修改"})

@app.route("/api/admin/users/<username>/expiry", methods=["PUT"])
@admin_required
def api_set_expiry(username):
    data = request.get_json(force=True)
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

@app.route("/api/admin/stats", methods=["GET"])
@admin_required
def api_stats():
    ac = load_data()
    users = ac.get("users", {})
    total = len(users)
    enabled = sum(1 for u in users.values() if u.get("enabled", True))
    return json_resp({"success": True, "stats": {"total": total, "enabled": enabled, "disabled": total - enabled}})

# ─── Web 管理面板 ─────────────────────────────────────────────────────────────

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
<form method="post" action="/admin/login">
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
let pwdUser=null,expUser=null,selDays=null,token=null;
(function(){const m=document.cookie.match(/admin_token=([^;]+)/);if(m)token=m[1]})();
function qs(s){return document.querySelector(s)}
function show(m,t){const e=qs('#alert');e.textContent=m;e.className='alert alert-'+t}
function api(p,o){const h={'Content-Type':'application/json'};if(token)h['X-Admin-Token']=token;return fetch(p,{...o,headers:h}).then(r=>r.json())}
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

@app.route("/admin/")
@app.route("/admin")
def admin_dashboard():
    token = request.cookies.get("admin_token", "")
    ac = load_data()
    s = ac.get("sessions", {}).get(token, {})
    if s.get("role") != "admin" or s.get("expires_at", "") < datetime.now().isoformat():
        return redirect("/admin/login")

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

    return ADMIN_DASHBOARD_HTML.format(total=total, enabled=enabled, disabled=disabled, rows=rows_html), 200, {"Content-Type": "text/html; charset=utf-8"}

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        pwd = request.form.get("password", "")
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
            resp.set_cookie("admin_token", token, max_age=28800, httponly=True, samesite="Lax")
            return resp
        return ADMIN_LOGIN_HTML.replace("{error}", '<div class="error">密码错误</div>'), 200, {"Content-Type": "text/html; charset=utf-8"}
    return ADMIN_LOGIN_HTML.replace("{error}", ""), 200, {"Content-Type": "text/html; charset=utf-8"}

@app.route("/admin/logout")
def admin_logout():
    resp = redirect("/admin/login")
    resp.set_cookie("admin_token", "", max_age=0)
    return resp
