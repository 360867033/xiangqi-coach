import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from xq import rules as R, coach, review as RV

# 用中文记谱输入一段真实、合法的开局（中炮对屏风马）
TEXT = "炮二平五 马8进7 马二进三 车9平8 车一平二 卒7进1 兵七进一 马2进3 车二进六 炮8平9 车二平三 炮9退1"
b, red = R.parse_fen(R.START_FEN)
tokens = RV.parse_move_input(TEXT)
ucis, chinese, unknown = RV.resolve_moves(b, red, tokens)
print("识别着法 :", ' '.join(chinese))
print("未识别   :", unknown or "无")

for u in ucis:
    b = R.apply_move(b, R.uid_to_move(u)); red = not red
FEN = R.to_fen(b, red)
print("\n最终 FEN :", FEN)
ok, probs = R.validate(b, red)
print("局面校验 :", "合法" if ok else probs)
print("走子方   :", "红方" if red else "黑方")

PLAYED = "a3a4"      # 兵九进一（偏慢的闲着）
print("测试着法 :", R.move_to_chinese(b, R.uid_to_move(PLAYED)),
      "(合法)" if R.uid_to_move(PLAYED) in R.legal_moves(b, red) else "(不合法!)")

t0 = time.time()
facts = coach.build_facts(FEN, played_move=PLAYED, depth=18, multipv=4, cfg=coach.load_cfg())
print(f"\n事实包组装耗时 {time.time()-t0:.1f}s")
if "error" in facts:
    print("ERROR:", facts["error"]); sys.exit(1)

print("\n" + "=" * 72)
print(coach.facts_to_text(facts))
print("=" * 72)

print("\n调用大模型讲解中...")
t0 = time.time()
res = coach.explain(facts)
print(f"耗时 {time.time()-t0:.1f}s  模型 {res.get('model')}  tokens {res.get('usage',{}).get('total_tokens')}")
print("\n" + "=" * 72)
print(res["content"])
print("=" * 72)
open("_last_explain.md", "w", encoding="utf-8").write(res["content"])
