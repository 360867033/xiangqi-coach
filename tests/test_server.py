import json, time, urllib.request, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from xq import rules as R, review as RV

TEXT = "炮二平五 马8进7 马二进三 车9平8 车一平二 卒7进1 兵七进一 马2进3 车二进六 炮8平9 车二平三 炮9退1"
b, red = R.parse_fen(R.START_FEN)
ucis, ch, unk = RV.resolve_moves(b, red, RV.parse_move_input(TEXT))
for u in ucis:
    b = R.apply_move(b, R.uid_to_move(u)); red = not red
FEN = R.to_fen(b, red)
print("测试局面:", FEN)
print("测试着法: 兵九进一 (a3a4)")

def post(url, body, stream=False):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=600)

# 1) 非流式分析
t0 = time.time()
r = json.loads(post("http://127.0.0.1:8760/api/analyze",
                    {"fen": FEN, "played": "a3a4"}).read())
print(f"\n[分析] {time.time()-t0:.1f}s ok={r['ok']}")
f = r["facts"]
print("  候选数:", len(f["candidates"]), " 云库:", f["cloud"]["status"])
print("  最佳:", f["best"]["chinese"], f["best"]["score_cp"])
print("  我的:", f["played"]["chinese"], f["played"]["score_cp"],
      " 损失:", f["played"]["loss_cp"], f["played"]["label"])

# 2) 流式讲解
print("\n[流式讲解]")
t0 = time.time()
first = None
total = 0
think = 0
resp = post("http://127.0.0.1:8760/api/explain", {"fen": FEN, "played": "a3a4"})
buf = b""
for chunk in resp:
    buf += chunk
    while b"\n\n" in buf:
        part, buf = buf.split(b"\n\n", 1)
        line = part.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        o = json.loads(line[5:].strip())
        if o["t"] == "delta":
            if first is None:
                first = time.time() - t0
                print(f"  首字节 {first:.1f}s")
            total += len(o["d"])
        elif o["t"] == "think":
            think += len(o["d"])
        elif o["t"] == "error":
            print("  ERROR:", o["d"])
print(f"  正文 {total} 字，思考 {think} 字，总耗时 {time.time()-t0:.1f}s")
