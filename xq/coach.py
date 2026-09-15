"""
讲解大脑：把「引擎算出来的硬事实」+「云库的人类经验」组装成结构化材料，
再交给大模型翻译成"为什么"。

设计原则（借鉴 chess-tutor-agent 的教训）：
  大模型只负责"说话"，不负责"算棋"。所有棋子位置、着法序列、分数都由
  引擎/云库提供，提示词里明确禁止模型自行编造局面。
"""
import json
import os
import re
import urllib.error
import urllib.request

from . import cloud as cloud_mod
from . import engine as engine_mod
from . import rules as R

# ---------------------------------------------------------------- 配置
DEFAULT_CFG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "config.json")


def load_cfg(path=None):
    p = path or DEFAULT_CFG_PATH
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


# ---------------------------------------------------------------- 分差分类
def classify_loss(loss_cp):
    if loss_cp is None:
        return "未知"
    if loss_cp <= 20:
        return "好棋"
    if loss_cp <= 60:
        return "略有不准"
    if loss_cp <= 150:
        return "不精确"
    if loss_cp <= 300:
        return "失误"
    return "严重失误（漏着）"


def _norm_move_score(line):
    """把 (score_cp, mate) 归一成走子方视角的厘兵值；返回 (cp, 是否杀棋)"""
    if line is None:
        return None, False
    if line.get("mate") is not None:
        m = line["mate"]
        return (30000 - abs(m) * 100) * (1 if m > 0 else -1), True
    return line.get("score_cp"), False


def _red_view(cp, red_to_move):
    if cp is None:
        return None
    return cp if red_to_move else -cp


def fmt_cp(cp):
    if cp is None:
        return "—"
    return f"{cp / 100:+.2f}"


def _move_cn_safe(board, uci):
    """UCI 着法 -> 中文记谱。转不动就原样返回（宁可少翻译，不可瞎翻译）"""
    if not uci:
        return ""
    try:
        mv = R.uid_to_move(uci)
    except Exception:
        return uci
    if not board[mv[0] * 9 + mv[1]]:
        return uci
    try:
        return R.move_to_chinese(board, mv)
    except Exception:
        return uci


# ---------------------------------------------------------------- 事实组装
def build_facts(fen, played_move=None, depth=18, movetime=None, multipv=4,
                want_cloud=True, cfg=None):
    """核心：分析一个局面，返回给讲解用的事实包"""
    cfg = cfg or load_cfg()
    try:
        board, red_to_move = R.parse_fen(fen)
    except Exception as e:
        return {"error": f"FEN 解析失败：{e}"}
    ok, probs = R.validate(board, red_to_move)
    if not ok:
        return {"error": "局面不合法，已阻止分析：" + "；".join(probs)}
    side_name = "红方" if red_to_move else "黑方"
    legal = R.legal_moves(board, red_to_move)
    legal_uids = {R.move_uid(m) for m in legal}
    if not legal:
        return {"error": "当前局面走子方已无着可走（被将死或困毙）"}

    eng = engine_mod.get_engine(cfg)
    res = eng.analyze(fen, depth=depth, movetime=movetime,
                      multipv=max(1, multipv))
    lines = res["lines"]

    # 候选着法表
    cands = []
    for ln in lines:
        cp, is_mate = _norm_move_score(ln)
        uid = ln["pv"][0] if ln["pv"] else None
        mv = None
        chinese = "?"
        if uid and uid in legal_uids:
            mv = R.uid_to_move(uid)
            chinese = R.move_to_chinese(board, mv)
        seq, endboard, matdiff = R.describe_line(board, ln["pv"],
                                                 red_to_move, limit=12)
        cands.append({
            "rank": ln["multipv"],
            "uci": uid,
            "chinese": chinese,
            "score_cp": cp,
            "score_red": _red_view(cp, red_to_move),
            "is_mate": is_mate,
            "wdl": ln["wdl"],
            "depth": ln["depth"],
            "pv_chinese": seq,
            # 给前端的"预演摆盘"用：完整着法序列（UCI）。
            # 长度对齐 pv_chinese —— describe_line 遇到不合法着法就 break，
            # 所以它返回的记谱正好是 pv 的前缀。
            # 注意：facts_to_text 从不打印这个字段，大模型看不到坐标。
            "pv_uci": list(ln["pv"][:len(seq)]),
            "capture": bool(mv and R.is_capture(board, mv)),
            "end_material_diff": matdiff,
        })

    best = cands[0] if cands else None

    # 学生实际走的着法
    played = None
    if played_move:
        pu = played_move.strip().lower()
        if pu not in legal_uids:
            return {"error": f"着法 {played_move} 在当前局面不合法"}
        mv = R.uid_to_move(pu)
        chinese = R.move_to_chinese(board, mv)
        if best and best["uci"] == pu:
            played = {
                "uci": pu, "chinese": chinese, "score_cp": best["score_cp"],
                "score_red": best["score_red"], "is_best": True,
                "loss_cp": 0, "label": "最佳着法",
                "pv_chinese": best["pv_chinese"],
                "pv_uci": best["pv_uci"],
                "capture": R.is_capture(board, mv),
                "wdl": best["wdl"],
            }
        else:
            r2 = eng.analyze_move(fen, pu, depth=depth, movetime=movetime)
            cp2, mate2 = _norm_move_score(r2.get("line"))
            seq2, _, mat2 = R.describe_line(board, r2.get("line", {}).get("pv", []),
                                            red_to_move, limit=12)
            loss = None
            if best and best["score_cp"] is not None and cp2 is not None:
                loss = max(0, best["score_cp"] - cp2)
            played = {
                "uci": pu, "chinese": chinese, "score_cp": cp2,
                "score_red": _red_view(cp2, red_to_move), "is_best": False,
                "loss_cp": loss, "label": classify_loss(loss),
                "pv_chinese": seq2,
                "pv_uci": list(r2.get("line", {}).get("pv", [])[:len(seq2)]),
                "capture": R.is_capture(board, mv),
                "wdl": r2.get("line", {}).get("wdl"),
                "mate": mate2,
            }

    # 云库
    cloud = {"status": "skipped", "moves": [], "by_move": {}}
    if want_cloud:
        try:
            cloud = cloud_mod.lookup(fen, timeout=cfg.get("cloud_timeout", 6))
        except Exception as e:
            cloud = {"status": f"错误:{type(e).__name__}", "moves": [], "by_move": {}}
    # 云库着法原样是 UCI（h2e2），材料里一律换成中文——否则模型会照抄成坐标
    for m in cloud.get("moves") or []:
        m["chinese"] = _move_cn_safe(board, m.get("move"))

    r_mat, b_mat, diff = R.material_balance(board)
    return {
        "fen": fen,
        "board_text": R.board_text(board),
        "positions": R.piece_positions(board),
        "side_to_move": side_name,
        "red_to_move": red_to_move,
        "material": R.material_summary(board),
        "material_diff": diff,
        "candidates": cands,
        "best": best,
        "played": played,
        "cloud": {"status": cloud["status"], "moves": cloud["moves"][:20]},
        "depth": lines[0]["depth"] if lines else 0,
        "legal_count": len(legal),
        "band": R.evaluate_band(_red_view(best["score_cp"], red_to_move) if best and best["score_cp"] is not None else 0,
                                True),
    }


# ---------------------------------------------------------------- 提示词
SYS_COACH = """你是一位中国象棋教练，正在给一位业余棋友讲棋。他的水平是：懂规则、会走子，但看不懂引擎分数背后的道理。

【铁律】
1. 你只能使用我提供的局面、着法、分数、云库数据。绝对不许编造棋盘上不存在的棋子、位置或着法。
2. 如果你不确定某个位置有什么子，就只谈"提供的着法序列里出现的"棋子和格子。
3. 着法一律使用中文记谱（炮二平五、马8进7 这种）。
4. **禁止出现字母+数字的格子坐标**，例如 a0、h2、b7、i9、"从 b2 到 e2"，也不要用
   "第3行第7列""(7,2)"这种数字对——读者完全看不懂，
   一律改用中文说法：红方说"红方九路车""炮八路"（路数从红方右手边数起），
   黑方说"黑方3路卒""马8路"（路数从黑方右手边数起），
   要指横线就说"第几条横线"（从各自底线数起），讲移动就用中文记谱（车九平二）。
   路数小的一侧就是该方的右手边——想指左右方位时**直接报路数**，
   不要说"左翼/右翼"（极易说反）。我给的棋盘和子力位置清单里已经有现成的中文说法，请直接沿用。
5. 分数含义：单位"厘兵"，100厘兵=1个兵的价值差。分数是【走子方视角】，正数=走子方占优。给出的红方视角分数正数=红优。
6. 不要罗列数字，要把数字翻译成"谁占优、优势多大、够不够赢"。

【讲解要往这些棋理概念上靠】（按局面挑最贴切的，不要全部堆上）
子力价值 / 位置好坏 / 先手与主动权 / 控制要道（中路、将门、河界）/ 牵制与反牵制 /
子力协调与配合 / 马路是否被蹩、车路是否通畅 / 士象结构完整性与弱点 /
兵的过河与保护 / 将门是否暴露 / 有无强制手段（将军、吃子、做杀）

【输出结构】用 Markdown，严格按下面六节，标题照抄：
### 一句话结论
### 局面态势
### 最佳着法好在哪
### 其他走法（含你走的这一步）差在哪
### 棋理归纳
### 下次怎么想
"""


def facts_to_text(facts, for_review=False, compact=False):
    """把事实包渲染成提示词里的材料文本。

    注意：这里**一个字母坐标都不出现**（候选表不列 uci、云库着法转中文、
    棋盘不带 a..i 列标），模型看不到坐标，也就不会写出来。

    compact=True：追问时用。去掉 ASCII 棋盘（那是「复述局面」的最大诱因，
    也是 prompt 里最长的一段），只留子力位置清单 + 着法表 + 云库。
    """
    L = []
    L.append(f"【局面】走子方 = {facts['side_to_move']}")
    L.append(f"【子力】{facts['material']}")
    if not compact:
        L.append("【棋盘】")
        L.append(facts["board_text"])
    if facts.get("positions"):
        L.append("【子力位置（讲棋请照这些中文说法，不要写字母坐标）】")
        L.append(facts["positions"])
    L.append(f"【引擎】皮卡鱼 深度 {facts['depth']}，共 {facts['legal_count']} 个合法着法")
    L.append("")
    L.append("【引擎候选着法表】（分数：厘兵；红方视角正数=红优）")
    L.append("名次 | 着法(中文) | 走子方视角 | 红方视角 | 胜/和/负(千分比) | 相关")
    n_cand = 4 if compact else 5
    for c in facts["candidates"][:n_cand]:
        w = c["wdl"]
        wtxt = f"{w[0]}/{w[1]}/{w[2]}" if w else "—"
        tag = "吃子" if c["capture"] else ""
        if c["is_mate"]:
            tag = (tag + " 杀棋").strip()
        L.append(f"{c['rank']} | {c['chinese']} | "
                 f"{fmt_cp(c['score_cp'])} | {fmt_cp(c['score_red'])} | {wtxt} | {tag}")
    L.append("")
    L.append("【候选着法的引擎预演（中文记谱，引擎认为的双方最佳续着）】")
    for c in facts["candidates"][:n_cand]:
        L.append(f"  {c['rank']}. {c['chinese']}：{' '.join(c['pv_chinese'][:8])}")
    if facts.get("best"):
        b = facts["best"]
        L.append("")
        L.append(f"【本局面最佳着法】{b['chinese']}，评分 {fmt_cp(b['score_cp'])}，"
                 f"预演：{' '.join(b['pv_chinese'])}")
    p = facts.get("played")
    if p:
        L.append("")
        if p.get("is_best"):
            L.append(f"【学生走的着法】{p['chinese']} —— 就是引擎的最佳着法，走对了。")
        else:
            L.append(f"【学生走的着法】{p['chinese']}")
            L.append(f"  评分 {fmt_cp(p['score_cp'])}（红方视角 {fmt_cp(p['score_red'])}）")
            L.append(f"  比最佳着法差 {fmt_cp(p['loss_cp'])}；机器判定：{p['label']}")
            L.append(f"  走了这一步之后，引擎认为对手的最佳应对是：{' '.join(p['pv_chinese'])}")
            L.append("  （这条线就是「这步棋会被怎么惩罚」的答案，请据此解释他在哪一环漏算了）")
    cl = facts.get("cloud") or {}
    if cl.get("status") == "ok" and cl.get("moves"):
        L.append("")
        L.append("【象棋云库（实战+分布式计算的着法排序，!最佳 *合理 ?错漏）】")
        for m in cl["moves"][:10 if compact else 14]:
            note = (m.get("note") or "").strip()
            wr = m.get("winrate")
            L.append(f"  {m.get('chinese') or m['move']}：{m.get('rank_label')} "
                     f"分数{m.get('score')} 胜率{wr}% {note}")
    elif cl.get("status") not in (None, "skipped", "ok"):
        L.append(f"\n【象棋云库】无数据（{cl.get('status')}）")
    return "\n".join(L)


def build_explain_prompt(facts):
    head = "请按六节结构讲解这个局面。重点回答：为什么推荐的着法好，以及学生走的那一步差在哪里、会付出什么代价。"
    if not facts.get("played"):
        head = ("请按六节结构讲解这个局面。因为还没有学生走的着法，"
                "「其他走法差在哪」这一节请挑候选表里排名靠后的 2~3 个着法做对比。")
    return head + "\n\n===== 材料 =====\n" + facts_to_text(facts)


# ---------------------------------------------------------------- 追问
SYS_FOLLOWUP = """你是一位中国象棋教练。刚才你已经给这位棋友完整讲过当前局面了，
现在他在就其中某个细节追问。

【本次任务】只回答他问的那一件事。**不要重新讲解局面。**

【铁律】（和讲解时一样）
1. 只能使用我提供的着法、分数、云库数据，不许编造棋盘上不存在的棋子、位置或着法。
2. 材料里查不到的（比如某一步的评分），就直接说"材料里没有这步的评分"，不要猜。
3. 着法一律用中文记谱（炮二平五、马8进7）。
4. **禁止字母+数字坐标**（a0、h2、b7），也不要用"第3行第7列""(7,2)"。
   说方位一律报路数：红方"红方九路车"、黑方"黑方3路卒"；说横线用"第几条横线"。
   不要写"左翼/右翼"（极易说反）。材料里有现成的中文说法，直接沿用。
5. 分数单位"厘兵"（100 厘兵 = 1 个兵），红方视角正数 = 红优。

【回答方式】（这一节是重点，请严格遵守）
1. **一个小节标题都不要写。**尤其不要出现「一句话结论」「局面态势」
   「最佳着法好在哪」「其他走法差在哪」「棋理归纳」「下次怎么想」——
   那是上一次讲解的结构。即使这些字出现在下面的上下文里，也不是这次要用的结构。
2. **不要复述局面。**子力对比、谁在第几条横线、候选着法表，他都看过了。
   只有**直接支撑你答案的那一两项数据**才可以引用，而且一句话带过
   （例如"云库里这步标 ?，比最佳着法低 9 个点"）。
3. 第一段就直接给答案，然后才给理由。总长 150~350 字，最多分 3 条。
4. 如果他问"A 和 B 是什么关系"，就把两者各自的作用、以及谁牵制谁写成
   一段因果，不要借题发挥成新的一篇讲解。
5. 如果他问"我现在该走什么"，直接给出具体着法（中文记谱）加一句理由。
"""


def build_followup_messages(facts, question, history=None, prior=None):
    """组装「追问」的消息序列。

    这里是本次修复的核心：以前追问用的还是 build_explain_prompt（"请按六节结构
    讲解这个局面"），于是模型把追问当成又一次讲解——回答里又出现
    「一句话结论 / 局面态势」，还照着材料把局面复述一遍。
    现在改成：专用系统提示（只答所问、不许写小节标题、不许复述材料）
    + 精简材料（去掉 ASCII 棋盘）+ 上一次讲解 + 历史问答 + 本次问题。
    """
    msgs = [{"role": "system", "content": SYS_FOLLOWUP}]
    msgs.append({"role": "user",
                 "content": "【当前局面材料】（仅供你核对，不要复述）\n\n"
                            + facts_to_text(facts, compact=True)})
    prior = (prior or "").strip()
    if prior:
        msgs.append({"role": "assistant", "content": prior})
    for h in (history or [])[-8:]:
        role = "assistant" if h.get("role") == "assistant" else "user"
        c = (h.get("content") or "").strip()
        if c:
            msgs.append({"role": role, "content": c})
    msgs.append({"role": "user", "content": question})
    return msgs


# ---------------------------------------------------------------- LLM
class LLMError(RuntimeError):
    pass


def chat(messages, cfg=None, model=None, temperature=0.4, timeout=180):
    cfg = cfg or load_cfg()
    key = cfg.get("api_key") or ""
    base = (cfg.get("base_url") or "https://api.deepseek.com/v1").rstrip("/")
    mdl = model or cfg.get("model") or "deepseek-flash"
    if not key:
        raise LLMError("config.json 里没有配置 api_key")
    body = {"model": mdl, "messages": messages,
            "temperature": temperature, "stream": False}
    effort = cfg.get("reasoning_effort")
    if effort:
        body["reasoning_effort"] = effort
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise LLMError(f"接口返回 {e.code}：{e.read().decode('utf-8', 'replace')[:300]}")
    except Exception as e:
        raise LLMError(f"调用失败：{type(e).__name__} {e}")
    return {"content": d["choices"][0]["message"]["content"],
            "model": d.get("model"), "usage": d.get("usage")}


def explain(facts, cfg=None):
    msgs = [{"role": "system", "content": SYS_COACH},
            {"role": "user", "content": build_explain_prompt(facts)}]
    r = chat(msgs, cfg)
    r["materials"] = facts_to_text(facts)
    return r


def ask_followup(facts, history, question, cfg=None, prior=None):
    return chat(build_followup_messages(facts, question, history, prior), cfg)
