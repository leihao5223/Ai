"""FaceMagic 账号验证服务器 — Vercel 版"""
import json, os, hashlib, secrets
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, redirect
from functools import wraps

app = Flask(__name__)

# ─── Vercel KV ─────────────────────────────────────────────────────────────────

redis = None
if os.environ.get("KV_REST_API_URL") and os.environ.get("KV_REST_API_TOKEN"):
    from upstash_redis import Redis
    redis = Redis(url=os.environ["KV_REST_API_URL"], token=os.environ["KV_REST_API_TOKEN"])

DATA_KEY = "facemagic:v3"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin888")

def _hash(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${h}"

def _check(password, stored):
    if not stored or "$" not in stored:
        return False
    return _hash(password, stored.split("$", 1)[0]) == stored

def _token():
    return secrets.token_hex(32)

def _seed():
    return {
        "accounts": {
            "a522352377": {
                "password_hash": _hash("Qq1314520."),
                "role": "super_admin",
                "enabled": True, "created_by": "system",
                "created_at": datetime.now().isoformat(),
                "expires_at": None, "last_login": None
            },
            "xianqi5223": {
                "password_hash": _hash("Aa112211"),
                "role": "admin",
                "enabled": True, "created_by": "a522352377",
                "created_at": datetime.now().isoformat(),
                "expires_at": None, "last_login": None
            }
        },
        "sessions": {},
        "admin_password_hash": _hash(ADMIN_PASSWORD)
    }

def load():
    if redis is None:
        return _seed()
    try:
        raw = redis.get(DATA_KEY)
        if raw:
            data = json.loads(raw)
            # 确保种子账号存在
            data.setdefault("accounts", {})
            if "a522352377" not in data["accounts"]:
                data["accounts"]["a522352377"] = _seed()["accounts"]["a522352377"]
            if "xianqi5223" not in data["accounts"]:
                data["accounts"]["xianqi5223"] = _seed()["accounts"]["xianqi5223"]
            return data
    except Exception:
        pass
    return _seed()

def save(data):
    if redis is None:
        return
    try:
        redis.set(DATA_KEY, json.dumps(data, ensure_ascii=False))
    except Exception:
        pass

# ─── 权限装饰器 ────────────────────────────────────────────────────────────────

now = lambda: datetime.now().isoformat()
exp8h = lambda: (datetime.now() + timedelta(hours=8)).isoformat()
exp7d = lambda: (datetime.now() + timedelta(days=7)).isoformat()

def authorize(token, roles=None):
    if not token:
        return None
    data = load()
    s = data.get("sessions", {}).get(token, {})
    if s.get("expires_at", "") < now():
        return None
    acct = data.get("accounts", {}).get(s.get("username", ""))
    if not acct or not acct.get("enabled", False):
        return None
    if roles and acct.get("role") not in roles:
        return None
    return acct, s["username"]

def require_role(*roles):
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            token = request.headers.get("X-Admin-Token", "") or request.cookies.get("admin_token", "")
            result = authorize(token, roles)
            if not result:
                return jsonify({"success": False, "msg": "无权限"}), 401
            request._user = result[1]
            request._role = result[0]["role"]
            return f(*args, **kwargs)
        return wrapper
    return deco

# ─── 客户端 API ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return jsonify({"name": "FaceMagic Auth", "version": "3.0", "status": "running"})

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True)
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"success": False, "msg": "用户名和密码不能为空"}), 400

    ac = load()
    user = ac.get("accounts", {}).get(username)
    if not user or not _check(password, user.get("password_hash", "")):
        return jsonify({"success": False, "msg": "用户名或密码错误"}), 401
    if not user.get("enabled", True):
        return jsonify({"success": False, "msg": "账号已被禁用"}), 403
    if user.get("expires_at"):
        if datetime.now() > datetime.fromisoformat(user["expires_at"]):
            return jsonify({"success": False, "msg": "账号已过期"}), 403

    token = _token()
    ac.setdefault("sessions", {})[token] = {
        "username": username, "role": user["role"],
        "created_at": now(), "expires_at": exp7d()
    }
    user["last_login"] = now()
    save(ac)

    remaining = 0
    if user.get("expires_at"):
        d = datetime.fromisoformat(user["expires_at"]) - datetime.now()
        remaining = max(1, d.days)
        msg = f"登录成功，账号剩余 {remaining} 天"
    else:
        msg = "登录成功（永久有效）"

    return jsonify({
        "success": True, "msg": msg, "token": token,
        "username": username, "remaining_days": remaining,
        "role": user["role"]
    })

@app.route("/api/verify", methods=["POST"])
def api_verify():
    data = request.get_json(force=True)
    token = data.get("token", "")
    result = authorize(token)
    if not result:
        return jsonify({"success": False, "valid": False}), 401
    return jsonify({"success": True, "valid": True, "username": result[1]})

# ─── 管理 API ──────────────────────────────────────────────────────────────────

@app.route("/api/admin/login", methods=["POST"])
def api_admin_login():
    data = request.get_json(force=True)
    pwd = data.get("password", "")
    ac = load()
    if not _check(pwd, ac.get("admin_password_hash", "")):
        return jsonify({"success": False, "msg": "密码错误"}), 401
    token = _token()
    ac.setdefault("sessions", {})[token] = {
        "role": "admin_panel", "created_at": now(), "expires_at": exp8h()
    }
    save(ac)
    return jsonify({"success": True, "token": token})

@app.route("/api/admin/users", methods=["GET"])
@require_role("super_admin", "admin")
def api_list_users():
    ac = load()
    accounts = ac.get("accounts", {})
    viewer = request._user
    role = request._role

    users = []
    for name, info in accounts.items():
        if info.get("role") == "super_admin":
            continue
        if role == "admin" and info.get("created_by") != viewer:
            continue
        users.append({
            "username": name,
            "role": info.get("role", "user"),
            "enabled": info.get("enabled", True),
            "created_by": info.get("created_by", ""),
            "created_at": info.get("created_at", ""),
            "expires_at": info.get("expires_at", "") or None,
            "last_login": info.get("last_login", ""),
        })
    return jsonify({"success": True, "users": users})

@app.route("/api/admin/users", methods=["POST"])
@require_role("super_admin", "admin")
def api_create_user():
    data = request.get_json(force=True)
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")
    target_role = data.get("role", "user")

    if not username or not password:
        return jsonify({"success": False, "msg": "用户名和密码不能为空"}), 400
    if len(username) < 3:
        return jsonify({"success": False, "msg": "用户名至少3字符"}), 400
    if len(password) < 4:
        return jsonify({"success": False, "msg": "密码至少4字符"}), 400

    # admin 不能创建 admin 或 super_admin
    if request._role == "admin" and target_role != "user":
        return jsonify({"success": False, "msg": "无权限创建此角色"}), 403

    ac = load()
    if username in ac.get("accounts", {}):
        return jsonify({"success": False, "msg": "用户名已存在"}), 409

    ac.setdefault("accounts", {})[username] = {
        "password_hash": _hash(password),
        "role": target_role,
        "enabled": True,
        "created_by": request._user,
        "created_at": now(),
        "expires_at": None,
        "last_login": None
    }
    save(ac)
    return jsonify({"success": True, "msg": f"用户 {username} 创建成功"})

@app.route("/api/admin/users/<username>/disable", methods=["POST"])
@require_role("super_admin", "admin")
def api_disable_user(username):
    ac = load()
    if username not in ac.get("accounts", {}):
        return jsonify({"success": False, "msg": "用户不存在"}), 404

    user = ac["accounts"][username]
    if user.get("role") == "super_admin":
        return jsonify({"success": False, "msg": "不能禁用超管"}), 403
    if request._role == "admin" and user.get("created_by") != request._user:
        return jsonify({"success": False, "msg": "只能管理自己创建的用户"}), 403

    user["enabled"] = not user.get("enabled", True)
    save(ac)
    s = "启用" if user["enabled"] else "禁用"
    return jsonify({"success": True, "msg": f"用户 {username} 已{s}，记录完整保留"})

@app.route("/api/admin/users/<username>/password", methods=["PUT"])
@require_role("super_admin", "admin")
def api_set_password(username):
    data = request.get_json(force=True)
    new_pwd = data.get("password", "")
    if not new_pwd or len(new_pwd) < 4:
        return jsonify({"success": False, "msg": "密码至少4字符"}), 400

    ac = load()
    if username not in ac.get("accounts", {}):
        return jsonify({"success": False, "msg": "用户不存在"}), 404

    user = ac["accounts"][username]
    if request._role == "admin" and user.get("created_by") != request._user:
        return jsonify({"success": False, "msg": "只能修改自己创建的用户密码"}), 403

    user["password_hash"] = _hash(new_pwd)
    save(ac)
    return jsonify({"success": True, "msg": f"用户 {username} 密码已修改"})

@app.route("/api/admin/users/<username>/expiry", methods=["PUT"])
@require_role("super_admin", "admin")
def api_set_expiry(username):
    data = request.get_json(force=True)
    days = data.get("duration_days")

    ac = load()
    if username not in ac.get("accounts", {}):
        return jsonify({"success": False, "msg": "用户不存在"}), 404

    user = ac["accounts"][username]
    if request._role == "admin" and user.get("created_by") != request._user:
        return jsonify({"success": False, "msg": "只能管理自己创建的用户期限"}), 403

    if days is None or days < 0:
        user["expires_at"] = None
        save(ac)
        return jsonify({"success": True, "msg": f"用户 {username} 已设为永久有效"})

    user["expires_at"] = (datetime.now() + timedelta(days=days)).isoformat()
    save(ac)
    return jsonify({"success": True, "msg": f"用户 {username} 有效期已设为 {days} 天"})

@app.route("/api/admin/stats", methods=["GET"])
@require_role("super_admin", "admin")
def api_stats():
    ac = load()
    accounts = ac.get("accounts", {})
    viewer = request._user
    role = request._role

    total = enabled = 0
    for name, info in accounts.items():
        if info.get("role") == "super_admin":
            continue
        if role == "admin" and info.get("created_by") != viewer:
            continue
        total += 1
        if info.get("enabled", True):
            enabled += 1

    return jsonify({
        "success": True, "stats": {"total": total, "enabled": enabled, "disabled": total - enabled}
    })

# ─── Web 管理面板 ─────────────────────────────────────────────────────────────

PAGE_LOGIN = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FaceMagic 管理面板</title>
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
<p>管理员专用</p>
{error}
<form method="post">
<input type="password" name="password" placeholder="管理密码" autofocus required>
<button type="submit">登 录</button>
</form>
</div>
</body></html>"""

def dashboard_html(accounts, viewer, role):
    rows = ""
    total = enabled = 0
    for name, info in sorted(accounts.items()):
        if info.get("role") == "super_admin":
            continue
        if role == "admin" and info.get("created_by") != viewer:
            continue

        total += 1
        if info.get("enabled", True):
            enabled += 1

        s_cls = "status-on" if info.get("enabled", True) else "status-off"
        s_txt = "启用" if info.get("enabled", True) else "禁用"
        created = (info.get("created_at", "") or "")[:10] or "-"
        expires = info.get("expires_at", "") or "永久"
        last_login = (info.get("last_login", "") or "")[:16] or "从未"
        toggle_txt = "禁用" if info.get("enabled", True) else "启用"
        toggle_cls = "btn-warn" if info.get("enabled", True) else "btn-ok"

        rows += f"""<tr><td><strong>{name}</strong><br><span style="font-size:11px;color:#888">{info.get("role","user")}</span></td>
<td class="{s_cls}">{s_txt}</td>
<td>{created}</td>
<td>{expires}</td>
<td>{last_login}</td>
<td class="actions">
<button class="btn btn-sm {toggle_cls}" onclick="apiToggle('{name}')">{toggle_txt}</button>
<button class="btn btn-sm btn-outline" onclick="showPwd('{name}')">改密</button>
<button class="btn btn-sm btn-outline" onclick="showExp('{name}')">期限</button>
</td></tr>"""

    if not rows:
        rows = '<tr><td colspan="6" class="empty">暂无用户</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FaceMagic 管理面板</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,sans-serif;background:#1a1a2e;color:#e0e0e0;padding:20px;font-size:14px}}
.header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;padding-bottom:16px;border-bottom:1px solid #0f3460}}
h1{{color:#e94560;font-size:22px}}
.header-right{{display:flex;gap:12px;align-items:center;color:#888;font-size:13px}}
.btn{{padding:8px 16px;border-radius:6px;border:none;cursor:pointer;font-size:13px;font-weight:bold;text-decoration:none;display:inline-block}}
.btn-danger{{background:#e94560;color:#fff}}.btn-danger:hover{{background:#ff6b81}}
.btn-sm{{padding:4px 10px;font-size:12px}}
.btn-warn{{background:#ffd93d;color:#1a1a2e}}
.btn-ok{{background:#6bcb77;color:#1a1a2e}}
.btn-outline{{background:transparent;border:1px solid #0f3460;color:#e0e0e0;cursor:pointer}}.btn-outline:hover{{border-color:#e94560}}
.stats{{display:flex;gap:16px;margin-bottom:24px}}
.stat-card{{background:#16213e;padding:16px 20px;border-radius:8px;flex:1;text-align:center}}
.stat-card .num{{font-size:28px;font-weight:bold;color:#e94560}}
.stat-card .label{{font-size:12px;color:#888;margin-top:4px}}
.form-row{{display:flex;gap:12px;margin-bottom:24px;align-items:center;background:#16213e;padding:16px;border-radius:8px;flex-wrap:wrap}}
.form-row input{{padding:8px 12px;background:#0f3460;border:1px solid #1a3a6b;border-radius:6px;color:#e0e0e0;font-size:13px}}
.form-row input:focus{{outline:none;border-color:#e94560}}
table{{width:100%;border-collapse:collapse;background:#16213e;border-radius:8px;overflow:hidden}}
th{{background:#0f3460;color:#888;font-size:12px;padding:12px 16px;text-align:left;font-weight:normal;white-space:nowrap}}
td{{padding:12px 16px;border-top:1px solid #0f3460;font-size:13px}}
tr:hover{{background:rgba(233,69,96,.05)}}
.status-on{{color:#6bcb77;font-weight:bold}}.status-off{{color:#ff6b6b;font-weight:bold}}
.actions{{display:flex;gap:6px;flex-wrap:wrap}}
.empty{{text-align:center;padding:40px;color:#555;font-size:14px}}
.alert{{display:none;padding:10px 16px;border-radius:6px;margin-bottom:16px;font-size:13px}}
.alert-success{{display:block;background:rgba(107,203,119,.15);color:#6bcb77;border:1px solid rgba(107,203,119,.3)}}
.alert-error{{display:block;background:rgba(255,107,107,.15);color:#ff6b6b;border:1px solid rgba(255,107,107,.3)}}
.modal{{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.6);justify-content:center;align-items:center;z-index:100}}
.modal.show{{display:flex}}
.modal-content{{background:#16213e;padding:24px;border-radius:12px;width:380px;max-width:90%}}
.modal-content h3{{color:#e94560;margin-bottom:16px;font-size:16px}}
.modal-content p{{color:#888;margin-bottom:16px}}
.modal-content input{{width:100%;padding:10px;background:#0f3460;border:1px solid #1a3a6b;border-radius:6px;color:#e0e0e0;font-size:14px;margin-bottom:12px}}
.modal-content input:focus{{outline:none;border-color:#e94560}}
.modal-btns{{display:flex;gap:10px;justify-content:flex-end;align-items:center}}
.duration-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px}}
.duration-btn{{padding:10px;background:#0f3460;border:1px solid #1a3a6b;border-radius:6px;color:#e0e0e0;font-size:13px;cursor:pointer;text-align:center}}
.duration-btn:hover{{border-color:#e94560}}
.duration-btn.active{{border-color:#6bcb77;background:rgba(107,203,119,.1);color:#6bcb77}}
</style></head>
<body>
<div class="header">
<h1>FaceMagic 管理面板</h1>
<div class="header-right"><span>{viewer} ({role})</span><span>{total} 个用户</span><a href="/admin/logout" class="btn btn-outline btn-sm">退出</a></div>
</div>
<div id="alert" class="alert"></div>
<div class="stats">
<div class="stat-card"><div class="num">{total}</div><div class="label">总用户</div></div>
<div class="stat-card"><div class="num">{enabled}</div><div class="label">已启用</div></div>
<div class="stat-card"><div class="num">{total - enabled}</div><div class="label">已禁用</div></div>
</div>
<div class="form-row">
<input type="text" id="newUsername" placeholder="用户名" style="flex:1;min-width:120px">
<input type="password" id="newPassword" placeholder="密码" style="flex:1;min-width:120px">
<button class="btn btn-ok" onclick="createUser()">添加用户</button>
</div>
<table><thead><tr><th>用户名</th><th>状态</th><th>创建时间</th><th>有效期</th><th>最后登录</th><th>操作</th></tr></thead><tbody>{rows}</tbody></table>
<div id="pwdModal" class="modal"><div class="modal-content"><h3>修改密码</h3><p id="pwdUser"></p><input type="text" id="newPwd" placeholder="新密码"><div class="modal-btns"><button class="btn btn-outline" onclick="closePwd()">取消</button><button class="btn btn-danger" onclick="confirmPwd()">确认</button></div></div></div>
<div id="expModal" class="modal"><div class="modal-content"><h3>设置期限</h3><p id="expUser"></p><div class="duration-grid"><div class="duration-btn" data-d="7" onclick="sel(this)">7天</div><div class="duration-btn" data-d="30" onclick="sel(this)">30天</div><div class="duration-btn" data-d="90" onclick="sel(this)">90天</div><div class="duration-btn" data-d="365" onclick="sel(this)">1年</div></div><div class="modal-btns" style="justify-content:space-between"><button class="btn btn-ok" onclick="confirmExp(-1)">永久</button><div><button class="btn btn-outline" onclick="closeExp()">取消</button><button class="btn btn-danger" onclick="confirmExp(0)">确认</button></div></div></div></div>
<script>
let pwu=null,exu=null,sd=null;
function q(s){{return document.querySelector(s)}}
function al(m,t){{const e=q('#alert');e.textContent=m;e.className='alert alert-'+t}}
function api(p,o){{return fetch(p,{{...o,headers:{{'Content-Type':'application/json',...o?.headers}}}}).then(r=>r.json())}}
function createUser(){{const u=q('#newUsername').value.trim(),p=q('#newPassword').value.trim();if(!u||!p){{al('请填写用户名和密码','error');return}}
api('/api/admin/users',{{method:'POST',body:JSON.stringify({{username:u,password:p}})}}).then(r=>{{al(r.msg,r.success?'success':'error');if(r.success)location.reload()}})}}
function apiToggle(u){{api('/api/admin/users/'+u+'/disable',{{method:'POST'}}).then(r=>{{al(r.msg,r.success?'success':'error');if(r.success)location.reload()}})}}
function showPwd(u){{pwu=u;q('#pwdUser').textContent='用户: '+u;q('#newPwd').value='';q('#pwdModal').classList.add('show')}}
function closePwd(){{q('#pwdModal').classList.remove('show');pwu=null}}
function confirmPwd(){{const p=q('#newPwd').value.trim();if(!p||p.length<4){{al('密码至少4字符','error');return}}
api('/api/admin/users/'+pwu+'/password',{{method:'PUT',body:JSON.stringify({{password:p}})}}).then(r=>{{al(r.msg,r.success?'success':'error');closePwd()}})}}
function showExp(u){{exu=u;sd=null;q('#expUser').textContent='用户: '+u;document.querySelectorAll('.duration-btn').forEach(b=>b.classList.remove('active'));q('#expModal').classList.add('show')}}
function closeExp(){{q('#expModal').classList.remove('show');exu=null;sd=null}}
function sel(el){{document.querySelectorAll('.duration-btn').forEach(b=>b.classList.remove('active'));el.classList.add('active');sd=parseInt(el.dataset.d)}}
function confirmExp(d){{if(d>=0&&sd===null){{al('请选择期限','error');return}}
api('/api/admin/users/'+exu+'/expiry',{{method:'PUT',body:JSON.stringify({{duration_days:d>=0?d:sd}})}}).then(r=>{{al(r.msg,r.success?'success':'error');if(r.success)location.reload();closeExp()}})}}
document.querySelectorAll('.modal').forEach(m=>{{m.addEventListener('click',function(e){{if(e.target===this)this.classList.remove('show')}})}})
</script></body></html>"""

@app.route("/admin/")
@app.route("/admin")
def admin_page():
    token = request.cookies.get("admin_token", "")
    r = authorize(token, ["admin_panel"])
    if r:
        # Re-login as the actual user
        pass

    # 先尝试用 admin_panel session，然后检查 login form
    ac = load()
    s = ac.get("sessions", {}).get(token, {})
    if s.get("role") == "admin_panel" and s.get("expires_at", "") > now():
        # 展示管理面板首页，需要选账号登录
        return redirect("/admin/login")

    return redirect("/admin/login")

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        pwd = request.form.get("password", "")
        ac = load()
        if _check(pwd, ac.get("admin_password_hash", "")):
            token = _token()
            ac.setdefault("sessions", {})[token] = {
                "role": "admin_panel", "created_at": now(), "expires_at": exp8h()
            }
            save(ac)
            resp = redirect("/admin/panel")
            resp.set_cookie("admin_token", token, max_age=28800, httponly=True, samesite="Lax")
            return resp
        return PAGE_LOGIN.replace("{error}", '<div class="error">密码错误</div>'), 200, {"Content-Type": "text/html"}
    return PAGE_LOGIN.replace("{error}", ""), 200, {"Content-Type": "text/html"}

@app.route("/admin/logout")
def admin_logout():
    resp = redirect("/admin/login")
    resp.set_cookie("admin_token", "", max_age=0)
    return resp

@app.route("/admin/panel", methods=["GET"])
def admin_panel():
    token = request.cookies.get("admin_token", "")
    ac = load()
    s = ac.get("sessions", {}).get(token, {})
    if s.get("role") != "admin_panel" or s.get("expires_at", "") < now():
        return redirect("/admin/login")

    # 管理员先选自己要操作的账号登录
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FaceMagic 管理面板 - 选择账号</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,sans-serif;background:#1a1a2e;color:#e0e0e0;display:flex;justify-content:center;align-items:center;min-height:100vh;padding:20px}}
.card{{background:#16213e;padding:40px;border-radius:12px;width:400px;box-shadow:0 8px 32px rgba(0,0,0,.3)}}
h1{{color:#e94560;text-align:center;margin-bottom:24px;font-size:20px}}
.btn{{display:block;width:100%;padding:14px;border-radius:8px;border:1px solid #0f3460;background:#0f3460;color:#e0e0e0;font-size:14px;cursor:pointer;text-align:center;margin-bottom:12px;text-decoration:none}}
.btn:hover{{border-color:#e94560;background:#1a3a6b}}
.btn-admin{{border-color:#e94560;color:#e94560}}
p{{color:#888;text-align:center;margin-bottom:20px;font-size:13px}}
</style></head>
<body>
<div class="card">
<h1>FaceMagic 管理面板</h1>
<p>选择要管理的账号登录</p>
<a href="/admin/login-as?user=a522352377" class="btn btn-admin">超管 - a522352377</a>
<a href="/admin/login-as?user=xianqi5223" class="btn">管理 - xianqi5223</a>
</div>
</body></html>"""

@app.route("/admin/login-as", methods=["GET"])
def admin_login_as():
    username = request.args.get("user", "")
    if username not in ("a522352377", "xianqi5223"):
        return redirect("/admin/panel")

    token = request.cookies.get("admin_token", "")
    ac = load()
    s = ac.get("sessions", {}).get(token, {})
    if s.get("role") != "admin_panel" or s.get("expires_at", "") < now():
        return redirect("/admin/login")

    # 创建操作 session
    op_token = _token()
    ac.setdefault("sessions", {})[op_token] = {
        "role": ac["accounts"][username]["role"],
        "username": username,
        "created_at": now(), "expires_at": exp8h()
    }
    save(ac)
    resp = redirect("/admin/dashboard")
    resp.set_cookie("op_token", op_token, max_age=28800, httponly=True, samesite="Lax")
    return resp

@app.route("/admin/dashboard", methods=["GET"])
def admin_dashboard():
    op_token = request.cookies.get("op_token", "")
    ac = load()
    s = ac.get("sessions", {}).get(op_token, {})
    role = s.get("role", "")
    username = s.get("username", "")
    if not role or s.get("expires_at", "") < now():
        return redirect("/admin/panel")

    user_info = ac.get("accounts", {}).get(username, {})
    html = dashboard_html(ac.get("accounts", {}), username, role)
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}
