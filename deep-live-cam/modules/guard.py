"""Security module: file integrity, anti-debug, string protection"""
import hashlib, os, sys, base64, json

# --- checksums ----------------------------------------------------------------
# Run: python tools/gen_checksum.py  to regenerate
_CHECKSUMS = {
    "modules/__init__.py": "ea010c3062b0f3ed68dd31f14eb87aa080aa09ea7badccfd618a622ee3597828",
    "modules/auth.py": "f1296ec0399b15ad0ff8f88114bace4b9f3506ecc4425c66dfc308be0cfe3e5d",
    "modules/capturer.py": "bc64d3cd993a34c34bedb379eca469f4afab52752cc36e52d746134e36c93bb0",
    "modules/cluster_analysis.py": "0a461af05851409eb9bd4641066ecfa7e41754680050c5f789cb12a970904b0a",
    "modules/core.py": "9ccd2b0a340ac497fb22d6d001871b20c2d94ccd144cbe36adef65e126230003",
    "modules/custom_types.py": "d7a1ce26fec4011957ef145eb842215f8270ff12eb231c175ed677bbcd814a6f",
    "modules/face_analyser.py": "bf5dae44f8d325246c7789b3e7cc4f8633a35ec951bf9ca12f040e81da993b1a",
    "modules/gettext.py": "eaa23229067b0b02e6687cc02d8cda5a45835cd0b913bbceb8f464d06e05294b",
    "modules/globals.py": "11b1088bb58913ee4ac8e5296ce9b7ec7edf8d405e5272546117d4e93fcb778d",
    "modules/gpu_processing.py": "3a45068dd46d258e4ceadad57ff03b2459ef53e97d74e6ef1d26ff0efb67f4c1",
    "modules/metadata.py": "ae500c178fbb44f38f8217c8896e29c28c9fdc24f537c5867aaaa055967e0da3",
    "modules/onnx_optimize.py": "b723211f8b4e11aa0f5e819ba47677f54bfa38fdc4a87d54bb1f01966adfe9d8",
    "modules/paths.py": "0e9ae9236413fca715ca10166246397a24385a6df870ce2700cc5155746e905d",
    "modules/platform_info.py": "f96e2b715f658e152747de99e653858e51baadec2c6384eb87adb2a04512fbc2",
    "modules/predicter.py": "f00e8a5c328e87c71d45cd371b7d1aa5d07a0025bbb027a58a6c864974cd7f22",
    "modules/processors/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "modules/processors/frame/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "modules/processors/frame/_onnx_enhancer.py": "f578feafbad210f63d53a5de4199a063357137ffc2ad137406256f81ebbe0f46",
    "modules/processors/frame/core.py": "d9e4406cbb8e65367607a0c7eb33ef180d984c9a56adaf4cb2ac450eaa149854",
    "modules/processors/frame/face_enhancer.py": "953fa7bab9e7990fd1c28fee9054f1c553c275f303e85da9c9785e11c8e44bb0",
    "modules/processors/frame/face_enhancer_gpen256.py": "78e8fb9815d28d774af5bf6b8019afa608eb04c4adba68bc90d0723803e5c4e2",
    "modules/processors/frame/face_enhancer_gpen512.py": "937fffcb6d29a1dbec3a3afcaea1ed3c6adec780b0f819f8cdd626405ed9a9d1",
    "modules/processors/frame/face_masking.py": "f36ed75f6503a7f8f735e268e066bbe077b209bd7645c877c1389dbdcbe9f15d",
    "modules/processors/frame/face_swapper.py": "b60d2cd0738a5c0833af7032d38bf9bf1a113fc4738812ab2fda07c27de085bf",
    "modules/run.py": "15a1bf1c887c14344c52d3daec21141d29961f401a0abb1742eb52b19a3b73fe",
    "modules/tkinter_fix.py": "9bea4ebf0f7ac6d75c1d3c91f4abbfb666f4b4644653c71505dae062dbf55baa",
    "modules/typing.py": "02b6d4d90b3f917338fd4d7a29adae737c91f71d686cfeb4c52aded51d8f7525",
    "modules/ui.py": "e740d3e5d57a43421265395a0ae36945c279976a70695c5bba004d5ef8a8a685",
    "modules/ui_tooltip.py": "61d515f60023f78480a27b4652f1e5eb88bb1d45d402c30ea6ccaef092b42ee8",
    "modules/utilities.py": "d0bd14936957de7c347d5d1b638558bb339f6af066190668fe2a40b1b684b0e8",
    "modules/video_capture.py": "03b5f69c11c8f1f739f87343769d7feadfe3e153d3beea194849393269a2a473",
    "zhaohui_launcher.py": "c47d9ec188ddc4ea25f3c22ab966dbf6fe4388db5f658dd7ea34ddcc082b02b1"
}
_CHECKSUMS_SELF_HASH = "1415790f917692489cc9fc80571739bff456262731b317e34e77fa0ef0e63df6"  # sha256 of guard.py

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
_ENC_CACHE = {}


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
    print("OK" if ok else f"FAIL: {msg}")
