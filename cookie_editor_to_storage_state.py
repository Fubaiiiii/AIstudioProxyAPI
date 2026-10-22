#!/usr/bin/env python3
"""
把用户从自己电脑 Cookie-Editor 扩展导出的两份 JSON
（aistudio.google.com 和 google.com 各一份）
转成 AIStudioProxyAPI（Camoufox）无头模式要的 storage_state 认证文件。

用法:
    python cookie_editor_to_storage_state.py aistudio.json google.json

输出: auth_profiles/saved/cookie_import_<timestamp>.json
之后由主 agent 把它拷到 auth_profiles/active/（active 下只留一个 .json），
再重启服务并验证会话有效。

Cookie-Editor 导出格式: 数组，每个 cookie 含
  name, value, domain, path, expirationDate, httpOnly, secure,
  sameSite(no_restriction|lax|strict|unspecified), hostOnly, session
目标格式: Playwright storage_state: {"cookies": [...], "origins": []}
"""

import json
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
SAVED = BASE / "auth_profiles" / "saved"

SAMESITE_MAP = {
    "no_restriction": "None",
    "lax": "Lax",
    "strict": "Strict",
    # unspecified: Playwright 加载时缺省按 Lax 处理，这里显式填 Lax
    "unspecified": "Lax",
    "": "Lax",
}


def load_cookie_editor(path: Path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):  # 兼容有的导出是 {"cookies": [...]}
        raw = raw.get("cookies", [])
    if not isinstance(raw, list):
        raise ValueError(f"{path}: 不是 Cookie-Editor 的数组格式")
    return raw


def convert_one(c: dict) -> dict:
    out = {
        "name": c.get("name", ""),
        "value": c.get("value", ""),
        "domain": c.get("domain", ""),
        "path": c.get("path", "/"),
        "httpOnly": bool(c.get("httpOnly", False)),
        "secure": bool(c.get("secure", False)),
        "sameSite": SAMESITE_MAP.get(str(c.get("sameSite", "")).lower(), "Lax"),
    }
    if c.get("session") or not c.get("expirationDate"):
        out["expires"] = -1
    else:
        try:
            out["expires"] = float(c["expirationDate"])
        except (TypeError, ValueError):
            out["expires"] = -1
    return out


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    files = [Path(a) for a in sys.argv[1:]]
    for f in files:
        if not f.is_file():
            print(f"找不到文件: {f}")
            sys.exit(2)

    merged: dict[tuple, dict] = {}
    for f in files:
        for c in load_cookie_editor(f):
            key = (c.get("name"), c.get("domain"), c.get("path"))
            # 后一份文件（google.com）的同键 cookie 覆盖前一份——同一浏览器会话下它们本就一致
            merged[key] = convert_one(c)

    cookies = [v for v in merged.values() if v["name"]]
    state = {"cookies": cookies, "origins": []}

    # 健全性检查：Google 会话关键 cookie 是否在场
    domains = {}
    for v in cookies:
        domains.setdefault(v["domain"], []).append(v["name"])
    key_cookies = {"SID", "HSID", "SSID", "APISID", "SAPISID", "__Secure-1PSID"}
    present = {n for names in domains.values() for n in names} & key_cookies
    missing = key_cookies - present

    SAVED.mkdir(parents=True, exist_ok=True)
    out_path = SAVED / f"cookie_import_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    # 凭证类文件只给本机可读
    out_path.chmod(0o600)

    print(f"已写入: {out_path}")
    print(f"cookie 总数: {len(cookies)}")
    for d in sorted(domains):
        print(f"  {d}: {len(domains[d])} 个")
    if missing:
        print(f"注意: 以下 Google 会话关键 cookie 缺失 {sorted(missing)} —— 会话可能不完整，"
              f"导入后若无头模式仍跳登录页，请让用户重新确认导出时登录的是目标账号。")
    else:
        print("关键 Google 会话 cookie 齐全，看起来像一份有效会话。")
    print("\n下一步（主 agent 执行）:")
    print("  1. cp 该文件到 auth_profiles/active/，并确保 active 下只有这一个 .json")
    print("  2. 重启 AIStudioProxyAPI 无头模式，确认不再跳 Google 登录页")
    print("  3. 跑 Argon 验证请求（Pi 侧抓样本核对）")


if __name__ == "__main__":
    main()
