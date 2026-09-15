"""端到端回归（自终止）：临时端口起一个真服务，跑 test_full.py 的全流程，跑完就关。

为什么不用外部已经跑着的服务：这样测试不依赖"用户此刻有没有开服务"，
也不会留下后台进程。用完即走。

用法： python tests/test_e2e_inproc.py
"""
import os
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import server as S  # noqa: E402

PORT = 8874
fails = []


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), S.Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"[临时服务] http://127.0.0.1:{PORT}（跑完自动关闭）")
    out = ""
    try:
        env = dict(os.environ, XQ_BASE=f"http://127.0.0.1:{PORT}",
                   PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        p = subprocess.run([sys.executable, "-u", os.path.join(HERE, "test_full.py")],
                           capture_output=True, env=env, timeout=1500)
        out = p.stdout.decode("utf-8", "replace")
        err = p.stderr.decode("utf-8", "replace")
        print(out)
        if p.returncode != 0:
            fails.append(f"test_full.py 退出码 {p.returncode}")
            print("--- stderr ---")
            print(err[-2000:])
    finally:
        srv.shutdown()
        srv.server_close()
        print("[临时服务] 已关闭")

    if "全部通过" not in out:
        fails.append("test_full.py 没有跑到最后（未见「全部通过」）")
    if "首字节" not in out:
        fails.append("讲解流式输出没有产生首字节统计")
    if "失着" not in out:
        fails.append("整盘复盘没有产出失着清单")

    print("")
    if fails:
        print("结果：" + "；".join(fails))
        return 1
    print("结果：端到端全部通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
