"""一键跑完所有自测（改了代码就跑这个）

用法：
    python tests/run_all.py          # 快速自测（几秒，不含引擎/大模型）
    python tests/run_all.py --full   # 加上端到端（会真的调引擎和大模型，约 1 分钟）

退出码 0 = 全部通过
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable

FAST = [
    ("规则引擎（合法着法 / 中文记谱 / 照面将军）", [PY, "-u", "tests/test_rules.py"], "全部检查完成"),
    ("坐标中文化（材料无坐标 / 流式兜底翻译）", [PY, "-u", "tests/test_zh.py"], "全部通过"),
    ("追问链路（只答所问 / 材料瘦身 / 带上一次讲解）", [PY, "-u", "tests/test_followup.py"], "全部通过"),
    ("前端记谱 ↔ Python 对拍（504 个着法）", ["node", "tests/test_notation_js.js"], "不一致: 0"),
    ("棋盘点击与坐标反算", ["node", "tests/test_board_click.js"], "全部通过"),
    ("局面编辑流程", ["node", "tests/test_edit_mode.js"], "全部通过"),
    ("预演摆盘（摆盘时讲解不许消失）", ["node", "tests/test_preview.js"], "全部通过"),
    ("对弈模式（状态隔离 / 悔棋 / 棋谱导出对拍）", ["node", "tests/test_play.js"], "全部通过"),
    ("局面校验接口 /api/validate", [PY, "-u", "tests/test_edit_api.py"], "全部通过"),
]
SLOW = [
    ("端到端（讲解 + 复盘 + AI 报告）", [PY, "-u", "tests/test_e2e_inproc.py"], "端到端全部通过"),
]


def node_exe():
    """Windows 上 node 经常不在 PATH 里：找得到就用绝对路径"""
    p = os.environ.get("NODE_EXE")
    if p and os.path.exists(p):
        return p
    from shutil import which
    for cand in ("node", "node.exe"):
        found = which(cand)
        if found:
            return found
    # 兜底：WorkBuddy 自带的 node
    import glob
    pats = [os.path.expanduser("~/.workbuddy/binaries/node/versions/*/node.exe"),
            r"C:\Program Files\nodejs\node.exe",
            os.path.expanduser("~/AppData/Roaming/nvm/*/node.exe")]
    for pat in pats:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return "node"


def run(name, cmd, expect):
    if cmd[0] == "node":
        cmd = [node_exe()] + cmd[1:]
    print("=" * 66)
    print(f"[{name}]  {' '.join(cmd)}")
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True)
    out = p.stdout.decode("utf-8", "replace")
    err = p.stderr.decode("utf-8", "replace")
    tail = [l for l in out.strip().splitlines() if l.strip()][-6:]
    for l in tail:
        print("  " + l)
    if err.strip():
        print("  --- stderr ---")
        for l in err.strip().splitlines()[-8:]:
            print("  " + l)
    ok = p.returncode == 0 and expect in out
    if not ok:
        print(f"  >>> 失败（退出码 {p.returncode}，期望输出含「{expect}」）")
    return ok


def main():
    full = "--full" in sys.argv
    # 有的 node 测试要反过来调 Python 做跨语言对拍（棋谱格式），把解释器路径告诉它
    os.environ.setdefault("PY_EXE", sys.executable)
    todo = FAST + (SLOW if full else [])
    print(f"共 {len(todo)} 项自测{'（含端到端，较慢）' if full else '（快速，不含引擎/大模型）'}\n")
    bad = []
    for name, cmd, expect in todo:
        if not run(name, cmd, expect):
            bad.append(name)
    print("=" * 66)
    if bad:
        print(f"结果：{len(bad)} 项失败 → " + "；".join(bad))
        return 1
    print(f"结果：{len(todo)} 项全部通过 ✓")
    if not full:
        print("（端到端未跑：加 --full 参数，会用真引擎 + 真大模型跑一遍）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
