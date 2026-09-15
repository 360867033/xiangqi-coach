"""
整盘复盘：把一盘棋的每一步都过一遍引擎，标出失着，并生成"局势曲线"。

算法（和 Lichess 的做法一致）：
  对第 i 个局面做一次搜索，得到 cp_i（走子方视角）和最佳着法。
  第 i 手由 S 方走出，则这一手的代价：
      loss = cp_{i-1}(S 视角的应有分数) - (-cp_i)(S 视角的实际分数)
           = cp_{i-1} + cp_i
  这样每个局面只需要搜索一次，效率翻倍。
"""
import time

from . import engine as engine_mod
from . import rules as R
from .coach import classify_loss, fmt_cp, _norm_move_score, _red_view


def parse_move_input(text):
    """把用户输入的一串着法解析成 UCI 列表。
    支持：UCI（h2e2）、中文记谱（炮二平五）、以及两者混排、带手数序号。"""
    text = text.replace('\n', ' ').replace('，', ' ').replace(',', ' ')
    text = text.replace('\t', ' ')
    # 去掉 "1." "1、" 等序号
    text = re_sub_handnums(text)
    tokens = [t for t in text.split(' ') if t.strip()]
    return tokens


def re_sub_handnums(text):
    import re
    text = re.sub(r'\d+\s*[.、)）]\s*', ' ', text)
    return text


def resolve_moves(board, red_to_move, tokens):
    """把 token 逐个匹配成合法着法，返回 (uci列表, 中文列表, 未识别token)"""
    ucis, chinese, unknown = [], [], []
    b = list(board)
    red = red_to_move
    for tk in tokens:
        tk = tk.strip()
        if not tk:
            continue
        legal = R.legal_moves(b, red)
        # 先试 UCI
        cand = None
        low = tk.lower()
        if len(low) == 4 and low[0] in 'abcdefghi' and low[2] in 'abcdefghi' \
                and low[1].isdigit() and low[3].isdigit():
            try:
                mv = R.uid_to_move(low)
                if mv in legal:
                    cand = mv
            except ValueError:
                cand = None
        # 再试中文记谱
        if cand is None:
            for mv in legal:
                if R.move_to_chinese(b, mv) == tk:
                    cand = mv
                    break
        if cand is None:
            unknown.append(tk)
            continue
        ucis.append(R.move_uid(cand))
        chinese.append(R.move_to_chinese(b, cand))
        b = R.apply_move(b, cand)
        red = not red
    return ucis, chinese, unknown


def review(uci_moves, start_fen=R.START_FEN, depth=14, cfg=None,
           progress=None, movetime=None):
    """复盘整盘棋。progress(done, total, note) 用于回报进度。"""
    cfg = cfg or {}
    eng = engine_mod.get_engine(cfg)
    board, red_to_move = R.parse_fen(start_fen)

    # 1) 展开所有局面
    positions = [{"board": list(board), "red": red_to_move,
                  "fen": R.to_fen(board, red_to_move), "uci": None, "chinese": None}]
    b, red = list(board), red_to_move
    moved_chinese = []
    for u in uci_moves:
        try:
            mv = R.uid_to_move(u)
        except ValueError:
            break
        ch = R.move_to_chinese(b, mv)
        b = R.apply_move(b, mv)
        red = not red
        positions.append({"board": list(b), "red": red, "fen": R.to_fen(b, red),
                          "uci": u, "chinese": ch})
        moved_chinese.append(ch)

    # 2) 每个局面搜索一次
    total = len(positions)
    evals = []
    for i, p in enumerate(positions):
        if progress:
            progress(i, total, f"分析第 {i + 1}/{total} 个局面")
        try:
            res = eng.analyze(p["fen"], depth=depth, movetime=movetime, multipv=1)
        except Exception as e:
            evals.append({"cp": None, "best": None, "error": str(e)})
            continue
        ln = res["lines"][0] if res["lines"] else {}
        cp, is_mate = _norm_move_score(ln)
        evals.append({
            "cp": cp, "is_mate": is_mate, "best": res["bestmove"],
            "best_chinese": None, "depth": ln.get("depth"),
            "wdl": ln.get("wdl"), "pv": ln.get("pv", []),
        })

    # 3) 逐手算代价
    moves = []
    for i in range(1, len(positions)):
        prev, cur = evals[i - 1], evals[i]
        mover = "红方" if positions[i - 1]["red"] else "黑方"
        rec = {
            "index": i,
            "no": (i + 1) // 2,
            "side": mover,
            "uci": positions[i]["uci"],
            "chinese": positions[i]["chinese"],
            "fen_before": positions[i - 1]["fen"],
            "cp_before": prev.get("cp"),
            "cp_after": cur.get("cp"),
            "score_red_after": _red_view(cur.get("cp"), positions[i]["red"]),
            "best_uci": prev.get("best"),
            "loss_cp": None,
            "label": None,
            "is_best": False,
            "pv_after": cur.get("pv", [])[:8],
        }
        if prev.get("cp") is not None and cur.get("cp") is not None:
            loss = max(0, prev["cp"] + cur["cp"])
            rec["loss_cp"] = loss
            rec["label"] = classify_loss(loss)
        if prev.get("best") and prev["best"] == positions[i]["uci"]:
            rec["is_best"] = True
        if prev.get("best"):
            try:
                rec["best_chinese"] = R.move_to_chinese(
                    positions[i - 1]["board"], R.uid_to_move(prev["best"]))
            except Exception:
                rec["best_chinese"] = prev["best"]
        # 这一手的引擎预演（中文）
        try:
            seq, _, _ = R.describe_line(positions[i]["board"], cur.get("pv", [])[:8],
                                        positions[i]["red"], limit=8)
            rec["pv_chinese"] = seq
        except Exception:
            rec["pv_chinese"] = []
        moves.append(rec)

    # 4) 局势曲线（红方视角）
    curve = []
    for i, e in enumerate(evals):
        red = positions[i]["red"]
        y = _red_view(e.get("cp"), red)
        if y is None:
            y = 0
        curve.append({"ply": i, "cp_red": max(-1500, min(1500, y))})

    # 5) 统计
    def side_stats(side):
        ms = [m for m in moves if m["side"] == side and m["loss_cp"] is not None]
        if not ms:
            return {}
        bad = [m for m in ms if m["loss_cp"] > 60]
        big = [m for m in ms if m["loss_cp"] > 150]
        avg = sum(m["loss_cp"] for m in ms) / len(ms)
        return {"moves": len(ms), "avg_loss": round(avg, 1),
                "inaccuracies": len(bad), "mistakes": len(big),
                "worst": max(ms, key=lambda m: m["loss_cp"])}

    worst = sorted([m for m in moves if m["loss_cp"] is not None],
                   key=lambda m: -m["loss_cp"])[:6]

    return {
        "start_fen": start_fen,
        "depth": depth,
        "moves": moves,
        "curve": curve,
        "stats": {"red": side_stats("红方"), "black": side_stats("黑方")},
        "worst_moves": worst,
    }


def review_to_text(rev):
    """把复盘结果渲染成给大模型的材料"""
    L = []
    st = rev["stats"]
    L.append(f"【复盘】共 {len(rev['moves'])} 手，引擎深度 {rev['depth']}")
    for side in ("红方", "黑方"):
        s = st.get(side) or {}
        if s:
            L.append(f"{side}：走了 {s['moves']} 手，平均每手损失 {s['avg_loss']} 厘兵，"
                     f"不精确以上 {s['inaccuracies']} 手，失误以上 {s['mistakes']} 手")
    L.append("")
    L.append("【逐手记录】（代价=这一手比引擎最佳着法多损失的厘兵）")
    for m in rev["moves"]:
        loss = m["loss_cp"]
        loss_txt = "最佳" if m.get("is_best") else (f"损失 {loss}" if loss is not None else "—")
        bm = f"，引擎最佳是 {m['best_chinese']}" if (not m.get("is_best") and m.get("best_chinese")) else ""
        pv = ' '.join(m.get("pv_chinese") or [])[:60]
        L.append(f"  {m['no']}.{'红' if m['side'] == '红方' else '黑'} {m['chinese']} "
                 f"[{loss_txt}]{bm}" + (f" → 后续 {pv}" if pv else ""))
    L.append("")
    L.append("【最严重的几手】")
    for m in rev["worst_moves"]:
        if (m["loss_cp"] or 0) <= 60:
            continue
        L.append(f"  第{m['no']}手 {m['side']}走 {m['chinese']}：损失 {m['loss_cp']} 厘兵"
                 f"（{m['label']}），引擎推荐 {m['best_chinese']}；"
                 f"这一手之后引擎预演：{' '.join(m.get('pv_chinese') or [])}")
    return "\n".join(L)


SYS_REVIEW = """你是一位中国象棋教练，正在给一位业余棋友做整盘复盘。

【铁律】
1. 只能使用我提供的着法、分数。绝对不许编造棋盘上不存在的棋子或位置。
2. 着法用中文记谱（炮二平五、马8进7 这种）。
3. **禁止出现字母+数字的格子坐标**，例如 a0、h2、b7、"从 b2 到 e2"，也不要用
   "第3行第7列""(7,2)"这种数字对——读者完全看不懂。
   要指位置就用中文说法：红方"九路车""炮八路"（路数从红方右手边数起），
   黑方"3路卒""马8路"（路数从黑方右手边数起），指横线就说"第几条横线"（从各自底线数起）。
   路数小的一侧是该方的右手边，想指左右方位就直接报路数，别用"左翼/右翼"（容易说反）。
4. 分数单位"厘兵"，100 厘兵 = 一个兵的价值。损失超过 300 厘兵通常等于丢子或漏杀。
5. 不要逐手罗列，要归纳规律。

【输出结构】用 Markdown，严格按下面五节：
### 总评
### 三个阶段
（开局/中局/残局各一段，说明这一阶段的局面走向和双方得失）
### 关键转折点
（挑 2~4 手，讲清当时应该怎么想、实际错在哪、代价是什么）
### 你的习惯性问题
（从错误里归纳 2~3 条可迁移的毛病，例如"老是忘记对方有炮镇中路"这类）
### 下一步练习建议
（具体、可执行，最多 3 条）
"""


def review_report(rev, cfg=None):
    from .coach import chat
    msgs = [{"role": "system", "content": SYS_REVIEW},
            {"role": "user", "content": review_to_text(rev)}]
    return chat(msgs, cfg)
