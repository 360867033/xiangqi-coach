# -*- coding: utf-8 -*-
"""追问链路自测（离线，不调引擎/大模型）

背景（本次修复的 bug）：追问时发给大模型的还是一条
「请按六节结构讲解这个局面」，于是模型把追问当成了又一次讲解——
回答里又冒出「一句话结论 / 局面态势」，还照着材料把局面复述一遍。

这个测试锁死三件事：
  1. 追问走的是 SYS_FOLLOWUP，消息里不再出现"六节结构"那条指令
  2. 上一次讲解作为 assistant 消息带进上下文
  3. 追问用的材料去掉了 ASCII 棋盘（"复述局面"的最大诱因）
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from xq import coach as C   # noqa: E402

FAIL = []


def check(cond, ok_msg, bad_msg=""):
    if cond:
        print("  [OK] " + ok_msg)
    else:
        print("  [!!] " + (bad_msg or ok_msg))
        FAIL.append(bad_msg or ok_msg)


def fake_facts():
    board_text = "\n".join(
        [f"r{r} | " + " · ".join(["炮"] * 9) for r in range(9, -1, -1)])
    board_text += "\n      红方路数 九 八 七 六 五 四 三 二 一\n      黑方路数 1 2 3 4 5 6 7 8 9"
    cands = []
    for i, (cn, cp) in enumerate([("车九进一", 30), ("车一进一", 20),
                                  ("卒5进1", -10), ("炮二平四", -40)], start=1):
        cands.append({
            "rank": i, "uci": "a0a1", "chinese": cn,
            "score_cp": cp, "score_red": cp, "is_mate": False,
            "wdl": [0, 900, 100], "depth": 18,
            "pv_chinese": ["车九进一", "卒5进1", "车二进八"],
            "capture": False, "end_material_diff": 0,
        })
    return {
        "fen": "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR b - - 0 1",
        "board_text": board_text,
        "positions": "红方 — 九路车（第1条横线）、一路车（第1条横线）\n黑方 — 1路车（第1条横线）",
        "side_to_move": "黑方", "red_to_move": False,
        "material": "双方子力完全一样", "material_diff": 0,
        "candidates": cands, "best": cands[0], "played": None,
        "cloud": {"status": "ok", "moves": [
            {"move": "a0a1", "chinese": "车九进一", "rank_label": "!最佳",
             "score": 20, "winrate": 92, "note": ""},
        ]},
        "depth": 18, "legal_count": 40, "band": "均势",
    }


def main():
    f = fake_facts()

    print("1) 追问不再使用讲解用的六节结构指令")
    msgs = C.build_followup_messages(f, "黑方卒5进1和红方车二进八的关系是什么",
                                     history=[], prior="## 上次的讲解正文")
    flat = "\n".join(m["content"] for m in msgs)
    check(msgs[0]["role"] == "system" and msgs[0]["content"] == C.SYS_FOLLOWUP,
          "system 用的是 SYS_FOLLOWUP",
          "system 不是 SYS_FOLLOWUP")
    check("请按六节结构" not in flat,
          "消息里没有『请按六节结构讲解这个局面』",
          "消息里仍有『请按六节结构讲解这个局面』——模型会当成又一次讲解")
    check(C.build_explain_prompt(f).count("请按六节结构") == 1,
          "讲解（explain）那条路径仍然保留六节结构",
          "讲解路径的六节结构被误删了")

    print("2) 追问提示词明确禁掉旧小节标题 + 禁掉复述")
    for h in ("一句话结论", "局面态势", "最佳着法好在哪",
              "其他走法", "棋理归纳", "下次怎么想"):
        check(h in C.SYS_FOLLOWUP, f"SYS_FOLLOWUP 点名禁止「{h}」",
              f"SYS_FOLLOWUP 没有点名禁止「{h}」")
    check("不要复述" in C.SYS_FOLLOWUP, "SYS_FOLLOWUP 要求不要复述局面")

    print("3) 上一次讲解进入上下文（模型知道已经讲过了）")
    check(any(m["role"] == "assistant" and "上次的讲解正文" in m["content"]
              for m in msgs), "prior 作为 assistant 消息带上",
          "prior 没有被带进上下文")
    msgs2 = C.build_followup_messages(f, "那我该走什么", prior="")
    check(not any(m["role"] == "assistant" for m in msgs2),
          "没有 prior 时不会塞空 assistant 消息")

    print("4) 追问材料瘦身：去掉 ASCII 棋盘")
    full = C.facts_to_text(f)
    slim = C.facts_to_text(f, compact=True)
    check("r9 |" in full, "讲解材料仍带 ASCII 棋盘")
    check("r9 |" not in slim, "追问材料已去掉 ASCII 棋盘",
          "追问材料里还留着 ASCII 棋盘（模型会照抄成『局面态势』）")
    check(len(slim) < len(full), "追问材料比讲解材料短",
          "追问材料没有变短")
    check("车九进一" in slim and "云库" in slim,
          "瘦身之后关键数据（着法表 / 云库）还在")

    print("5) 问题始终是最后一条 user 消息，历史最多 8 条")
    q = "为什么不能吃这个卒？"
    m = C.build_followup_messages(
        f, q, history=[{"role": "user", "content": f"问{i}"} for i in range(12)])
    check(m[-1] == {"role": "user", "content": q}, "最后一条就是本次问题")
    hist = [x for x in m if x["content"].startswith("问")]
    check(len(hist) == 8, "历史被截断到 8 条", f"历史条数 = {len(hist)}")

    print("6) 服务端 /api/ask 已切到追问链路")
    srv = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    seg = srv.split("def _handle_ask")[1].split("def _handle_review")[0]
    check("build_followup_messages" in seg, "/api/ask 调用 build_followup_messages",
          "/api/ask 没有调用 build_followup_messages")
    check("build_explain_prompt" not in seg,
          "/api/ask 里已经没有 build_explain_prompt",
          "/api/ask 里还在用 build_explain_prompt")
    check('data.get("prior")' in seg, "/api/ask 接收前端传来的上一次讲解")

    print("7) 前端会把上一次讲解带给追问")
    html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    check("window.lastExplain = md" in html, "讲解完成后留下正文副本")
    check("prior: window.lastExplain" in html, "追问请求里带 prior")
    check(html.count("window.lastExplain = ''") >= 3,
          "换局面 / 新开一局时会清掉旧讲解",
          "换局面时没有清掉旧讲解（会串场）")

    print()
    if FAIL:
        print(f"结果：{len(FAIL)} 项失败")
        for x in FAIL:
            print("  - " + x)
        return 1
    print("结果：全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
