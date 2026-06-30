"""
环境快照记录器
记录: Claude Code / OpenClaw / Codex / Cursor Skills & Rules + Pip + npm
用法:
    python record_env.py           # 保存快照
    python record_env.py --diff    # 对比变化
    python record_env.py --list    # 列出所有
    python record_env.py --web     # 网页查看器
"""

import json
import os
import subprocess
import sys
import io
import site
from datetime import datetime, timezone, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ---- 配置 ----

SNAPSHOT_FILE = os.environ.get(
    "ENV_SNAPSHOT_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "env_snapshots.json")
)

PROJECT_ROOTS = [
    os.path.expanduser("~/Documents/Codex"),
    "C:/Work",
]

# (工具名, 全局目录, 项目级目录, 类型 skill/rule)
AI_AGENTS = [
    ("Claude Code", "~/.claude/skills", ".claude/skills", "skill"),
    ("OpenClaw", "~/.openclaw/skills", ".openclaw/skills", "skill"),
    ("Codex", "~/.codex/skills", ".codex/skills", "skill"),
    ("Codex Rules", "~/.codex/rules", ".codex/rules", "rule"),
    ("Cursor Rules", None, ".cursor/rules", "rule"),
]


# ---- 工具函数 ----

def _print_columns(items, indent="   ", width=100):
    if not items:
        return
    max_len = max(len(s) for s in items) + 2
    cols = max(1, width // max_len)
    for i in range(0, len(items), cols):
        row = indent + "  ".join(s.ljust(max_len) for s in items[i:i + cols])
        print(row)


# ---- AI Agent Skills/Rules 扫描 ----

def _scan_ai_dir(directory, scope, project_name, item_type="skill"):
    items = []
    if not directory or not os.path.isdir(directory):
        return items
    for name in os.listdir(directory):
        path = os.path.join(directory, name)
        if item_type == "skill":
            if os.path.isdir(path):
                skill_md = os.path.join(path, "SKILL.md")
                items.append({"name": name, "scope": scope, "project": project_name,
                              "type": "skill", "has_md": os.path.exists(skill_md)})
        elif item_type == "rule":
            if os.path.isfile(path) and (name.endswith(".rules") or name.endswith(".md")):
                items.append({"name": name, "scope": scope, "project": project_name,
                              "type": "rule", "has_md": True})
    return items


def _find_ai_items():
    all_items = []
    scanned = set()

    # 1. 全局
    for tool_name, global_dir, proj_dir, item_type in AI_AGENTS:
        if global_dir:
            gdir = os.path.expanduser(global_dir)
            real = os.path.realpath(gdir) if os.path.exists(gdir) else gdir
            if real not in scanned:
                scanned.add(real)
                for item in _scan_ai_dir(gdir, "global", None, item_type):
                    item["tool"] = tool_name
                    all_items.append(item)

    # 2. 项目级
    for root in PROJECT_ROOTS:
        if not os.path.isdir(root):
            continue
        for entry in os.listdir(root):
            proj_path = os.path.join(root, entry)
            if not os.path.isdir(proj_path):
                continue
            for tool_name, global_dir, proj_rel_dir, item_type in AI_AGENTS:
                if not proj_rel_dir:
                    continue
                ai_dir = os.path.join(proj_path, proj_rel_dir)
                real = os.path.realpath(ai_dir) if os.path.exists(ai_dir) else ai_dir
                if real not in scanned and os.path.isdir(ai_dir):
                    scanned.add(real)
                    for item in _scan_ai_dir(ai_dir, "project", entry, item_type):
                        item["tool"] = tool_name
                        all_items.append(item)

    # 3. 当前项目
    cwd = os.getcwd()
    for tool_name, global_dir, proj_rel_dir, item_type in AI_AGENTS:
        if not proj_rel_dir:
            continue
        ai_dir = os.path.join(cwd, proj_rel_dir)
        real = os.path.realpath(ai_dir) if os.path.exists(ai_dir) else ai_dir
        if real not in scanned and os.path.isdir(ai_dir):
            scanned.add(real)
            for item in _scan_ai_dir(ai_dir, "project", os.path.basename(cwd), item_type):
                item["tool"] = tool_name
                all_items.append(item)

    return all_items


def get_skills():
    return sorted(_find_ai_items(), key=lambda s: (s["scope"], s.get("tool") or "", s["name"]))


# ---- Pip 扫描 ----

def _run_pip_list(args=None):
    cmd = [sys.executable, "-m", "pip", "list", "--format=json"]
    if args:
        cmd.extend(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return json.loads(result.stdout)
    except (json.JSONDecodeError, subprocess.TimeoutExpired):
        return []


def get_pip_global():
    pkgs = _run_pip_list(["--user"])
    if not pkgs:
        pkgs = _run_pip_list()
    return [{"name": p["name"], "version": p.get("version", "?"), "scope": "global"}
            for p in sorted(pkgs, key=lambda x: x["name"])]


def get_pip_project():
    in_venv = sys.prefix != sys.base_prefix
    if not in_venv:
        return []
    all_pkgs = _run_pip_list()
    global_pkgs = _run_pip_list(["--user"])
    global_names = {p["name"] for p in (global_pkgs or [])}
    project_pkgs = [p for p in all_pkgs if p["name"] not in global_names]
    return [{"name": p["name"], "version": p.get("version", "?"), "scope": "project"}
            for p in sorted(project_pkgs, key=lambda x: x["name"])]


def get_all_pip():
    return get_pip_global() + get_pip_project()


# ---- npm 扫描 ----

def _find_npm():
    candidates = [
        os.path.expanduser("~/Programs/Dev/nodejs/npm.cmd"),
        os.path.expanduser("~/Programs/Dev/nodejs/npm"),
        os.path.expanduser("~/AppData/Roaming/npm/npm.cmd"),
        "/c/Program Files/nodejs/npm.cmd",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return "npm.cmd"


def get_npm_packages(scope, args):
    npm = _find_npm()
    try:
        result = subprocess.run(
            [npm, "list"] + args + ["--depth=0", "--json"],
            capture_output=True, text=True, timeout=10
        )
        data = json.loads(result.stdout)
        deps = data.get("dependencies", {})
        return [{"name": k, "version": v.get("version", "?"), "scope": scope}
                for k, v in deps.items()]
    except (json.JSONDecodeError, AttributeError, FileNotFoundError, subprocess.TimeoutExpired):
        return []


def get_npm_global():
    return get_npm_packages("global", ["-g"])


def get_npm_project():
    cwd = os.getcwd()
    node_modules = os.path.join(cwd, "node_modules")
    if not os.path.isdir(node_modules):
        return []
    return get_npm_packages("project", [])


def get_all_npm():
    return get_npm_global() + get_npm_project()


def _get_npm_root():
    npm = _find_npm()
    try:
        r = subprocess.run([npm, "root", "-g"], capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except Exception:
        return "~/.npm/"


# ---- 快照 ----

def take_snapshot():
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).isoformat()

    snapshot = {
        "time": now,
        "ai_agents": get_skills(),
        "pip_packages": get_all_pip(),
        "npm_packages": get_all_npm(),
    }

    history = []
    if os.path.exists(SNAPSHOT_FILE):
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)

    history.append(snapshot)
    history = history[-50:]

    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    _print_summary(snapshot)
    return snapshot


def _print_summary(s):
    print(f"\n{'='*50}")
    print(f"  环境快照 - {s['time'][:19]}")
    print(f"{'='*50}")

    ai = s.get("ai_agents", s.get("skills", []))
    # 按工具分组
    tool_groups = {}
    for item in ai:
        tool = item.get("tool", "Claude Code")
        scope = item.get("scope", "global")
        key = f"🌐 {tool} 全局" if scope == "global" else f"📁 {tool} [{item.get('project', '?')}]"
        tool_groups.setdefault(key, []).append(item["name"])

    print(f"\n🤖 AI Agents:  {len(ai)} 个")
    for group, names in sorted(tool_groups.items()):
        print(f"   {group} ({len(names)}): {', '.join(names)}")

    pip = s.get("pip_packages", [])
    pip_g = [p for p in pip if p.get("scope") == "global"]
    pip_pj = [p for p in pip if p.get("scope") == "project"]
    print(f"\n🐍 Pip:  {len(pip)} 个 ({len(pip_g)} 全局 + {len(pip_pj)} 项目)")

    npm = s.get("npm_packages", s.get("npm_global", []))
    npm_g = [p for p in npm if p.get("scope") == "global"]
    npm_pj = [p for p in npm if p.get("scope") == "project"]
    if npm:
        print(f"📦 npm:  {len(npm)} 个 ({len(npm_g)} 全局 + {len(npm_pj)} 项目)")
    else:
        print(f"📦 npm:  0 个")


# ---- 对比 ----

def show_diff():
    if not os.path.exists(SNAPSHOT_FILE):
        print("还没有快照")
        return
    with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)
    if len(history) < 2:
        print(f"只有 {len(history)} 条快照")
        return

    old = history[-2]
    new = history[-1]
    print(f"\n对比: {old['time'][:19]} → {new['time'][:19]}")

    old_ai = {s["name"] for s in old.get("ai_agents", old.get("skills", []))}
    new_ai = {s["name"] for s in new.get("ai_agents", new.get("skills", []))}
    added = new_ai - old_ai
    removed = old_ai - new_ai
    if added:
        print(f"\n➕ 新增 AI Agent 项目 ({len(added)}):")
        for s in sorted(added):
            print(f"   + {s}")
    if removed:
        print(f"\n➖ 移除 AI Agent 项目 ({len(removed)}):")
        for s in sorted(removed):
            print(f"   - {s}")
    if not added and not removed:
        print("\n   AI Agents: 无变化")

    old_pkgs = {p["name"]: p.get("version", "?") for p in old.get("pip_packages", [])}
    new_pkgs = {p["name"]: p.get("version", "?") for p in new.get("pip_packages", [])}
    added_p = {k: v for k, v in new_pkgs.items() if k not in old_pkgs}
    removed_p = {k: v for k, v in old_pkgs.items() if k not in new_pkgs}
    if added_p:
        print(f"\n➕ 新增 Pip ({len(added_p)}):")
        for name, ver in sorted(added_p.items()):
            print(f"   + {name}=={ver}")
    if removed_p:
        print(f"\n➖ 移除 Pip ({len(removed_p)}):")
        for name, ver in sorted(removed_p.items()):
            print(f"   - {name}=={ver}")
    if not added_p and not removed_p:
        print("   Pip: 无变化")

    old_npm_key = "npm_packages" if "npm_packages" in old else "npm_global"
    new_npm_key = "npm_packages" if "npm_packages" in new else "npm_global"
    old_npm = {p["name"]: p.get("version", "?") for p in old.get(old_npm_key, [])}
    new_npm = {p["name"]: p.get("version", "?") for p in new.get(new_npm_key, [])}
    added_n = {k: v for k, v in new_npm.items() if k not in old_npm}
    if added_n:
        print(f"\n➕ 新增 npm ({len(added_n)}):")
        for name, ver in sorted(added_n.items()):
            print(f"   + {name}@{ver}")


# ---- 列表 ----

def list_current():
    s = {
        "ai_agents": get_skills(),
        "pip_packages": get_all_pip(),
        "npm_packages": get_all_npm(),
    }
    print(f"\n{'='*50}")
    print(f"  当前环境")
    print(f"{'='*50}")

    ai = s["ai_agents"]
    groups = {}
    for item in ai:
        tool = item.get("tool", "?")
        scope = item.get("scope", "global")
        proj = item.get("project", "")
        if scope == "global":
            key = f"🌐 {tool} 全局"
        else:
            key = f"📁 {tool} [{proj}]"
        groups.setdefault(key, []).append(item)

    print(f"\n🤖 AI Agents ({len(ai)}):")
    for group, items in sorted(groups.items()):
        print(f"\n  {group} ({len(items)}):")
        for item in items:
            icon = "📄" if item.get("has_md") else "📁"
            print(f"     {icon} {item['name']}")

    pip = s["pip_packages"]
    pip_g = [p for p in pip if p.get("scope") == "global"]
    pip_pj = [p for p in pip if p.get("scope") == "project"]
    print(f"\n🐍 Pip ({len(pip)}):")
    if pip_g:
        print(f"\n  🌐 全局 ({len(pip_g)}):")
        for pkg in pip_g:
            print(f"     {pkg['name']}=={pkg['version']}")
    if pip_pj:
        print(f"\n  📁 项目 ({len(pip_pj)}):")
        for pkg in pip_pj:
            print(f"     {pkg['name']}=={pkg['version']}")

    npm = s["npm_packages"]
    npm_g = [p for p in npm if p.get("scope") == "global"]
    npm_pj = [p for p in npm if p.get("scope") == "project"]
    if npm:
        print(f"\n📦 npm ({len(npm)}):")
        if npm_g:
            print(f"\n  🌐 全局 ({len(npm_g)}):")
            for pkg in npm_g:
                print(f"     {pkg['name']}@{pkg['version']}")
        if npm_pj:
            print(f"\n  📁 项目 ({len(npm_pj)}):")
            for pkg in npm_pj:
                print(f"     {pkg['name']}@{pkg['version']}")


# ---- 入口 ----

if __name__ == "__main__":
    if "--path" in sys.argv:
        idx = sys.argv.index("--path")
        if idx + 1 < len(sys.argv):
            SNAPSHOT_FILE = sys.argv[idx + 1]
            sys.argv.pop(idx)
            sys.argv.pop(idx)

    if len(sys.argv) > 1 and sys.argv[1] == "--diff":
        show_diff()
    elif len(sys.argv) > 1 and sys.argv[1] == "--list":
        list_current()
    elif len(sys.argv) > 1 and sys.argv[1] == "--web":
        import threading, http.server, webbrowser
        tools_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(tools_dir)
        server = http.server.HTTPServer(("127.0.0.1", 8765), http.server.SimpleHTTPRequestHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        webbrowser.open("http://127.0.0.1:8765/env_viewer.html")
        print(f"🌐 环境查看器: http://127.0.0.1:8765/env_viewer.html")
        print(f"   按 Ctrl+C 停止服务器")
        try:
            while True:
                pass
        except KeyboardInterrupt:
            server.shutdown()
            print("已停止")
    else:
        take_snapshot()
        print(f"\n💡 提示:")
        print(f"   python record_env.py --diff    # 查看变化")
        print(f"   python record_env.py --list    # 列出当前所有")
        print(f"   python record_env.py --web     # 网页查看")
        print(f"   python record_env.py --path /your/path/snapshots.json  # 自定义路径")
