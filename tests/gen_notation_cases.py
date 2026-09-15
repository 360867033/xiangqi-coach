"""生成一批"局面 + 合法着法 + 正确中文记谱"作为基准数据，交给 JS 对拍"""
import json, sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from xq import rules as R

random.seed(20260914)

def sample(fen, n=40):
    b, red = R.parse_fen(fen)
    lms = R.legal_moves(b, red)
    random.shuffle(lms)
    return b, [{"uci": R.move_uid(m), "chinese": R.move_to_chinese(b, m)}
               for m in lms[:n]]

cases = []
seen = {R.START_FEN}
cases.append({"fen": R.START_FEN, "moves": sample(R.START_FEN)[1]})

# 随机走若干步，收集各种局面（含残局、有重复子力的局面）
for trial in range(14):
    b, red = R.parse_fen(R.START_FEN)
    plies = random.randint(4, 30)
    for _ in range(plies):
        lms = R.legal_moves(b, red)
        if not lms:
            break
        b = R.apply_move(b, random.choice(lms)); red = not red
    fen = R.to_fen(b, red)
    ok, _p = R.validate(b, red)
    if fen in seen or not ok:
        continue
    seen.add(fen)
    _, mv = sample(fen)
    if mv:
        cases.append({"fen": fen, "moves": mv})

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_notation_cases.json")
json.dump(cases, open(out, "w", encoding="utf-8"), ensure_ascii=False)
print(f"生成 {len(cases)} 个局面，共 {sum(len(c['moves']) for c in cases)} 个着法")
