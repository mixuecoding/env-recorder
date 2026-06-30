"""
环境快照记录器
记录: Claude Code Skills + Python 库 + npm 全局包
用法:
    python record_env.py           # 保存快照
    python record_env.py --diff    # 对比上次快照，显示新增
"""

import json
import os
import subprocess
import sys
import io
import site
from datetime import datetime, timezone, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 快照文件默认存在工具目录下，可通过环境变量 ENV_SNAPSHOT_FILE 自定义
SNAPSHOT_FILE = os.environ.get(
    "ENV_SNAPSHOT_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "env_snapshots.json")
)
# Skills 全局目录（Claude Code 默认），不存在则跳过
GLOBAL_SKILLS_DIR = os.path.expanduser("~/.claude/skills")


def _print_columns(items, indent="   ", width=100):
    """将列表分列打印，每行约 width 字符"""
    if not items:
        return
    max_len = max(len(s) for s in items) + 2
    cols = max(1, width // max_len)
    for i in range(0, len(items), cols):
        row = indent + "  ".join(s.ljust(max_len) for s in items[i:i + cols])
        print(row)

# 需要扫描的项目根目录（含 .claude/skills 的目录）
# 工具会自动扫描这些目录下所有子目录的 .claude/skills
PROJECT_ROOTS = [
    os.path.expanduser("~/Documents/Codex"),
    "C:/Work",
    # 添加更多目录: "D:/Projects",
]


def _scan_skills_dir(directory, scope, project_name=None):
    """扫描一个 skills 目录，返回 skill 列表"""
    skills = []
    if os.path.isdir(directory):
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            if os.path.isdir(path):
                skill_md = os.path.join(path, "SKILL.md")
                s = {
                    "name": name,
                    "scope": scope,
                    "project": project_name,
                    "has_skill_md": os.path.exists(skill_md),
                }
                skills.append(s)
    return skills


def _find_project_skills():
    """扫描所有已知项目的 .claude/skills 目录"""
    all_skills = []
    scanned = set()

    # 扫描所有 PROJECT_ROOTS 下的子目录
    for root in PROJECT_ROOTS:
        if not os.path.isdir(root):
            continue
        for entry in os.listdir(root):
            proj_path = os.path.join(root, entry)
            if not os.path.isdir(proj_path):
                continue
            skills_path = os.path.join(proj_path, ".claude", "skills")
            real_path = os.path.realpath(skills_path)  # 规范化路径
            if os.path.isdir(skills_path) and real_path not in scanned:
                scanned.add(real_path)
                all_skills.extend(_scan_skills_dir(skills_path, "project", entry))

    # 也扫当前项目（如果不在已扫描目录中）
    cwd = os.getcwd()
    cwd_skills = os.path.join(cwd, ".claude", "skills")
    cwd_real = os.path.realpath(cwd_skills)
    if cwd_real not in scanned and os.path.isdir(cwd_skills):
        scanned.add(cwd_real)
        proj_name = os.path.basename(cwd)
        all_skills.extend(_scan_skills_dir(cwd_skills, "project", proj_name))

    return all_skills


def get_skills():
    """获取所有 Skills（全局 + 所有项目级）"""
    skills = _scan_skills_dir(GLOBAL_SKILLS_DIR, "global", None)
    skills.extend(_find_project_skills())
    return sorted(skills, key=lambda s: (s["scope"], s.get("project") or "", s["name"]))


def _run_pip_list(args=None):
    """运行 pip list 并返回解析结果"""
    cmd = [sys.executable, "-m", "pip", "list", "--format=json"]
    if args:
        cmd.extend(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return json.loads(result.stdout)
    except (json.JSONDecodeError, subprocess.TimeoutExpired):
        return []


def get_pip_global():
    """获取全局 pip 包"""
    pkgs = _run_pip_list(["--user"])
    if not pkgs:
        pkgs = _run_pip_list()
    return [{"name": p["name"], "version": p.get("version", "?"), "scope": "global"}
            for p in sorted(pkgs, key=lambda x: x["name"])]


def get_pip_project():
    """获取当前项目虚拟环境的 pip 包"""
    # 检测是否在虚拟环境中
    in_venv = sys.prefix != sys.base_prefix
    if not in_venv:
        return []

    # 虚拟环境中的所有包（排除标准库）
    all_pkgs = _run_pip_list()
    global_pkgs = _run_pip_list(["--user"])
    global_names = {p["name"] for p in (global_pkgs or [])}

    # 项目级 = venv 全部 - 已在全局的
    project_pkgs = [p for p in all_pkgs if p["name"] not in global_names]
    return [{"name": p["name"], "version": p.get("version", "?"), "scope": "project"}
            for p in sorted(project_pkgs, key=lambda x: x["name"])]


def get_all_pip():
    """获取所有 pip 包（全局 + 项目）"""
    pkgs = get_pip_global()
    pkgs.extend(get_pip_project())
    return pkgs


def _find_npm():
    """找到 npm 可执行文件路径"""
    # .cmd 优先（Windows），然后直接名
    candidates = [
        os.path.expanduser("~/Programs/Dev/nodejs/npm.cmd"),
        os.path.expanduser("~/Programs/Dev/nodejs/npm"),
        os.path.expanduser("~/AppData/Roaming/npm/npm.cmd"),
        "/c/Program Files/nodejs/npm.cmd",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return "npm.cmd"  # 最后尝试系统 PATH


def get_npm_packages(scope, args):
    """获取 npm 包"""
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
    """获取 npm 全局安装的包"""
    return get_npm_packages("global", ["-g"])


def get_npm_project():
    """获取当前项目 node_modules 的包"""
    cwd = os.getcwd()
    node_modules = os.path.join(cwd, "node_modules")
    if not os.path.isdir(node_modules):
        return []
    return get_npm_packages("project", [])


def get_all_npm():
    """获取所有 npm 包（全局 + 项目）"""
    return get_npm_global() + get_npm_project()


def _get_npm_root():
    """获取 npm 全局安装根目录"""
    npm = _find_npm()
    try:
        r = subprocess.run([npm, "root", "-g"], capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except Exception:
        return "~/.npm/"


def take_snapshot():
    """拍摄当前环境快照"""
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).isoformat()

    snapshot = {
        "time": now,
        "skills": get_skills(),
        "pip_packages": get_all_pip(),
        "npm_global": get_all_npm(),
    }

    # 加载历史记录
    history = []
    if os.path.exists(SNAPSHOT_FILE):
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)

    history.append(snapshot)
    # 只保留最近 50 条
    history = history[-50:]

    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    _print_summary(snapshot)
    return snapshot


def _print_summary(s):
    print(f"\n{'='*50}")
    print(f"  环境快照已保存 - {s['time'][:19]}")
    print(f"{'='*50}")

    # Skills 按来源分组列出
    global_skills = [sk for sk in s["skills"] if sk.get("scope") == "global"]
    proj_groups = {}
    for sk in s["skills"]:
        if sk.get("scope") == "project":
            p = sk.get("project", "unknown")
            proj_groups.setdefault(p, []).append(sk["name"])

    print(f"\n📦 Skills:  {len(s['skills'])} 个")
    print(f"   🌐 全局 ({len(global_skills)}) 路径: ~/.claude/skills/")
    print(f"      {', '.join(sk['name'] for sk in global_skills)}")
    for proj, names in sorted(proj_groups.items()):
        print(f"   📁 {proj} ({len(names)}) 路径: <项目>/.claude/skills/")
        print(f"      {', '.join(names)}")

    # Pip — 分全局和项目
    pip_global = [p for p in s["pip_packages"] if p.get("scope") == "global"]
    pip_project = [p for p in s["pip_packages"] if p.get("scope") == "project"]
    print(f"\n🐍 Pip 包:  {len(s['pip_packages'])} 个")
    if pip_global:
        names = [p["name"] for p in pip_global]
        print(f"   🌐 全局 ({len(pip_global)}) 路径: {site.getusersitepackages()}")
        _print_columns(names, indent="      ")
    if pip_project:
        names = [p["name"] for p in pip_project]
        print(f"   📁 项目 venv ({len(pip_project)}) 路径: {sys.prefix}")

    # npm — 分全局和项目
    npm_global = [p for p in s["npm_global"] if p.get("scope") == "global"]
    npm_project = [p for p in s["npm_global"] if p.get("scope") == "project"]
    if npm_global or npm_project:
        print(f"\n📦 npm:  {len(s['npm_global'])} 个")
        if npm_global:
            npm_root = _get_npm_root()
            names = [p["name"] for p in npm_global]
            print(f"   🌐 全局 ({len(npm_global)}) 路径: {npm_root}")
            print(f"      {', '.join(names)}")
        if npm_project:
            names = [p["name"] for p in npm_project]
            print(f"   📁 项目 ({len(npm_project)}) 路径: {os.getcwd()}/node_modules")
            print(f"      {', '.join(names)}")
    else:
        print(f"\n📦 npm: 0 个")


def show_diff():
    """对比最近两次快照的差异"""
    if not os.path.exists(SNAPSHOT_FILE):
        print("还没有快照，先运行 python record_env.py")
        return

    with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)

    if len(history) < 2:
        print(f"只有 {len(history)} 条快照，需要至少 2 条才能对比")
        return

    old = history[-2]
    new = history[-1]

    print(f"\n对比: {old['time'][:19]} → {new['time'][:19]}")

    # Skills 变化
    old_skills = {s["name"] for s in old["skills"]}
    new_skills = {s["name"] for s in new["skills"]}
    added_skills = new_skills - old_skills
    removed_skills = old_skills - new_skills

    if added_skills:
        print(f"\n➕ 新增 Skills ({len(added_skills)}):")
        for s in sorted(added_skills):
            print(f"   + {s}")
    if removed_skills:
        print(f"\n➖ 移除 Skills ({len(removed_skills)}):")
        for s in sorted(removed_skills):
            print(f"   - {s}")
    if not added_skills and not removed_skills:
        print("\n   Skills: 无变化")

    # Pip 包变化
    old_pkgs = {p["name"]: p.get("version", "?") for p in old["pip_packages"]}
    new_pkgs = {p["name"]: p.get("version", "?") for p in new["pip_packages"]}
    added_pkgs = {k: v for k, v in new_pkgs.items() if k not in old_pkgs}
    removed_pkgs = {k: v for k, v in old_pkgs.items() if k not in new_pkgs}
    upgraded_pkgs = {}
    for k in set(old_pkgs) & set(new_pkgs):
        if old_pkgs[k] != new_pkgs[k]:
            upgraded_pkgs[k] = (old_pkgs[k], new_pkgs[k])

    if added_pkgs:
        print(f"\n➕ 新增 Pip 包 ({len(added_pkgs)}):")
        for name, ver in sorted(added_pkgs.items()):
            print(f"   + {name}=={ver}")
    if removed_pkgs:
        print(f"\n➖ 移除 Pip 包 ({len(removed_pkgs)}):")
        for name, ver in sorted(removed_pkgs.items()):
            print(f"   - {name}=={ver}")
    if upgraded_pkgs:
        print(f"\n🔄 版本变化 ({len(upgraded_pkgs)}):")
        for name, (old_v, new_v) in sorted(upgraded_pkgs.items()):
            print(f"   ~ {name}: {old_v} → {new_v}")
    if not added_pkgs and not removed_pkgs and not upgraded_pkgs:
        print("   Pip 包: 无变化")

    # npm 全局变化
    old_npm = {p["name"]: p.get("version", "?") for p in old["npm_global"]}
    new_npm = {p["name"]: p.get("version", "?") for p in new["npm_global"]}
    added_npm = {k: v for k, v in new_npm.items() if k not in old_npm}

    if added_npm:
        print(f"\n➕ 新增 npm 全局包 ({len(added_npm)}):")
        for name, ver in sorted(added_npm.items()):
            print(f"   + {name}@{ver}")
    elif not added_npm:
        pass  # npm 变化不单独提示


def list_current():
    """列出当前环境的所有内容"""
    s = {
        "skills": get_skills(),
        "pip_packages": get_all_pip(),
        "npm_global": get_all_npm(),
    }
    print(f"\n{'='*50}")
    print(f"  当前环境")
    print(f"{'='*50}")

    # Skills — 按来源分组显示
    print(f"\n📦 Skills ({len(s['skills'])}):")
    # 分组: global → 各项目
    groups = {}
    for sk in s["skills"]:
        key = "🌐 全局" if sk["scope"] == "global" else f"📁 {sk.get('project', 'unknown')}"
        groups.setdefault(key, []).append(sk)

    for group_name, items in groups.items():
        print(f"\n  {group_name} ({len(items)}):")
        for sk in items:
            md_flag = "📄" if sk["has_skill_md"] else "📁"
            print(f"     {md_flag} {sk['name']}")

    # Pip — 分全局和项目
    pip_global = [p for p in s["pip_packages"] if p.get("scope") == "global"]
    pip_project = [p for p in s["pip_packages"] if p.get("scope") == "project"]
    print(f"\n🐍 Pip 包 ({len(s['pip_packages'])}):")
    if pip_global:
        print(f"\n  🌐 全局 ({len(pip_global)}):")
        for pkg in pip_global:
            print(f"     {pkg['name']}=={pkg['version']}")
    if pip_project:
        print(f"\n  📁 项目 venv ({len(pip_project)}):")
        for pkg in pip_project:
            print(f"     {pkg['name']}=={pkg['version']}")

    # npm — 分全局和项目
    npm_global = [p for p in s["npm_global"] if p.get("scope") == "global"]
    npm_project = [p for p in s["npm_global"] if p.get("scope") == "project"]
    if npm_global or npm_project:
        print(f"\n📦 npm ({len(s['npm_global'])}):")
        if npm_global:
            print(f"\n  🌐 全局 ({len(npm_global)}):")
            for pkg in npm_global:
                print(f"     {pkg['name']}@{pkg['version']}")
        if npm_project:
            print(f"\n  📁 项目 ({len(npm_project)}):")
            for pkg in npm_project:
                print(f"     {pkg['name']}@{pkg['version']}")


if __name__ == "__main__":
    # 支持 --path 自定义快照文件路径
    if "--path" in sys.argv:
        idx = sys.argv.index("--path")
        if idx + 1 < len(sys.argv):
            SNAPSHOT_FILE = sys.argv[idx + 1]
            sys.argv.pop(idx)  # 移除 --path
            sys.argv.pop(idx)  # 移除值

    if len(sys.argv) > 1 and sys.argv[1] == "--diff":
        show_diff()
    elif len(sys.argv) > 1 and sys.argv[1] == "--list":
        list_current()
    elif len(sys.argv) > 1 and sys.argv[1] == "--web":
        # 启动本地 HTTP 服务器 + 打开网页
        import threading, http.server, webbrowser
        tools_dir = os.path.dirname(os.path.abspath(__file__))
        # HTTP 服务根目录 = tools/，快照文件和 viewer 都在这个目录下
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
