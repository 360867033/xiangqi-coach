"""测试：快速模式讲解 + 整盘复盘全流程"""
import json, time, urllib.request, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from xq import rules as R, review as RV

BASE = os.environ.get("XQ_BASE", "http://127.0.0.1:8760")   # 可用环境变量指向临时端口的服务

def post(url, body):
    req = urllib.request.Request(BASE + url, data=json.dumps(body).encode(),
                                headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=900)

TEXT = "炮二平五 马8进7 马二进三 车9平8 车一平二 卒7进1 兵七进一 马2进3 车二进六 炮8平9 车二平三 炮9退1"
b, red = R.parse_fen(R.START_FEN)
ucis, ch, unk = RV.resolve_moves(b, red, RV.parse_move_input(TEXT))
for u in ucis:
    b = R.apply_move(b, R.uid_to_move(u)); red = not red
FEN = R.to_fen(b, red)

# ---- 1) 快速模式 ----
import re
COORD = re.compile(r"(?<![A-Za-z0-9])[a-iA-I]\d(?![A-Za-z0-9])")

print("=" * 66)
print("[1] 快速模式（reasoning_effort=none）")
t0 = time.time(); first = None; n = 0
body = []
for chunk in post("/api/explain", {"fen": FEN, "played": "a3a4", "effort": "none"}):
    for part in chunk.decode("utf-8", "replace").split("\n\n"):
        if not part.strip().startswith("data:"):
            continue
        o = json.loads(part.strip()[5:].strip())
        if o["t"] == "delta":
            if first is None:
                first = time.time() - t0
                print(f"  首字节 {first:.1f}s")
            n += len(o["d"])
            body.append(o["d"])
print(f"  正文 {n} 字，总耗时 {time.time()-t0:.1f}s")
full = "".join(body)
open("_last_explain.md", "w", encoding="utf-8").write(full)
hit = COORD.findall(full)
print(f"  中文路数说法出现 {full.count('路')} 次")
print(f"  字母坐标残留: {hit if hit else '无 ✓'}")
if hit:
    print("  失败：讲解里出现了字母坐标 —— 材料或过滤有问题")
    sys.exit(1)
if "路" not in full:
    print("  警告：讲解里完全没出现「路」，中文位置表述可能没生效")
print("  讲解开头：", full.strip().splitlines()[0][:60] if full.strip() else "（空）")

# ---- 2) 整盘复盘 ----
print("=" * 66)
print("[2] 整盘复盘（深度 12，缩短测试时间）")
GAME = ("炮二平五 马8进7 马二进三 车9平8 车一平二 卒7进1 兵七进一 马2进3 "
        "车二进六 炮8平9 车二平三 炮9退1 马八进七 车8进5 兵五进一 士4进5 "
        "车三退一 炮9平7 车三平四 马7进8")
r = json.loads(post("/api/review", {"text": GAME, "depth": 12}).read())
jid = r["job_id"]
print("  任务:", jid)
t0 = time.time()
while True:
    j = json.loads(urllib.request.urlopen(f"{BASE}/api/job?id={jid}", timeout=60).read())
    if j["finished"]:
        break
    print(f"  {j['note']}", end="\r")
    time.sleep(1.0)
print(f"  完成，耗时 {time.time()-t0:.1f}s")
if j.get("error"):
    print("  失败:", j["error"]); sys.exit(1)
res = j["result"]
print(f"  共 {len(res['moves'])} 手，未识别: {res['unknown_tokens'] or '无'}")
st = res["stats"]
for k, lab in (("red", "红方"), ("black", "黑方")):
    s = st.get(k) or {}
    print(f"  {lab}: 平均损失 {s.get('avg_loss')} 厘兵, 不精确以上 {s.get('inaccuracies')} 手, "
          f"失误以上 {s.get('mistakes')} 手")
print("  失着 Top5:")
for m in res["worst_moves"][:5]:
    print(f"    第{m['no']}手 {m['side']} {m['chinese']} 损失 {m['loss_cp']} "
          f"({m['label']}) 推荐 {m['best_chinese']}")
print(f"  曲线点数: {len(res['curve'])}")

# ---- 3) 复盘报告 ----
print("=" * 66)
print("[3] AI 复盘报告（快速模式）")
t0 = time.time(); n = 0; first = None
rep = []
for chunk in post("/api/review_report", {"job_id": jid, "effort": "none"}):
    for part in chunk.decode("utf-8", "replace").split("\n\n"):
        if not part.strip().startswith("data:"):
            continue
        o = json.loads(part.strip()[5:].strip())
        if o["t"] == "delta":
            if first is None:
                first = time.time() - t0
            n += len(o["d"])
            rep.append(o["d"])
        elif o["t"] == "error":
            print("  错误:", o["d"])
print(f"  首字节 {first:.1f}s，报告 {n} 字，总耗时 {time.time()-t0:.1f}s")
report = "".join(rep)
hit2 = COORD.findall(report)
print(f"  字母坐标残留: {hit2 if hit2 else '无 ✓'}")
if hit2:
    print("  失败：复盘报告里出现了字母坐标")
    sys.exit(1)
open("_last_report.md", "w", encoding="utf-8").write(report)

# ---- 4) 追问（必须只答所问，不能又讲一遍局面） ----
print("=" * 66)
print("[4] 追问（带了上一次讲解；应答所问，不许重出六节标题）")
HEADINGS = ["一句话结论", "局面态势", "最佳着法好在哪", "棋理归纳", "下次怎么想"]
QUESTION = "你推荐的这步棋走完之后，对方最好的应对是什么？为什么？"
t0 = time.time(); n = 0; first = None
ans = []
for chunk in post("/api/ask", {"fen": FEN, "played": "a3a4", "effort": "none",
                               "question": QUESTION,
                               "prior": full, "history": []}):
    for part in chunk.decode("utf-8", "replace").split("\n\n"):
        if not part.strip().startswith("data:"):
            continue
        o = json.loads(part.strip()[5:].strip())
        if o["t"] == "delta":
            if first is None:
                first = time.time() - t0
            n += len(o["d"])
            ans.append(o["d"])
        elif o["t"] == "error":
            print("  错误:", o["d"])
answer = "".join(ans)
open("_last_ask.md", "w", encoding="utf-8").write(answer)
print(f"  首字节 {first:.1f}s，回答 {n} 字，总耗时 {time.time()-t0:.1f}s")
head_hit = [h for h in HEADINGS if h in answer]
print(f"  旧小节标题残留: {head_hit if head_hit else '无 ✓'}")
print(f"  字母坐标残留: {COORD.findall(answer) if COORD.findall(answer) else '无 ✓'}")
if head_hit:
    print("  失败：追问回答里又出现了讲解用的六节标题 —— 多半是提示词又串回 build_explain_prompt")
    sys.exit(1)
if COORD.findall(answer):
    print("  失败：追问回答里出现了字母坐标")
    sys.exit(1)
if n > 1400:
    print(f"  失败：追问回答 {n} 字，太长了（像是又把局面讲了一遍）")
    sys.exit(1)
print("  回答开头：", answer.strip().splitlines()[0][:70] if answer.strip() else "（空）")

# ---- 5) 预演摆盘所需的数据：/api/analyze 必须给出着法序列（pv_uci） ----
print("=" * 66)
print("[5] 预演摆盘数据（/api/analyze 的 candidates[].pv_uci）")
an = json.loads(post("/api/analyze", {"fen": FEN, "played": "a3a4", "depth": 12}).read())
if not an.get("ok"):
    print("  失败：分析接口报错", an)
    sys.exit(1)
f2 = an["facts"]
bad = []
for c in f2["candidates"]:
    pu, pc = c.get("pv_uci") or [], c.get("pv_chinese") or []
    print(f"  {c['rank']}. {c['chinese']}  预演 {len(pu)} 步：{' '.join(pc[:6])}")
    if not pu:
        bad.append(f"第{c['rank']}名没有 pv_uci")
    elif len(pu) != len(pc):
        bad.append(f"第{c['rank']}名 pv_uci({len(pu)}) 与 pv_chinese({len(pc)}) 长度不一致")
    elif any(len(u) != 4 for u in pu):
        bad.append(f"第{c['rank']}名 pv_uci 里有非法串 {pu}")
if f2.get("played") and not f2["played"].get("is_best"):
    pu = f2["played"].get("pv_uci") or []
    print(f"  你  {f2['played']['chinese']}  预演 {len(pu)} 步：{' '.join(f2['played']['pv_chinese'][:6])}")
    if not pu:
        bad.append("学生着法那一行没有 pv_uci（那条线在界面上摆不了）")
if bad:
    print("  失败：" + "；".join(bad))
    sys.exit(1)
print("  ✓ 每条预演线都能直接交给前端摆盘（长度与中文记谱一一对应）")

print("\n全部通过")
