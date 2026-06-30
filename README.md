# env-recorder

> 一行命令记录开发环境的每一次变化。Skills、Pip、npm — 全局 vs 项目，一目了然。

## 快速开始

```bash
git clone https://github.com/mixuecoding/env-recorder.git
cd env-recorder
python record_env.py
```

## 用法

```bash
python record_env.py              # 拍快照
python record_env.py --diff       # 对比上次变化
python record_env.py --list       # 列出当前所有
python record_env.py --web        # 网页查看器（搜索/筛选/对比）
python record_env.py --path ./my-snapshots.json  # 自定义快照路径
```

## 功能

| 维度 | 全局 | 项目级 |
|------|------|--------|
| 📦 Skills | `~/.claude/skills/` | `<项目>/.claude/skills/` |
| 🐍 Pip | `site-packages/` | 虚拟环境 |
| 📦 npm | `npm root -g` | `node_modules/` |

## 示例输出

```
📦 Skills:  20 个
   🌐 全局 (2) 路径: ~/.claude/skills/
      agent-reach, anysearch
   📁 AiTools (17) 路径: <项目>/.claude/skills/
      animejs, gsap, hyperframes...

🐍 Pip 包:  89 个
   🌐 全局 (89) 路径: ...Python312/site-packages

📦 npm:  10 个
   🌐 全局 (10) 路径: .../npm/node_modules
      @anthropic-ai/claude-code, @openai/codex, vercel...
```

## 网页查看器

`python record_env.py --web` 打开本地网页：

- 🔍 搜索包名
- 🌐/📁 按范围筛选
- 📊 两次快照变化对比
- 📅 历史快照切换

## 自定义快照路径

```bash
# 环境变量
export ENV_SNAPSHOT_FILE=/path/to/snapshots.json

# 命令行
python record_env.py --path /path/to/snapshots.json
```

默认保存在脚本同目录的 `env_snapshots.json`。

## 扫描其他项目目录

编辑 `PROJECT_ROOTS` 列表添加你的工作目录：

```python
PROJECT_ROOTS = [
    "C:/Work",
    "~/Documents/Codex",
    "D:/Projects",  # 添加你的目录
]
```

## 依赖

- Python 3.10+
- npm（可选，用于记录 npm 全局包）

## License

MIT

---

<div align="center">
  <img src="mixuecodingQR.jpg" width="140" alt="蜜学编程">
  <p>👆 扫码关注「蜜学编程」</p>
  <p>氛围编程实战派。像喝蜜雪一样写代码。</p>
</div>
