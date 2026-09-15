# -*- coding: utf-8 -*-
"""
坐标中文化测试（xq/zh.py + 材料文本）

起因：大模型讲棋时会写 "红车在 a0、双炮在 b2、i2" 这种字母+数字坐标，
棋友看不懂。这里验证两层防线：
  1. 材料里不许出现坐标（模型没得抄）
  2. 输出兜底：万一它还是写了，也要翻成中文
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xq import rules as R          # noqa: E402
from xq import zh as ZH            # noqa: E402
from xq import coach as C          # noqa: E402

fails = 0


def check(cond, msg):
    global fails
    print(("  OK  " if cond else "  !!  ") + msg)
    if not cond:
        fails += 1


board, red = R.parse_fen(R.START_FEN)
COORD = re.compile(r"(?<![A-Za-z0-9])[a-iA-I]\d")


def run(text, fen=R.START_FEN):
    f = ZH.CoordFilter(fen)
    return f.feed(text) + f.flush()


print("【单点】有子的格子 -> 阵营 + 路数 + 棋子名")
check(run("红车在 a0。") == "红车在 红方九路车。", "a0（红方底线左车）-> 红方九路车")
check(run("车在 i0") == "车在 红方一路车", "i0 -> 红方一路车（一路=红方右手边）")
check(run("a9 是黑车") == "黑方1路车 是黑车", "a9 -> 黑方1路车（1路=黑方右手边）")
check(run("c9 的象") == "黑方3路象 的象", "c9 -> 黑方3路象")
check(run("h2 是炮") == "红方二路炮 是炮", "h2 -> 红方二路炮")

print("")
print("【单点】空格只报位置，编不出棋子")
out = run("e4 是空的")
check("红方五路" in out and "黑方5路" in out, "e4 -> 红方五路（黑方5路）：" + out)
check("车" not in out and "马" not in out, "空格不得凭空补一个棋子名")

print("")
print("【两点】能对上合法着法 -> 直接给中文记谱")
check(run("从 a0 到 a2") == "从 车九进二", "a0→a2 -> 车九进二：" + run("从 a0 到 a2"))
check(run("a9-a7") == "车1进2", "a9→a7 -> 车1进2（黑方进=rank 变小）：" + run("a9-a7"))
check(run("炮 b2->e2") == "炮 炮八平五", "b2->e2 -> 炮八平五（红方八路炮占 b2）：" + run("炮 b2->e2"))
check(run("炮 d2->e2") == "炮 红方六路（黑方4路）->红方五路（黑方5路）",
      "d2 是空的（起点无子）-> 只报位置不硬凑记谱：" + run("炮 d2->e2"))

print("")
print("【两点】不是合法着法 -> 分别翻译，绝不硬编")
out = run("a0-b0（自吃）")
check("红方九路车" in out and "红方八路马" in out,
      "a0-b0 起点是红车、终点是红马（非法）-> 各自翻译：" + out)
check("平" not in out, "非法着法不得生成中文记谱（会误导）")

print("")
print("【误伤】FEN 与英文不能被当成坐标")
fen_txt = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
check(run(fen_txt) == fen_txt, "整串 FEN 原样通过（1c5c1 里的片段不该匹配）")
for s in ["x1", "h10", "A1B", "3c5", "abc"]:
    check(run(s) == s, '"%s" 不该被改写' % s)

print("")
print("【防重复】前后文已交代过的别说两遍")
check(run("红方的 a0 车") == "红方的 九路 车", "已有阵营名时只报路数：" + run("红方的 a0 车"))
check(run("a0 车") == "红方九路 车", "只跟棋子名时不重复棋子名：" + run("a0 车"))

print("")
print("【流式】逐字喂也不能漏字、不能把半截坐标放出去")
long_txt = "红车 a0，黑车 a9，炮 h2 平 e2，还有 i0 与 e4 的空位。"
whole = run(long_txt)
f = ZH.CoordFilter(R.START_FEN)
got = ""
leaks = []
for ch in long_txt:                       # 极端情况：一个字一个字地来
    piece = f.feed(ch)
    got += piece
    if COORD.search(piece):
        leaks.append(piece)
got += f.flush()
check(got == whole, "逐字拼接结果与整块处理完全一致")
check(not leaks, "任何一块输出里都不含未翻译的坐标")
check("a0" not in whole and "a9" not in whole and "i0" not in whole, "最终文本无坐标残留")
f2 = ZH.CoordFilter(R.START_FEN)
parts = [f2.feed("落子在 a"), f2.feed("0 位置"), f2.flush()]
check("".join(parts) == "落子在 红方九路车 位置",
      "半截坐标跨块能接回：" + "".join(parts))

print("")
print("【无局面】不知道盘面时，只报位置不编棋子")
f = ZH.CoordFilter()
out = f.feed("a0 和 h2") + f.flush()
check("红方九路" in out and "红方二路" in out, "退化为纯位置说法：" + out)
check(not COORD.search(out), "仍然不含字母坐标")

print("")
print("【材料】喂给大模型的文本里一个坐标都不许有")
facts = {
    "fen": R.START_FEN,
    "board_text": R.board_text(board),
    "positions": R.piece_positions(board),
    "side_to_move": "红方",
    "material": R.material_summary(board),
    "material_diff": 0,
    "depth": 16,
    "legal_count": 44,
    "candidates": [{
        "rank": 1, "uci": "h2e2", "chinese": "炮二平五", "score_cp": 12,
        "score_red": 12, "wdl": [40, 55, 5], "depth": 16, "is_mate": False,
        "capture": False, "pv_chinese": ["炮二平五", "马8进7"],
        "pv_uci": ["h2e2", "h9g7"],          # 给前端"预演摆盘"用，绝不能进材料
        "end_material_diff": 0,
    }],
    "best": {"rank": 1, "uci": "h2e2", "chinese": "炮二平五", "score_cp": 12,
             "score_red": 12, "pv_chinese": ["炮二平五", "马8进7"],
             "pv_uci": ["h2e2", "h9g7"]},
    "played": {"uci": "b2e2", "chinese": "炮八平五", "score_cp": 5,
               "score_red": 5, "is_best": False, "loss_cp": 7,
               "label": "不精确", "pv_chinese": ["马8进7"],
               "pv_uci": ["b2e2", "h9g7"]},
    "cloud": {"status": "ok", "moves": [
        {"move": "h2e2", "chinese": "炮二平五", "rank_label": "最佳着法",
         "score": 8, "winrate": 52.1, "note": "! (44-12)"}]},
}
txt = C.facts_to_text(facts)
hit = COORD.findall(txt)
check(not hit, "候选表/最佳着法/学生着法/云库 全无坐标（命中：" + str(hit[:5]) + "）")
check("炮二平五" in txt, "云库着法已翻成中文")
check("九路车（第1条横线）" in txt, "材料里带了子力位置的中文说法（可直接照抄）")
check("h2e2" not in txt and "h9g7" not in txt and "b2e2" not in txt,
      "pv_uci（给前端预演摆盘用的着法序列）不会被写进材料")
bt = R.board_text(board)
check("a b c d e f g h i" not in bt, "棋盘文本不再有 a..i 列标")
prompt = C.build_explain_prompt(facts)
check(not COORD.search(prompt), "完整提示词（含材料）无坐标")

print("")
print("【盘面位置清单】路数与横线要对得上")
pos = R.piece_positions(board)
print("     " + pos.replace("\n", "\n     "))
check("一路车（第1条横线）、九路车（第1条横线）" in pos, "红车在一路/九路底线（按路数顺序）")
check("1路卒（第4条横线）" in pos, "黑卒在 1 路，从黑方数第 4 条横线（没过河）")
check("帅" in pos and "将" in pos, "帅与将都在清单里")

print("")
if fails:
    print("结果：%d 项失败" % fails)
    sys.exit(1)
print("结果：全部通过 ✓")
