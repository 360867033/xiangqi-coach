"""
本地象棋教练服务

启动： python server.py   然后浏览器打开 http://127.0.0.1:8760

只监听 127.0.0.1，不对外网开放。
"""
import json
import os
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from xq import rules as R
from xq import coach as C
from xq import review as RV
from xq import cloud as CL
from xq import engine as E
from xq import zh as ZH

WEB_DIR = os.path.join(HERE, "web")
CFG = C.load_cfg()

# ------------------------------------------------------------------ 缓存
_facts_cache = {}
_cache_lock = threading.Lock()
_cache_order = []


def cache_key(fen, played, depth, multipv):
    return f"{fen}|{played or ''}|{depth}|{multipv}"


def cache_put(k, v):
    with _cache_lock:
        _facts_cache[k] = v
        _cache_order.append(k)
        while len(_cache_order) > 40:
            old = _cache_order.pop(0)
            _facts_cache.pop(old, None)


def cache_get(k):
    with _cache_lock:
        return _facts_cache.get(k)


# ------------------------------------------------------------------ 复盘任务
class Job:
    def __init__(self):
        self.id = str(int(time.time() * 1000))
        self.done = 0
        self.total = 0
        self.note = "准备中"
        self.result = None
        self.error = None
        self.finished = False


_jobs = {}
_jobs_lock = threading.Lock()


def start_review(text, depth, start_fen=None):
    job = Job()
    with _jobs_lock:
        _jobs[job.id] = job

    def worker():
        try:
            board, red = R.parse_fen(start_fen or R.START_FEN)
            tokens = RV.parse_move_input(text)
            job.note = "识别着法中"
            # 先按红先识别；如果识别率差，再试黑先（兼容从黑方开始的棋谱）
            best = None
            for first_red in (red, not red):
                bb, rr = R.parse_fen(start_fen or R.START_FEN)
                u, c, un = RV.resolve_moves(bb, first_red, tokens)
                cand = (len(u), -len(un), u, c, un)
                if best is None or cand[:2] > best[:2]:
                    best = cand
            _, _, ucis, chinese, unknown = best
            if not ucis:
                job.error = "没有识别出任何合法着法，请检查输入"
                job.finished = True
                return
            job.note = f"识别到 {len(ucis)} 手，开始逐手分析"

            def prog(done, total, note):
                job.done, job.total, job.note = done, total, note

            res = RV.review(ucis, depth=depth, cfg=CFG, progress=prog)
            res["input_chinese"] = chinese
            res["unknown_tokens"] = unknown
            res["start_fen"] = start_fen or R.START_FEN
            res["text"] = RV.review_to_text(res)
            job.result = res
        except Exception as e:
            job.error = f"{type(e).__name__}: {e}"
            traceback.print_exc()
        finally:
            job.finished = True
            job.note = "完成"

    threading.Thread(target=worker, daemon=True).start()
    return job


# ------------------------------------------------------------------ HTTP
class Handler(SimpleHTTPRequestHandler):
    server_version = "XiangqiCoach/0.1"

    def log_message(self, fmt, *a):
        if "--verbose" in sys.argv:
            sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % a))

    # -------------------------------------------------- 工具
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def _sse_start(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

    def _sse_send(self, kind, text):
        if not text:
            return
        payload = json.dumps({"t": kind, "d": text}, ensure_ascii=False)
        self.wfile.write(b"data: " + payload.encode("utf-8") + b"\n\n")
        self.wfile.flush()

    # -------------------------------------------------- GET
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        try:
            if path in ("/", "/index.html"):
                return self._serve_file(os.path.join(WEB_DIR, "index.html"))
            if path.startswith("/static/"):
                rel = path[len("/static/"):]
                safe = os.path.normpath(rel).replace("\\", "/")
                if safe.startswith(".."):
                    return self._json({"error": "bad path"}, 400)
                return self._serve_file(os.path.join(WEB_DIR, safe))
            if path == "/api/config":
                return self._json({
                    "ok": True,
                    "model": CFG.get("model"),
                    "engine": os.path.basename(CFG.get("engine_path", "")),
                    "analyze_depth": CFG.get("analyze_depth", 18),
                    "review_depth": CFG.get("review_depth", 14),
                    "multipv": CFG.get("multipv", 4),
                    "cloud": CFG.get("cloud_enabled", True),
                    "start_fen": R.START_FEN,
                })
            if path == "/api/validate":
                # 局面合法性校验：给前端的编辑模式用（边编辑边提示哪里还不合法）
                fen = qs.get("fen", [""])[0]
                try:
                    board, red = R.parse_fen(fen)
                except Exception as e:
                    return self._json({"ok": True, "valid": False,
                                       "problems": [f"FEN 解析失败：{e}"]})
                ok, probs = R.validate(board, red)
                return self._json({"ok": True, "valid": ok, "problems": probs})
            if path == "/api/legal":
                fen = qs.get("fen", [""])[0]
                out = []
                try:
                    board, red = R.parse_fen(fen)
                    ok, probs = R.validate(board, red)
                    if not ok:
                        # 非法局面直接说清楚，别让前端拿到一堆乱七八遭的着法
                        return self._json({"ok": False, "valid": False, "moves": [],
                                           "problems": probs,
                                           "error": "；".join(probs)})
                    for mv in R.legal_moves(board, red):
                        out.append({"uci": R.move_uid(mv),
                                    "from": [mv[0], mv[1]], "to": [mv[2], mv[3]],
                                    "chinese": R.move_to_chinese(board, mv),
                                    "capture": R.is_capture(board, mv)})
                except Exception as e:
                    return self._json({"ok": False, "valid": False, "moves": [],
                                       "error": f"{type(e).__name__}: {e}"})
                return self._json({"ok": True, "valid": True, "moves": out})
            if path == "/api/job":
                jid = qs.get("id", [""])[0]
                with _jobs_lock:
                    job = _jobs.get(jid)
                if not job:
                    return self._json({"error": "任务不存在"}, 404)
                out = {"ok": True, "done": job.done, "total": job.total,
                       "note": job.note, "finished": job.finished,
                       "error": job.error}
                if job.result is not None:
                    out["result"] = job.result
                return self._json(out)
            if path == "/api/health":
                eng = E.get_engine(CFG)
                return self._json({"ok": True, "engine_alive": eng.proc.poll() is None,
                                   "engine": os.path.basename(eng.exe)})
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            traceback.print_exc()
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def _serve_file(self, p):
        if not os.path.exists(p):
            return self._json({"error": "file not found"}, 404)
        ext = os.path.splitext(p)[1].lower()
        ctype = {".html": "text/html; charset=utf-8",
                 ".js": "application/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8",
                 ".svg": "image/svg+xml", ".png": "image/png"}.get(ext,
                                                                    "application/octet-stream")
        with open(p, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # -------------------------------------------------- POST
    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            data = self._read_json()
        except Exception as e:
            return self._json({"error": f"请求体解析失败：{e}"}, 400)
        try:
            if path == "/api/analyze":
                return self._handle_analyze(data)
            if path == "/api/explain":
                return self._handle_explain(data)
            if path == "/api/ask":
                return self._handle_ask(data)
            if path == "/api/review":
                return self._handle_review(data)
            if path == "/api/review_report":
                return self._handle_review_report(data)
            if path == "/api/cloud":
                fen = data.get("fen", "")
                info = CL.lookup(fen, timeout=CFG.get("cloud_timeout", 6))
                return self._json({"ok": True, **info})
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            traceback.print_exc()
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    # -------------------------------------------------- 各接口
    def _handle_analyze(self, data):
        fen = (data.get("fen") or "").strip()
        played = (data.get("played") or "").strip() or None
        depth = int(data.get("depth") or CFG.get("analyze_depth", 18))
        multipv = int(data.get("multipv") or CFG.get("multipv", 4))
        if not fen:
            return self._json({"error": "缺少 fen"}, 400)
        k = cache_key(fen, played, depth, multipv)
        hit = cache_get(k)
        if hit is None:
            t0 = time.time()
            hit = C.build_facts(fen, played_move=played, depth=depth,
                                multipv=multipv,
                                want_cloud=CFG.get("cloud_enabled", True),
                                cfg=CFG)
            hit["elapsed"] = round(time.time() - t0, 2)
            if "error" not in hit:
                cache_put(k, hit)
        return self._json({"ok": "error" not in hit, "facts": hit})

    def _facts_for(self, data):
        fen = (data.get("fen") or "").strip()
        played = (data.get("played") or "").strip() or None
        depth = int(data.get("depth") or CFG.get("analyze_depth", 18))
        multipv = int(data.get("multipv") or CFG.get("multipv", 4))
        k = cache_key(fen, played, depth, multipv)
        facts = cache_get(k)
        if facts is None:
            facts = C.build_facts(fen, played_move=played, depth=depth,
                                  multipv=multipv,
                                  want_cloud=CFG.get("cloud_enabled", True), cfg=CFG)
            if "error" not in facts:
                cache_put(k, facts)
        return facts

    def _stream_llm(self, messages, temperature=0.4, effort_override=None,
                    fen=None):
        """把大模型的流式输出通过 SSE 转发给浏览器。

        传 fen 是为了过一层"坐标中文化"（xq/zh.py）：模型偶尔还是会写 a0/h2
        这种坐标，这里兜底翻成"红方九路车"。它看不见自己写的原话，观众看到的
        永远是中文。
        """
        # 正文与思考分开过滤：两条流交叉到达，共用一个缓冲区会把半截坐标串起来
        flt = ZH.CoordFilter(fen)
        flt_think = ZH.CoordFilter(fen)
        try:
            key = CFG.get("api_key") or ""
            base = (CFG.get("base_url") or "https://api.deepseek.com/v1").rstrip("/")
            model = CFG.get("model") or "deepseek-flash"
            import urllib.request
            body = {"model": model, "messages": messages,
                    "temperature": temperature, "stream": True}
            effort = effort_override if effort_override is not None \
                else CFG.get("reasoning_effort")
            if effort and effort != "default":
                body["reasoning_effort"] = effort
            req = urllib.request.Request(
                base + "/chat/completions",
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json",
                         "Authorization": "Bearer " + key})
            self._sse_start()
            with urllib.request.urlopen(req, timeout=300) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        obj = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    for ch in obj.get("choices", []):
                        delta = ch.get("delta") or {}
                        piece = delta.get("content")
                        if piece:
                            piece = flt.feed(piece)
                            if piece:
                                self._sse_send("delta", piece)
                        reason = delta.get("reasoning_content")
                        if reason:
                            reason = flt_think.feed(reason)
                            if reason:
                                self._sse_send("think", reason)
            # 过滤器尾部扣着的那一两个字符（可能是被切断的坐标）也要吐出去
            tail, tail_t = flt.flush(), flt_think.flush()
            if tail:
                self._sse_send("delta", tail)
            if tail_t:
                self._sse_send("think", tail_t)
            self._sse_send("done", "")
        except Exception as e:
            try:
                self._sse_start() if not self.wfile.closed else None
            except Exception:
                pass
            try:
                self._sse_send("error", f"{type(e).__name__}: {e}")
            except Exception:
                pass

    def _handle_explain(self, data):
        facts = self._facts_for(data)
        if "error" in facts:
            return self._json({"ok": False, "error": facts["error"]})
        msgs = [{"role": "system", "content": C.SYS_COACH},
                {"role": "user", "content": C.build_explain_prompt(facts)}]
        return self._stream_llm(msgs, effort_override=data.get("effort"),
                                fen=facts.get("fen"))

    def _handle_ask(self, data):
        facts = self._facts_for(data)
        if "error" in facts:
            return self._json({"ok": False, "error": facts["error"]})
        history = data.get("history") or []
        question = (data.get("question") or "").strip()
        if not question:
            return self._json({"ok": False, "error": "问题为空"})
        # 追问：用专用提示词（只答所问、不许写小节标题、不许复述局面），
        # 并把上一次的讲解带进上下文，模型才知道"这些我都说过了"。
        msgs = C.build_followup_messages(facts, question, history,
                                         prior=data.get("prior"))
        return self._stream_llm(msgs, effort_override=data.get("effort"),
                                fen=facts.get("fen"))

    def _handle_review(self, data):
        text = data.get("text") or ""
        depth = int(data.get("depth") or CFG.get("review_depth", 14))
        start_fen = data.get("start_fen") or None
        if not text.strip():
            return self._json({"error": "请输入棋谱", "ok": False})
        job = start_review(text, depth, start_fen)
        return self._json({"ok": True, "job_id": job.id})

    def _handle_review_report(self, data):
        jid = data.get("job_id")
        with _jobs_lock:
            job = _jobs.get(jid)
        if not job or not job.result:
            return self._json({"ok": False, "error": "任务未完成"})
        msgs = [{"role": "system", "content": RV.SYS_REVIEW},
                {"role": "user", "content": job.result["text"]}]
        return self._stream_llm(msgs, effort_override=data.get("effort"))


def _port_in_use(port, host="127.0.0.1"):
    """端口上已经有东西在监听？"""
    import socket
    s = socket.socket()
    s.settimeout(0.8)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def _open_browser(url):
    if os.environ.get("XQ_NO_BROWSER"):
        return
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass


def _set_console_title(text):
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW(text)
    except Exception:
        pass


def main():
    port = int(CFG.get("port", 8760))
    url = f"http://127.0.0.1:{port}"
    no_browser = "--no-browser" in sys.argv
    _set_console_title("象棋教练 · 皮卡鱼 + 云库 + DeepSeek")

    print("=" * 62)
    print("  象棋教练 · 皮卡鱼 + 云库 + DeepSeek")
    print("=" * 62)
    print(f"  引擎   : {os.path.basename(CFG.get('engine_path', '?'))}")
    print(f"  模型   : {CFG.get('model')}")
    print(f"  界面   : {url}")
    print("  停止   : 按 Ctrl+C")
    print("=" * 62)

    # 已经有一个实例在跑 → 不要再起第二个（会重复占内存、抢引擎），直接开界面
    if _port_in_use(port):
        print(f"  [提示] 端口 {port} 已在监听——象棋教练应该已经在运行了。")
        print(f"  正在打开界面：{url}")
        _open_browser(url)
        print("  （若浏览器没有自动打开，请手动访问上面的地址）")
        return 3

    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as e:
        print(f"  [错误] 无法绑定端口 {port}：{e}")
        return
    srv.daemon_threads = True

    # 预热引擎
    try:
        E.get_engine(CFG)
        print("  [OK] 引擎已就绪")
    except Exception as e:
        print(f"  [警告] 引擎启动失败：{e}")

    if not no_browser:
        print("  浏览器将自动打开…")
        threading.Timer(1.2, _open_browser, args=(url,)).start()

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        try:
            srv.server_close()
        except Exception:
            pass
        try:
            if E._engine:
                E._engine.quit()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main() or 0)
