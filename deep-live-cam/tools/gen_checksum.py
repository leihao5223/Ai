#!/usr/bin/env python3
"""Generate file checksums and embed into modules/guard.py

Usage:
    python tools/gen_checksum.py

Run this after modifying any protected .py files.
"""
import hashlib, os, sys, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD_PATH = os.path.join(ROOT, "modules", "guard.py")
EXCLUDED = {"guard.py"}


def hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collect() -> dict:
    """SHA256 of all .py files under modules/ + zhaohui_launcher.py, excluding guard.py"""
    files = {}

    mod_dir = os.path.join(ROOT, "modules")
    for dirpath, _, fnames in os.walk(mod_dir):
        for fn in fnames:
            if not fn.endswith(".py"):
                continue
            if fn in EXCLUDED:
                continue
            fp = os.path.join(dirpath, fn)
            rel = os.path.relpath(fp, ROOT).replace("\\", "/")
            files[rel] = hash_file(fp)

    for fn in ["zhaohui_launcher.py"]:
        fp = os.path.join(ROOT, fn)
        if os.path.exists(fp):
            files[fn] = hash_file(fp)

    return files


def update_guard(checksums: dict):
    """Rewrite guard.py with new checksums and self-hash (two-pass)."""
    # Pass 1: write checksums + placeholder self-hash
    new_content = _build_guard_content(checksums, "__PLACEHOLDER__")
    with open(GUARD_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

    # Pass 2: compute self-hash and rewrite
    self_hash = hash_file(GUARD_PATH)
    new_content = _build_guard_content(checksums, self_hash)
    with open(GUARD_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"[OK] {len(checksums)} files + self-hash ({self_hash[:16]}...) updated")


def _build_guard_content(checksums: dict, self_hash: str) -> str:
    checksum_json = json.dumps(checksums, indent=4, sort_keys=True)

    return f'''"""Security module: file integrity, anti-debug, string protection"""
import hashlib, os, sys, base64, json

# --- checksums ----------------------------------------------------------------
# Run: python tools/gen_checksum.py  to regenerate
_CHECKSUMS = {checksum_json}
_CHECKSUMS_SELF_HASH = "{self_hash}"  # sha256 of guard.py

# --- integrity ----------------------------------------------------------------

def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except (IOError, OSError):
        return ""


def verify_integrity(root: str) -> list:
    issues = []
    for rel, expected in _CHECKSUMS.items():
        fp = os.path.join(root, rel)
        if not os.path.exists(fp):
            issues.append("[MISSING] " + rel)
        elif _file_hash(fp) != expected:
            issues.append("[MODIFIED] " + rel)
    return issues


# --- anti-debug ---------------------------------------------------------------

def _detect_debugger() -> bool:
    if sys.gettrace() is not None:
        return True
    if os.environ.get("PYCHARM_HOSTED"):
        return True
    return False


# --- string protection -------------------------------------------------------

_ENC_KEY = b"FG@2025!Sk_"
_ENC_CACHE = {{}}


def _decrypt(data: str) -> str:
    raw = base64.b64decode(data)
    return bytes(b ^ _ENC_KEY[i % len(_ENC_KEY)] for i, b in enumerate(raw)).decode()


def decrypt_str(encoded: str) -> str:
    if encoded not in _ENC_CACHE:
        _ENC_CACHE[encoded] = _decrypt(encoded)
    return _ENC_CACHE[encoded]


def encrypt_str(plain: str) -> str:
    raw = bytes(ord(c) ^ _ENC_KEY[i % len(_ENC_KEY)] for i, c in enumerate(plain))
    return base64.b64encode(raw).decode()


# --- main entry ---------------------------------------------------------------

def verify() -> tuple:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if _detect_debugger():
        return False, "debugger detected"

    issues = verify_integrity(root)
    if issues:
        return False, "integrity check failed"

    return True, ""


# --- self-test ----------------------------------------------------------------

if __name__ == "__main__":
    ok, msg = verify()
    print("OK" if ok else f"FAIL: {{msg}}")
'''


if __name__ == "__main__":
    c = collect()
    update_guard(c)
    print(f"[OK] {len(c) + 1} files protected total")
