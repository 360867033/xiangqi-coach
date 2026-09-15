"""局面校验接口测试（自终止：起一个临时端口的服务，跑完就关）

背景：加了「编辑局面」功能后，前端需要一个能问"这个局面合法吗"的接口，
      而且 /api/legal 在遇到非法局面时不能再抛 500（否则前端一点棋子就卡死）。

用法： python tests/test_edit_api.py      （退出码 0 = 全部通过）
"""
import json
import os
import sys
import threading
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as S  # noqa: E402

PORT = 8873
BASE = f"http://127.0.0.1:{PORT}"

START = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
# 红帅被摆到九宫之外（rank5 中路），底线同时少了帅
KING_OUT = "rnbakabnr/9/1c5c1/p1p1p1p1p/4K4/9/P1P1P1P1P/1C5C1/9/RNBA1ABNR w - - 0 1"
# 黑将直接没了
NO_KING = "rnba1abnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"

fails = []


def check(ok, msg):
    if not ok:
        fails.append(msg)
        print("  ✗ " + msg)
    return ok


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=20) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def q(fen):
    return "/api/validate?fen=" + urllib.parse.quote(fen)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), S.Handler)
    srv.daemon_threads = True
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        print("【校验接口】/api/validate")
        st, d = get(q(START))
        check(st == 200 and d.get("ok") and d.get("valid"), f"开局应判为合法，实得 {d}")
        # 轮次也要参与判断：同样的摆子、改成黑走，红方没被将军，仍然合法
        st, d2 = get(q(START.replace(" w ", " b ")))
        check(d2.get("valid"), f"开局、黑方走棋也应合法，实得 {d2}")
        print("  ✓ 开局（红走/黑走）都判为合法")

        st, d = get(q(KING_OUT))
        check(d.get("valid") is False, f"红帅在九宫外应判为不合法，实得 {d}")
        check(any("九宫" in p for p in d.get("problems", [])),
              f"问题里应指出九宫问题，实得 {d.get('problems')}")
        print(f"  ✓ 帅出九宫被拦下：{d['problems']}")

        st, d = get(q(NO_KING))
        check(d.get("valid") is False and any("数量" in p for p in d.get("problems", [])),
              f"缺将应判为不合法，实得 {d}")
        print(f"  ✓ 缺将局面被拦下：{d['problems']}")

        st, d = get(q("这不是一个FEN"))
        check(st == 200 and d.get("ok") and d.get("valid") is False,
              f"解析不了的 FEN 也要干净返回，实得 {st} {d}")
        print("  ✓ FEN 解析失败时不抛 500，而是返回可读的问题")

        print("【合法着法】/api/legal")
        st, d = get("/api/legal?fen=" + urllib.parse.quote(START))
        check(st == 200 and d.get("ok") and len(d.get("moves", [])) == 44,
              f"开局应给出 44 步，实得 {st} {len(d.get('moves', []))}")
        check(d.get("valid") is True, "合法局面应带 valid=true")
        print(f"  ✓ 开局 44 步，valid=true")

        st, d = get("/api/legal?fen=" + urllib.parse.quote(KING_OUT))
        check(st == 200 and d.get("ok") is False and d.get("moves") == [],
              f"非法局面应返回 ok=false + 空着法，实得 {st} {str(d)[:120]}")
        check(d.get("problems"), "非法局面应带上具体问题清单")
        print(f"  ✓ 非法局面不再 500，而是 ok=false：{d.get('error')}")

        st, d = get("/api/legal?fen=" + urllib.parse.quote("乱码乱码"))
        check(st == 200 and d.get("ok") is False and "error" in d,
              f"FEN 坏了也应干净返回，实得 {st} {str(d)[:120]}")
        print("  ✓ FEN 损坏时 /api/legal 也不炸")

        print("【首页】")
        with urllib.request.urlopen(BASE + "/", timeout=20) as r:
            html = r.read().decode("utf-8")
        check(r.status == 200 and "编辑局面" in html, "首页应含编辑局面的按钮")
        check("棋子盒" in html, "首页应含棋子盒")
        print(f"  ✓ 首页 {len(html)} 字节，编辑按钮与棋子盒都在")
    finally:
        srv.shutdown()
        srv.server_close()

    print("")
    if fails:
        print(f"结果：{len(fails)} 项失败")
        return 1
    print("结果：全部通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
