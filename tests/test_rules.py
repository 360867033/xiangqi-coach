import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from xq import rules as R

b, red = R.parse_fen(R.START_FEN)
print("FEN 往返:", R.to_fen(b, red))
assert R.to_fen(b, red) == R.START_FEN, "FEN 往返不一致！"

lm = R.legal_moves(b, True)
print("开局红方合法着法数:", len(lm), "(应为 44)")
assert len(lm) == 44, f"着法数不对: {len(lm)}"

print("\n=== 开局着法记谱抽查 ===")
want = {'h2e2': '炮二平五', 'b2e2': '炮八平五', 'c3c4': '兵七进一', 'g3g4': '兵三进一',
        'a0a1': '车九进一', 'i0i1': '车一进一', 'h0g2': '马二进三', 'b0c2': '马八进七',
        'c0e2': '相七进五', 'g0e2': '相三进五', 'd0e1': '仕六进五'}
for u, exp in want.items():
    mv = R.uid_to_move(u)
    assert mv in lm, f"{u} 不在合法着法里"
    got = R.move_to_chinese(b, mv)
    flag = "OK " if got == exp else "!! "
    print(f"  {flag}{u} -> {got}   (期望 {exp})")

# 黑方
b2 = R.apply_move(b, R.uid_to_move('h2e2'))
bl = R.legal_moves(b2, False)
print("\n黑方合法着法数:", len(bl))
want_b = {'b9c7': '马2进3', 'h9g7': '马8进7', 'g6g5': '卒7进1', 'c6c5': '卒3进1',
          'a9a8': '车1进1', 'i9h9': '车9平8'}
for u, exp in want_b.items():
    mv = R.uid_to_move(u)
    got = R.move_to_chinese(b2, mv)
    ok = "OK " if got == exp else "!! "
    print(f"  {ok}{u} -> {got}   (期望 {exp})")

# 前/后 与 平 的测试：造一个双车同线的局面
test_fen = R.to_fen(b2, False)
print("\n=== 将军 / 照面 检测 ===")
# 简单：红方车吃黑将的照面测试
b3, _ = R.parse_fen("4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1")
print("  双帅照面(应 True):", R.kings_facing(b3))
b4, _ = R.parse_fen("4k4/9/9/9/9/9/9/9/4R4/4K4 w - - 0 1")
print("  红车照面将军(应 True):", R.in_check(b4, False))

print("\n=== 中文记谱：前/后 车测试 ===")
b5, _ = R.parse_fen("3k5/9/9/9/9/9/9/9/9/R3K3R w - - 0 1")
for mv in R.legal_moves(b5, True):
    ch = R.move_to_chinese(b5, mv)
    if '车' in ch:
        print("  ", R.move_uid(mv), "->", ch)

print("\n=== 子力清单 ===")
print(" ", R.material_summary(b))
print("\n=== 棋盘文本 ===")
print(R.board_text(b))
print("\n全部检查完成")
