"""FaceMagic 卡密验证服务器 — 在 Termux 中运行"""
import json
import sqlite3
import hashlib
import hmac
import os
import secrets
import string
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)
ADMIN_TOKEN = "admin888"

DB_PATH = os.path.join(os.path.dirname(__file__), "cards.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_key TEXT UNIQUE NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('day','month','year')),
            duration_days INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'unused' CHECK(status IN ('unused','used','expired')),
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            used_at TEXT,
            activated_at TEXT,
            expires_at TEXT,
            device_id TEXT,
            last_checkin TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            detail TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.commit()
    conn.close()

def generate_card_key():
    chars = string.ascii_uppercase + string.digits
    groups = []
    for _ in range(4):
        groups.append(''.join(secrets.choice(chars) for _ in range(4)))
    return 'AI-' + '-'.join(groups)

def verify_hmac(data, signature, secret="facemagic_secret_2025"):
    expected = hmac.new(secret.encode(), json.dumps(data, sort_keys=True).encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

@app.route('/')
def index():
    return jsonify({"name": "FaceMagic Auth Server", "status": "running"})

@app.route('/verify', methods=['POST'])
def verify_card():
    data = request.get_json(force=True)
    card_key = data.get('card_key', '').strip().upper()
    device_id = data.get('device_id', '')

    if not card_key or not device_id:
        return jsonify({"success": False, "msg": "卡密和设备ID不能为空"}), 400

    conn = get_db()
    row = conn.execute("SELECT * FROM cards WHERE card_key = ?", (card_key,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "msg": "卡密不存在"}), 404

    row = dict(row)
    now = datetime.now()

    if row['status'] == 'used':
        expires_at = datetime.fromisoformat(row['expires_at'])
        if now < expires_at:
            conn.execute("UPDATE cards SET last_checkin = ? WHERE id = ?",
                         (now.isoformat(), row['id']))
            conn.commit()
            conn.close()
            remaining = (expires_at - now).days
            return jsonify({
                "success": True,
                "msg": f"验证成功，剩余 {remaining} 天",
                "type": row['type'],
                "expires_at": row['expires_at'],
                "remaining_days": remaining
            })
        else:
            conn.execute("UPDATE cards SET status = 'expired' WHERE id = ?", (row['id'],))
            conn.commit()
            conn.close()
            return jsonify({"success": False, "msg": "卡密已过期"}), 403

    if row['status'] == 'expired':
        conn.close()
        return jsonify({"success": False, "msg": "卡密已过期"}), 403

    # 首次激活
    if row['status'] == 'unused':
        activated_at = now.isoformat()
        expires_at_dt = now + timedelta(days=row['duration_days'])
        expires_at_str = expires_at_dt.isoformat()
        conn.execute("""
            UPDATE cards SET status='used', used_at=?, activated_at=?,
                            expires_at=?, device_id=?, last_checkin=?
            WHERE id=?
        """, (now.isoformat(), activated_at, expires_at_str, device_id, activated_at, row['id']))
        conn.commit()
        conn.close()
        return jsonify({
            "success": True,
            "msg": f"激活成功！有效期至 {expires_at_str}",
            "type": row['type'],
            "expires_at": expires_at_str,
            "remaining_days": row['duration_days']
        })

    conn.close()
    return jsonify({"success": False, "msg": "卡密状态异常"}), 500

@app.route('/check', methods=['POST'])
def check_card():
    data = request.get_json(force=True)
    card_key = data.get('card_key', '').strip().upper()

    if not card_key:
        return jsonify({"success": False, "msg": "卡密不能为空"}), 400

    conn = get_db()
    row = conn.execute("SELECT * FROM cards WHERE card_key = ?", (card_key,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "msg": "卡密不存在"}), 404

    row = dict(row)
    if row['status'] == 'used' and row['expires_at']:
        expires_at = datetime.fromisoformat(row['expires_at'])
        remaining = (expires_at - datetime.now()).days
        conn.close()
        return jsonify({
            "success": True,
            "type": row['type'],
            "expires_at": row['expires_at'],
            "remaining_days": max(0, remaining),
            "status": "valid" if remaining > 0 else "expired"
        })

    conn.close()
    return jsonify({
        "success": row['status'] == 'unused',
        "type": row['type'],
        "status": row['status']
    })

@app.route('/admin/generate', methods=['POST'])
def generate_cards():
    data = request.get_json(force=True)
    token = data.get('token', '')

    if token != ADMIN_TOKEN:
        return jsonify({"success": False, "msg": "管理令牌错误"}), 403

    card_type = data.get('type', 'day')
    count = data.get('count', 1)

    type_days = {'day': 1, 'month': 30, 'year': 365}
    if card_type not in type_days:
        return jsonify({"success": False, "msg": "类型错误: day/month/year"}), 400

    if not isinstance(count, int) or count < 1 or count > 100:
        return jsonify({"success": False, "msg": "数量范围 1-100"}), 400

    conn = get_db()
    keys = []
    for _ in range(count):
        card_key = generate_card_key()
        conn.execute(
            "INSERT INTO cards (card_key, type, duration_days) VALUES (?, ?, ?)",
            (card_key, card_type, type_days[card_type])
        )
        keys.append(card_key)

    conn.execute(
        "INSERT INTO admin_log (action, detail) VALUES (?, ?)",
        ("generate", f"生成 {count} 张 {card_type} 卡")
    )
    conn.commit()
    conn.close()

    return jsonify({"success": True, "count": count, "type": card_type, "keys": keys})

@app.route('/admin/list', methods=['POST'])
def list_cards():
    data = request.get_json(force=True)
    token = data.get('token', '')

    if token != ADMIN_TOKEN:
        return jsonify({"success": False, "msg": "管理令牌错误"}), 403

    conn = get_db()
    rows = conn.execute("SELECT * FROM cards ORDER BY id DESC LIMIT 200").fetchall()
    conn.close()
    return jsonify({"success": True, "cards": [dict(r) for r in rows]})

@app.route('/admin/delete', methods=['POST'])
def delete_card():
    data = request.get_json(force=True)
    token = data.get('token', '')
    if token != ADMIN_TOKEN:
        return jsonify({"success": False, "msg": "管理令牌错误"}), 403
    card_key = data.get('card_key', '').strip().upper()
    if not card_key:
        return jsonify({"success": False, "msg": "卡密不能为空"}), 400
    conn = get_db()
    conn.execute("DELETE FROM cards WHERE card_key = ?", (card_key,))
    deleted = conn.rowcount > 0
    conn.commit()
    conn.close()
    if deleted:
        return jsonify({"success": True, "msg": f"已删除卡密: {card_key}"})
    return jsonify({"success": False, "msg": "卡密不存在"}), 404

@app.route('/admin/stats', methods=['POST'])
def stats():
    data = request.get_json(force=True)
    token = data.get('token', '')

    if token != ADMIN_TOKEN:
        return jsonify({"success": False, "msg": "管理令牌错误"}), 403

    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    unused = conn.execute("SELECT COUNT(*) FROM cards WHERE status='unused'").fetchone()[0]
    used = conn.execute("SELECT COUNT(*) FROM cards WHERE status='used'").fetchone()[0]
    expired = conn.execute("SELECT COUNT(*) FROM cards WHERE status='expired'").fetchone()[0]
    conn.close()
    return jsonify({
        "success": True,
        "stats": {"total": total, "unused": unused, "used": used, "expired": expired}
    })

if __name__ == '__main__':
    init_db()
    print("=" * 50)
    print("  FaceMagic 卡密验证服务器")
    print("=" * 50)
    print(f"  数据库: {DB_PATH}")
    print("  ADMIN 令牌: admin888")
    print()
    print("  请在 Termux 中运行 ngrok:")
    print("  ngrok http 5000")
    print()
    print("  然后在客户端配置中设置服务端地址为 ngrok 地址")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False)
