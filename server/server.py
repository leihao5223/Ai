"""FaceMagic 账号验证服务器 — 零依赖，极致轻量"""
import json, os, hashlib, secrets, time
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_FILE = os.path.join(BASE_DIR, "accounts.json")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin888")

# ─── 数据 ──────────────────────────────────────────────────────────────────────

_cache, _mtime = None, 0

def _seed():
    n = datetime.now().isoformat()
    return {
        "accounts": {
            "a522352377": {"role":"super_admin","enabled":True,"created_by":"system",
                "password_hash":_hash("Qq1314520."),"created_at":n,"expires_at":None,"last_login":None},
            "xianqi5223": {"role":"admin","enabled":True,"created_by":"a522352377",
                "password_hash":_hash("Aa112211"),"created_at":n,"expires_at":None,"last_login":None}
        }, "sessions": {}, "admin_password_hash": None
    }

def load():
    global _cache, _mtime
    try:
        mt = os.path.getmtime(ACCOUNTS_FILE) if os.path.exists(ACCOUNTS_FILE) else 0
        if _cache and mt <= _mtime: return _cache
        if not os.path.exists(ACCOUNTS_FILE):
            _cache, _mtime = _seed(), mt
            return _cache
        with open(ACCOUNTS_FILE) as f: _cache = json.load(f)
        _mtime = mt
        _cache.setdefault("accounts", {})
        for k, v in _seed()["accounts"].items():
            _cache["accounts"].setdefault(k, v)
        return _cache
    except:
        _cache = _seed()
        return _cache

def save(d):
    global _cache, _mtime
    _cache, _mtime = d, time.time()
    with open(ACCOUNTS_FILE, "w") as f: json.dump(d, f, indent=2, ensure_ascii=False)

def _hash(p, s=None):
    s = s or secrets.token_hex(16)
    return f"{s}${hashlib.sha256((s+p).encode()).hexdigest()}"

def _check(p, s):
    return s and "$" in s and _hash(p, s.split("$",1)[0]) == s

def _token(): return secrets.token_hex(32)
_now = lambda: datetime.now().isoformat()
_exp8h = lambda: (datetime.now()+timedelta(hours=8)).isoformat()
_exp7d = lambda: (datetime.now()+timedelta(days=7)).isoformat()

def jsonr(d, s=200):
    return s, {"Content-Type":"application/json; charset=utf-8"}, json.dumps(d, ensure_ascii=False).encode()

def htmlr(h, s=200):
    return s, {"Content-Type":"text/html; charset=utf-8"}, h.encode()

def redir(p):
    return 302, {"Location": p}, b""

def setc(r, n, v, ma=None):
    r[1]["Set-Cookie"] = f"{n}={v}; Path=/; HttpOnly; SameSite=Lax"+(f"; Max-Age={ma}" if ma else "")

# ─── 路由 ──────────────────────────────────────────────────────────────────────

def route(method, path, body, cookies):
    # favicon
    if path == "/favicon.ico": return 204, {}, b""

    ac = load()

    # GET /
    if method == "GET" and path == "/":
        return jsonr({"name":"FaceMagic Auth","version":"3.0","status":"running"})

    # POST /api/login
    if method == "POST" and path == "/api/login":
        d = json.loads(body)
        u, p = d.get("username","").strip(), d.get("password","")
        if not u or not p: return jsonr({"success":False,"msg":"用户名和密码不能为空"}, 400)
        user = ac.get("accounts",{}).get(u)
        if not user or not _check(p, user.get("password_hash","")):
            return jsonr({"success":False,"msg":"用户名或密码错误"}, 401)
        if not user.get("enabled",True): return jsonr({"success":False,"msg":"账号已被禁用"}, 403)
        if user.get("expires_at") and datetime.now() > datetime.fromisoformat(user["expires_at"]):
            return jsonr({"success":False,"msg":"账号已过期"}, 403)
        token = _token()
        ac.setdefault("sessions",{})[token] = {"username":u,"role":user["role"],"created_at":_now(),"expires_at":_exp7d()}
        user["last_login"] = _now()
        save(ac)
        rdays = 0
        if user.get("expires_at"):
            rd = datetime.fromisoformat(user["expires_at"]) - datetime.now()
            rdays = max(1, rd.days)
            msg = f"登录成功，账号剩余 {rdays} 天"
        else:
            msg = "登录成功（永久有效）"
        return jsonr({"success":True,"msg":msg,"token":token,"username":u,"role":user["role"],"remaining_days":rdays})

    # POST /api/verify
    if method == "POST" and path == "/api/verify":
        d = json.loads(body)
        s = ac.get("sessions",{}).get(d.get("token",""),{})
        if not s or s.get("expires_at","") < _now():
            return jsonr({"success":False,"valid":False}, 401)
        return jsonr({"success":True,"valid":True,"username":s["username"]})

    # ─── 管理 ──────────────────────────────────────────────────────────────

    def admin_session():
        t = cookies.get("op_token","")
        s = ac.get("sessions",{}).get(t,{})
        return (s.get("username",""), s.get("role","")) if s.get("role") in ("super_admin","admin") and s.get("expires_at","") > _now() else (None,None)

    viewer, vrole = admin_session()

    # POST /api/admin/login
    if path == "/api/admin/login" and method == "POST":
        d = json.loads(body)
        if not _check(d.get("password",""), ac.get("admin_password_hash","")):
            return jsonr({"success":False,"msg":"密码错误"}, 401)
        token = _token()
        ac.setdefault("sessions",{})[token] = {"role":"admin_panel","created_at":_now(),"expires_at":_exp8h()}
        save(ac)
        r = jsonr({"success":True,"token":token})
        setc(r, "admin_token", token, 28800)
        return r

    def req_admin():
        return viewer and vrole

    # GET /api/admin/users
    if method == "GET" and path == "/api/admin/users":
        if not req_admin(): return jsonr({"success":False,"msg":"无权限"}, 401)
        result = []
        for n, i in ac.get("accounts",{}).items():
            if i.get("role") == "super_admin": continue
            if vrole == "admin" and i.get("created_by") != viewer: continue
            result.append({"username":n,"role":i.get("role","user"),"enabled":i.get("enabled",True),
                "created_by":i.get("created_by",""),"created_at":i.get("created_at",""),
                "expires_at":i.get("expires_at","") or None,"last_login":i.get("last_login","")})
        return jsonr({"success":True,"users":result})

    # POST /api/admin/users
    if method == "POST" and path == "/api/admin/users":
        if not req_admin(): return jsonr({"success":False,"msg":"无权限"}, 401)
        d = json.loads(body)
        u, p, tr = d.get("username","").strip().lower(), d.get("password",""), d.get("role","user")
        if not u or not p: return jsonr({"success":False,"msg":"用户名和密码不能为空"}, 400)
        if len(u) < 3: return jsonr({"success":False,"msg":"用户名至少3字符"}, 400)
        if len(p) < 4: return jsonr({"success":False,"msg":"密码至少4字符"}, 400)
        if vrole == "admin" and tr != "user": return jsonr({"success":False,"msg":"无权限创建此角色"}, 403)
        if u in ac.get("accounts",{}): return jsonr({"success":False,"msg":"用户名已存在"}, 409)
        ac.setdefault("accounts",{})[u] = {"password_hash":_hash(p),"role":tr,"enabled":True,"created_by":viewer,
            "created_at":_now(),"expires_at":None,"last_login":None}
        save(ac)
        return jsonr({"success":True,"msg":f"用户 {u} 创建成功"})

    # POST /api/admin/users/<name>/disable
    if method == "POST" and "/disable" in path:
        if not req_admin(): return jsonr({"success":False,"msg":"无权限"}, 401)
        uname = path.split("/")[4]
        if uname not in ac.get("accounts",{}): return jsonr({"success":False,"msg":"用户不存在"}, 404)
        user = ac["accounts"][uname]
        if user.get("role") == "super_admin": return jsonr({"success":False,"msg":"不能禁用超管"}, 403)
        if vrole == "admin" and user.get("created_by") != viewer: return jsonr({"success":False,"msg":"只能管理自己的用户"}, 403)
        user["enabled"] = not user.get("enabled",True)
        save(ac)
        s = "启用" if user["enabled"] else "禁用"
        return jsonr({"success":True,"msg":f"用户 {uname} 已{s}，记录完整保留"})

    # PUT /api/admin/users/<name>/password
    if method == "PUT" and "/password" in path:
        if not req_admin(): return jsonr({"success":False,"msg":"无权限"}, 401)
        uname = path.split("/")[4]
        d = json.loads(body)
        np = d.get("password","")
        if not np or len(np) < 4: return jsonr({"success":False,"msg":"密码至少4字符"}, 400)
        if uname not in ac.get("accounts",{}): return jsonr({"success":False,"msg":"用户不存在"}, 404)
        user = ac["accounts"][uname]
        if vrole == "admin" and user.get("created_by") != viewer: return jsonr({"success":False,"msg":"只能修改自己的用户密码"}, 403)
        user["password_hash"] = _hash(np)
        save(ac)
        return jsonr({"success":True,"msg":f"用户 {uname} 密码已修改"})

    # PUT /api/admin/users/<name>/expiry
    if method == "PUT" and "/expiry" in path:
        if not req_admin(): return jsonr({"success":False,"msg":"无权限"}, 401)
        uname = path.split("/")[4]
        d = json.loads(body)
        days = d.get("duration_days")
        if uname not in ac.get("accounts",{}): return jsonr({"success":False,"msg":"用户不存在"}, 404)
        user = ac["accounts"][uname]
        if vrole == "admin" and user.get("created_by") != viewer: return jsonr({"success":False,"msg":"只能管理自己的用户期限"}, 403)
        if days is None or days < 0:
            user["expires_at"] = None
            save(ac)
            return jsonr({"success":True,"msg":f"用户 {uname} 已设为永久有效"})
        user["expires_at"] = (datetime.now()+timedelta(days=days)).isoformat()
        save(ac)
        return jsonr({"success":True,"msg":f"用户 {uname} 有效期已设为 {days} 天"})

    # GET /api/admin/stats
    if method == "GET" and path == "/api/admin/stats":
        if not req_admin(): return jsonr({"success":False,"msg":"无权限"}, 401)
        total = enabled = 0
        for n, i in ac.get("accounts",{}).items():
            if i.get("role") == "super_admin": continue
            if vrole == "admin" and i.get("created_by") != viewer: continue
            total += 1
            if i.get("enabled",True): enabled += 1
        return jsonr({"success":True,"stats":{"total":total,"enabled":enabled,"disabled":total-enabled}})

    # ─── Web ──────────────────────────────────────────────────────────────────

    _DASH_TPL = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FaceMagic 管理面板</title><style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#1a1a2e;color:#e0e0e0;padding:20px}
.top{max-width:1200px;margin:0 auto}
h1{color:#e94560;font-size:20px;margin-bottom:4px}
.sub{color:#888;font-size:13px;margin-bottom:20px}
.stats{display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap}
.stat{background:#16213e;padding:16px 20px;border-radius:8px;min-width:120px}
.stat .n{font-size:24px;font-weight:bold}
.stat .l{font-size:12px;color:#888;margin-top:2px}
.stat-blue .n{color:#4fc3f7}.stat-green .n{color:#66bb6a}.stat-red .n{color:#ef5350}
.card{background:#16213e;border-radius:8px;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:10px 14px;text-align:left;border-bottom:1px solid #0f3460;white-space:nowrap}
th{color:#888;font-weight:500;font-size:12px;text-transform:uppercase;letter-spacing:.5px}
tr:hover td{background:#1a3a6b44}
.status-on{color:#66bb6a}.status-off{color:#ef5350}
.actions{text-align:right}
.btn{display:inline-block;padding:6px 14px;border-radius:4px;border:none;font-size:12px;cursor:pointer;color:#fff}
.btn-sm{padding:4px 10px;font-size:11px;margin-left:4px}
.btn-warn{background:#e94560}.btn-warn:hover{background:#ff6b81}
.btn-ok{background:#2e7d32}.btn-ok:hover{background:#388e3c}
.btn-outline{background:0 0;border:1px solid #0f3460;color:#aaa}.btn-outline:hover{border-color:#e94560;color:#e94560}
.empty{text-align:center;color:#555;padding:30px!important}
.add-bar{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.add-bar input{flex:1;min-width:120px;padding:8px 12px;background:#0f3460;border:1px solid #1a3a6b;border-radius:4px;color:#e0e0e0;font-size:13px}
.add-bar input:focus{outline:none;border-color:#e94560}
.add-bar .btn-add{background:#e94560;color:#fff;border:none;border-radius:4px;padding:8px 20px;font-size:13px;cursor:pointer}
.add-bar .btn-add:hover{background:#ff6b81}
.modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.6);justify-content:center;align-items:center;z-index:100}
.modal.show{display:flex}
.modal-box{background:#16213e;padding:30px;border-radius:8px;width:360px}
.modal-box h3{color:#e94560;margin-bottom:16px;font-size:16px}
.modal-box input{width:100%;padding:10px;background:#0f3460;border:1px solid #1a3a6b;border-radius:4px;color:#e0e0e0;font-size:13px;margin-bottom:12px}
.modal-box input:focus{outline:none;border-color:#e94560}
.modal-btns{display:flex;gap:8px;justify-content:flex-end;margin-top:8px}
.modal-btns button{padding:8px 20px;border:none;border-radius:4px;font-size:13px;cursor:pointer}
.modal-btns .btn-cancel{background:#333;color:#aaa}.modal-btns .btn-cancel:hover{background:#444}
</style></head><body>
<div class="top">
<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap">
<div><h1>FaceMagic 管理面板</h1><p class="sub">{{uname}} · {{role}}</p></div>
<a href="/admin/logout" style="color:#888;font-size:13px;text-decoration:none;padding:8px 0;display:inline-block">退出</a>
</div>

<div class="stats">
<div class="stat stat-blue"><div class="n">{{total}}</div><div class="l">总用户</div></div>
<div class="stat stat-green"><div class="n">{{enabled}}</div><div class="l">已启用</div></div>
<div class="stat stat-red"><div class="n">{{disabled}}</div><div class="l">已禁用</div></div>
</div>

<div class="add-bar">
<input id="nu" placeholder="用户名" onkeydown="if(event.key==='Enter') addUser()">
<input id="np" type="password" placeholder="密码" onkeydown="if(event.key==='Enter') addUser()">
<button class="btn-add" onclick="addUser()">创建用户</button>
</div>

<div class="card"><table>
<thead><tr><th>用户</th><th>状态</th><th>创建时间</th><th>有效期</th><th>最后登录</th><th style="text-align:right">操作</th></tr></thead>
<tbody>{{rows}}</tbody>
</table></div></div>

<div id="pwdModal" class="modal" onclick="if(event.target===this)hideModal('pwdModal')"><div class="modal-box">
<h3>修改密码</h3>
<input id="pwdUser" type="hidden">
<input id="pwdVal" type="password" placeholder="新密码（至少4位）" onkeydown="if(event.key==='Enter')changePwd()">
<div class="modal-btns"><button class="btn-cancel" onclick="hideModal('pwdModal')">取消</button><button class="btn-add" onclick="changePwd()">确认</button></div>
</div></div>

<div id="expModal" class="modal" onclick="if(event.target===this)hideModal('expModal')"><div class="modal-box">
<h3>设置期限</h3>
<input id="expUser" type="hidden">
<input id="expVal" type="number" min="0" placeholder="天数（0=永久，空=永久）" onkeydown="if(event.key==='Enter')setExpiry()">
<div class="modal-btns"><button class="btn-cancel" onclick="hideModal('expModal')">取消</button><button class="btn-add" onclick="setExpiry()">确认</button></div>
</div></div>

<script>
const _u='{{uname}}';let _e;
function apiToggle(n){fetch('/api/admin/users/'+n+'/disable',{method:'POST'}).then(r=>r.json()).then(d=>{if(d.success)location.reload();else alert(d.msg)}).catch(()=>alert('请求失败'))}
function showPwd(n){document.getElementById('pwdUser').value=n;document.getElementById('pwdVal').value='';document.getElementById('pwdModal').classList.add('show');setTimeout(()=>document.getElementById('pwdVal').focus(),100)}
function hideModal(i){document.getElementById(i).classList.remove('show')}
function changePwd(){var n=document.getElementById('pwdUser').value,p=document.getElementById('pwdVal').value;if(!p||p.length<4){alert('密码至少4位');return}fetch('/api/admin/users/'+n+'/password',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:p})}).then(r=>r.json()).then(d=>{alert(d.msg);if(d.success)hideModal('pwdModal')}).catch(()=>alert('请求失败'))}
function setExpiry(){var n=document.getElementById('expUser').value,d=document.getElementById('expVal').value;d=d===''?null:parseInt(d);fetch('/api/admin/users/'+n+'/expiry',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({duration_days:d})}).then(r=>r.json()).then(d=>{alert(d.msg);if(d.success)hideModal('expModal');location.reload()}).catch(()=>alert('请求失败'))}
function addUser(){var u=document.getElementById('nu').value.trim(),p=document.getElementById('np').value;if(!u||!p){alert('请输入用户名和密码');return}fetch('/api/admin/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p,role:'user'})}).then(r=>r.json()).then(d=>{alert(d.msg);if(d.success){document.getElementById('nu').value='';document.getElementById('np').value='';location.reload()}}).catch(()=>alert('请求失败'))}
</script>
</body></html>"""

    ADMIN_LOGIN_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FaceMagic 管理面板</title><style>
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
</style></head><body>
<div class="card"><h1>FaceMagic 管理面板</h1><p>管理员专用</p>{error}
<form method="post"><input type="password" name="password" placeholder="管理密码" autofocus required><button type="submit">登 录</button></form></div></body></html>"""

    # GET/POST /admin/login
    if path == "/admin/login":
        if method == "POST":
            d = parse_form(body)
            pwd = d.get("password", [""])[0]
            if _check(pwd, ac.get("admin_password_hash","")):
                token = _token()
                ac.setdefault("sessions",{})[token] = {"role":"admin_panel","created_at":_now(),"expires_at":_exp8h()}
                save(ac)
                r = redir("/admin/panel")
                setc(r, "admin_token", token, 28800)
                return r
            return htmlr(ADMIN_LOGIN_HTML.replace("{error}",'<div class="error">密码错误</div>'))
        return htmlr(ADMIN_LOGIN_HTML.replace("{error}",""))

    # GET /admin/logout
    if method == "GET" and path == "/admin/logout":
        r = redir("/admin/login")
        setc(r, "admin_token", "", 0)
        setc(r, "op_token", "", 0)
        return r

    # GET /admin/panel
    if method == "GET" and path == "/admin/panel":
        t = cookies.get("admin_token","")
        s = ac.get("sessions",{}).get(t,{})
        if s.get("role") != "admin_panel" or s.get("expires_at","") < _now():
            return redir("/admin/login")
        return htmlr(f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FaceMagic 管理面板</title><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,sans-serif;background:#1a1a2e;color:#e0e0e0;display:flex;justify-content:center;align-items:center;min-height:100vh;padding:20px}}
.card{{background:#16213e;padding:40px;border-radius:12px;width:400px;box-shadow:0 8px 32px rgba(0,0,0,.3)}}
h1{{color:#e94560;text-align:center;margin-bottom:24px;font-size:20px}}
.btn{{display:block;width:100%;padding:14px;border-radius:8px;border:1px solid #0f3460;background:#0f3460;color:#e0e0e0;font-size:14px;cursor:pointer;text-align:center;margin-bottom:12px;text-decoration:none}}
.btn:hover{{border-color:#e94560;background:#1a3a6b}}
.btn-admin{{border-color:#e94560;color:#e94560}}
p{{color:#888;text-align:center;margin-bottom:20px;font-size:13px}}
</style></head><body>
<div class="card"><h1>FaceMagic 管理面板</h1><p>选择要管理的账号登录</p>
<a href="/admin/login-as?user=a522352377" class="btn btn-admin">超管 - a522352377</a>
<a href="/admin/login-as?user=xianqi5223" class="btn">管理 - xianqi5223</a>
</div></body></html>""")

    # GET /admin/login-as
    if method == "GET" and path.startswith("/admin/login-as"):
        uname = parse_qs(path).get("user", [""])[0]
        if uname not in ("a522352377","xianqi5223"):
            return redir("/admin/panel")
        t = cookies.get("admin_token","")
        s = ac.get("sessions",{}).get(t,{})
        if s.get("role") != "admin_panel" or s.get("expires_at","") < _now():
            return redir("/admin/login")
        op_token = _token()
        ac.setdefault("sessions",{})[op_token] = {"username":uname,"role":ac["accounts"][uname]["role"],
            "created_at":_now(),"expires_at":_exp8h()}
        save(ac)
        r = redir("/admin/dashboard")
        setc(r, "op_token", op_token, 28800)
        return r

    # GET /admin/dashboard
    if method == "GET" and path == "/admin/dashboard":
        t = cookies.get("op_token","")
        s = ac.get("sessions",{}).get(t,{})
        role, uname = s.get("role",""), s.get("username","")
        if not role or s.get("expires_at","") < _now():
            return redir("/admin/panel")

        rows = ""
        total = enabled = 0
        for n, i in sorted(ac.get("accounts",{}).items()):
            if i.get("role") == "super_admin": continue
            if role == "admin" and i.get("created_by") != uname: continue
            total += 1
            if i.get("enabled",True): enabled += 1
            sc = "status-on" if i.get("enabled",True) else "status-off"
            st = "启用" if i.get("enabled",True) else "禁用"
            created = (i.get("created_at","") or "")[:10] or "-"
            expires = i.get("expires_at","") or "永久"
            last = (i.get("last_login","") or "")[:16] or "从未"
            tt = "禁用" if i.get("enabled",True) else "启用"
            tc = "btn-warn" if i.get("enabled",True) else "btn-ok"
            rows += '<tr><td><strong>%s</strong><br><span style="font-size:11px;color:#888">%s</span></td>' % (n, i.get("role","user"))
            rows += '<td class="%s">%s</td><td>%s</td><td>%s</td><td>%s</td>' % (sc, st, created, expires, last)
            rows += '<td class="actions">'
            rows += '<button class="btn btn-sm %s" onclick="apiToggle(\'%s\')">%s</button>' % (tc, n, tt)
            rows += '<button class="btn btn-sm btn-outline" onclick="showPwd(\'%s\')">改密</button>' % n
            rows += '<button class="btn btn-sm btn-outline" onclick="showExp(\'%s\')">期限</button>' % n
            rows += '</td></tr>'
        if not rows: rows = '<tr><td colspan="6" class="empty">暂无用户</td></tr>'

        html = _DASH_TPL.replace("{{uname}}", uname).replace("{{role}}", role)
        html = html.replace("{{total}}", str(total)).replace("{{enabled}}", str(enabled))
        html = html.replace("{{disabled}}", str(total - enabled)).replace("{{rows}}", rows)
        return htmlr(html)

    return jsonr({"error":"Not Found"}, 404)

def parse_form(b):
    from urllib.parse import unquote_plus
    r = {}
    if b:
        for p in b.decode().split("&"):
            if "=" in p:
                k, v = p.split("=", 1)
                r.setdefault(k,[]).append(unquote_plus(v))
    return r

def parse_qs(p):
    from urllib.parse import unquote_plus
    r = {}
    if "?" in p:
        for part in p.split("?",1)[1].split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                r.setdefault(k,[]).append(unquote_plus(v))
    return r

class Handler(BaseHTTPRequestHandler):
    def do_GET(self): self._handle("GET")
    def do_POST(self): self._handle("POST")
    def do_PUT(self): self._handle("PUT")
    def do_DELETE(self): self._handle("DELETE")
    def _handle(self, method):
        try:
            cl = int(self.headers.get("Content-Length",0))
            body = self.rfile.read(cl) if cl > 0 else b""
            cookies = {}
            for c in self.headers.get("Cookie","").split(";"):
                c = c.strip()
                if "=" in c:
                    k, v = c.split("=", 1)
                    cookies[k.strip()] = v.strip()
            status, headers, data = route(method, self.path, body, cookies)
            self.send_response(status)
            for k, v in headers.items(): self.send_header(k, v)
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            try:
                self.send_response(500)
                self.send_header("Content-Type","application/json; charset=utf-8")
                self.send_header("Connection","close")
                self.end_headers()
                self.wfile.write(json.dumps({"error":str(e)}).encode())
            except: pass
    def log_message(self, *a): pass

def ensure_admin():
    os.makedirs(BASE_DIR, exist_ok=True)
    d = load()
    if not d.get("admin_password_hash"):
        d["admin_password_hash"] = _hash(ADMIN_PASSWORD)
        save(d)
        print(f"  管理密码: {ADMIN_PASSWORD}")
    # 清理过期 sessions
    n = _now()
    for k in list(d.get("sessions",{}).keys()):
        if d["sessions"][k].get("expires_at","") < n:
            del d["sessions"][k]
    save(d)

if __name__ == "__main__":
    ensure_admin()
    print("="*48)
    print("  FaceMagic 账号验证服务器 v3.0")
    print("  零依赖 | 极致轻量")
    print("="*48)
    print(f"  数据文件: {ACCOUNTS_FILE}")
    print(f"  管理面板: http://127.0.0.1:5000/admin/")
    print(f"  管理密码: {ADMIN_PASSWORD}")
    print("="*48)
    HTTPServer(("0.0.0.0", 5000), Handler).serve_forever()
