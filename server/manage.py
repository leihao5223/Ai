#!/usr/bin/env python3
"""
FaceMagic 卡密管理工具 — 在 Termux 中使用

用法:
    python manage.py gen day 10      # 生成 10 张天卡
    python manage.py gen month 5     # 生成 5 张月卡
    python manage.py gen year 2      # 生成 2 张年卡
    python manage.py list            # 列出所有卡密
    python manage.py stats           # 统计
    python manage.py delete AI-XXXX  # 删除卡密
"""
import sys
import json
import requests

BASE_URL = "http://127.0.0.1:5000"
TOKEN = "admin888"

def api(path, data=None):
    url = f"{BASE_URL}{path}"
    if data is None:
        data = {}
    data["token"] = TOKEN
    try:
        r = requests.post(url, json=data, timeout=10)
        return r.json()
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接服务器！请先运行 python server.py")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 错误: {e}")
        sys.exit(1)

def cmd_gen(card_type, count):
    result = api("/admin/generate", {"type": card_type, "count": count})
    if result.get("success"):
        print(f"\n✅ 成功生成 {count} 张 {card_type} 卡：")
        print("-" * 40)
        for key in result["keys"]:
            print(f"  {key}")
        print("-" * 40)
    else:
        print(f"❌ {result.get('msg', '生成失败')}")

def cmd_list():
    result = api("/admin/list")
    if not result.get("success"):
        print(f"❌ {result.get('msg', '获取失败')}")
        return
    cards = result.get("cards", [])
    if not cards:
        print("暂无卡密")
        return
    print(f"\n📋 共 {len(cards)} 条记录：")
    print("=" * 90)
    print(f"{'卡密':<25} {'类型':<8} {'状态':<10} {'有效期':<22} {'设备ID':<16}")
    print("=" * 90)
    for c in cards:
        status_map = {"unused": "未使用", "used": "已激活", "expired": "已过期"}
        status = status_map.get(c["status"], c["status"])
        expires = c.get("expires_at", "") or "-"
        device = (c.get("device_id", "") or "-")[:15]
        print(f"{c['card_key']:<25} {c['type']:<8} {status:<10} {expires:<22} {device:<16}")
    print("=" * 90)

def cmd_stats():
    result = api("/admin/stats")
    if not result.get("success"):
        print(f"❌ {result.get('msg', '获取失败')}")
        return
    s = result["stats"]
    print(f"\n📊 卡密统计：")
    print(f"  总计: {s['total']}")
    print(f"  未使用: {s['unused']}")
    print(f"  已激活: {s['used']}")
    print(f"  已过期: {s['expired']}")

def cmd_delete(card_key):
    result = api("/admin/delete", {"card_key": card_key})
    print(result.get("msg", "操作完成"))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "gen" and len(sys.argv) >= 4:
        cmd_gen(sys.argv[2], int(sys.argv[3]))
    elif cmd == "list":
        cmd_list()
    elif cmd == "stats":
        cmd_stats()
    elif cmd == "delete" and len(sys.argv) >= 3:
        cmd_delete(sys.argv[2])
    else:
        print(__doc__)
