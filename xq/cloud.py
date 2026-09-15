"""
象棋云库（chessdb.cn）查询

云库的价值：它给出的是「实战+分布式计算」沉淀下来的着法排序标记，
能回答"这一步在人类实战里算好棋还是错漏"，正好补引擎只看计算的盲区。

返回字段：
  move    着法（UCI）
  score   云库分值（正=红优）
  rank    2=最佳着法(!)  1=合理着法(*)  0=错漏着法(?)
  note    原始标记，形如 "! (44-02)"，括号内是 (已知应着-可走应着)
  winrate 走棋方胜率（%）
"""
import json
import urllib.parse
import urllib.request

API = "http://api.chessdb.cn:81/chessdb.php"
RANK_LABEL = {2: "最佳着法", 1: "合理着法", 0: "错漏着法"}


def _get(params, timeout=8):
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "xiangqi-coach/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace").strip()


def query_all(fen, showall=False, timeout=8):
    """查询局面的全部已知着法。返回 (moves, status)"""
    try:
        txt = _get({"action": "queryall", "board": fen,
                    "showall": 1 if showall else 0}, timeout)
    except Exception as e:
        return [], f"网络错误: {type(e).__name__}"
    if txt in ("invalid board", "unknown", "checkmate", "stalemate"):
        return [], txt
    out = []
    for item in txt.split("|"):
        if not item.strip():
            continue
        rec = {}
        for kv in item.split(","):
            if ":" not in kv:
                continue
            k, v = kv.split(":", 1)
            k = k.strip()
            if k in ("score", "rank"):
                try:
                    rec[k] = int(v)
                except ValueError:
                    rec[k] = None
            elif k == "winrate":
                try:
                    rec[k] = float(v)
                except ValueError:
                    rec[k] = None
            else:
                rec[k] = v
        if "move" in rec:
            rec["rank_label"] = RANK_LABEL.get(rec.get("rank"), "未知")
            out.append(rec)
    out.sort(key=lambda x: (-(x.get("rank") or 0), -(x.get("score") or -9999)))
    return out, "ok"


def query_score(fen, timeout=8):
    try:
        txt = _get({"action": "queryscore", "board": fen}, timeout)
    except Exception as e:
        return None, f"网络错误: {type(e).__name__}"
    if txt.startswith("eval:"):
        try:
            return int(txt.split(":", 1)[1]), "ok"
        except ValueError:
            return None, txt
    return None, txt


def query_pv(fen, timeout=8):
    try:
        txt = _get({"action": "querypv", "board": fen}, timeout)
    except Exception as e:
        return None, f"网络错误: {type(e).__name__}"
    if txt.startswith("score:"):
        rec = {}
        for kv in txt.split(","):
            if ":" in kv:
                k, v = kv.split(":", 1)
                rec[k] = v
        if "pv" in rec:
            rec["pv"] = rec["pv"].split("|")
        return rec, "ok"
    return None, txt


def queue(fen, timeout=8):
    """提交后台计算（让云库去算这个局面，之后再来查就有数据了）"""
    try:
        return _get({"action": "queue", "board": fen}, timeout), "ok"
    except Exception as e:
        return None, f"网络错误: {type(e).__name__}"


def lookup(fen, timeout=6):
    """给讲解用的整合查询"""
    moves, st = query_all(fen, timeout=timeout)
    by_move = {}
    for m in moves:
        by_move[m["move"]] = m
    return {"status": st, "moves": moves, "by_move": by_move}
