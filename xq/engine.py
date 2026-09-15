"""
皮卡鱼（Pikafish）UCI 引擎封装

提供的核心能力：
  analyze()          —— MultiPV 多线分析（候选着法 + 分数 + WDL + PV 主线）
  analyze_move()     —— 只分析「某一个着法」，得到它的真实评分与"被怎么惩罚"的应着线
"""
import os
import subprocess
import threading
import time

DEFAULT_ENGINE = r"D:\Pikafish\皮卡鱼-Pikafish\Pikafish-Windows-x86-64-universal.exe"


class EngineError(RuntimeError):
    pass


class Line:
    """一条候选着法（PV）"""

    def __init__(self):
        self.multipv = 1
        self.depth = 0
        self.score_cp = None
        self.mate = None
        self.wdl = None          # (win, draw, loss) 千分比，走子方视角
        self.pv = []
        self.seldepth = 0
        self.nodes = 0
        self.time_ms = 0

    def as_dict(self):
        return {
            "multipv": self.multipv, "depth": self.depth,
            "score_cp": self.score_cp, "mate": self.mate,
            "wdl": self.wdl, "pv": self.pv,
            "seldepth": self.seldepth, "nodes": self.nodes, "time_ms": self.time_ms,
        }


class Pikafish:
    def __init__(self, exe=DEFAULT_ENGINE, nnue=None, threads=8, hash_mb=512,
                 show_wdl=True):
        if not os.path.exists(exe):
            raise EngineError(f"找不到引擎：{exe}")
        self.exe = exe
        self.nnue = nnue
        self.threads = threads
        self.hash_mb = hash_mb
        self.show_wdl = show_wdl
        self.proc = None
        self._lock = threading.Lock()
        self._start()

    # ------------------------------------------------------------ 进程
    def _start(self):
        cwd = self.nnue or os.path.dirname(self.exe)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen(
            [self.exe], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace", bufsize=1, cwd=os.path.dirname(self.exe),
            creationflags=flags,
        )
        self._send("uci")
        self._read_until("uciok", 30)
        if self.nnue and os.path.exists(self.nnue):
            self._send(f'setoption name EvalFile value {self.nnue}')
        self._send(f"setoption name Threads value {self.threads}")
        self._send(f"setoption name Hash value {self.hash_mb}")
        if self.show_wdl:
            self._send("setoption name UCI_ShowWDL value true")
        self._send("isready")
        self._read_until("readyok", 60)

    def _send(self, cmd):
        if self.proc is None or self.proc.poll() is not None:
            raise EngineError("引擎进程已退出")
        self.proc.stdin.write(cmd + "\n")
        self.proc.stdin.flush()

    def _read_until(self, token, timeout):
        t0 = time.time()
        buf = []
        while time.time() - t0 < timeout:
            line = self.proc.stdout.readline()
            if not line:
                raise EngineError("引擎输出中断")
            line = line.rstrip("\n")
            buf.append(line)
            if token in line:
                return buf
        raise EngineError(f"等待 {token} 超时")

    # ------------------------------------------------------------ 解析
    @staticmethod
    def _parse_info(line):
        tk = line.split()
        d = {}
        i = 0
        while i < len(tk):
            t = tk[i]
            if t in ("depth", "seldepth", "multipv", "nodes", "nps", "hashfull",
                     "tbhits", "time", "cp"):
                try:
                    d[t] = int(tk[i + 1])
                except (ValueError, IndexError):
                    pass
                i += 2
            elif t == "score":
                if i + 2 < len(tk):
                    if tk[i + 1] == "cp":
                        d["score_cp"] = int(tk[i + 2])
                    elif tk[i + 1] == "mate":
                        d["mate"] = int(tk[i + 2])
                i += 3
            elif t == "wdl":
                try:
                    d["wdl"] = (int(tk[i + 1]), int(tk[i + 2]), int(tk[i + 3]))
                except (ValueError, IndexError):
                    pass
                i += 4
            elif t == "pv":
                d["pv"] = tk[i + 1:]
                i = len(tk)
            else:
                i += 1
        return d

    def _collect(self, timeout, collect_multi=True):
        """读到 bestmove，返回 (lines, bestmove, ponder)。

        带看门狗：超时后主动发 stop 让引擎收手，避免永久阻塞。"""
        lines = {}
        best, ponder = None, None
        done = threading.Event()

        def watchdog():
            if not done.wait(timeout):
                try:
                    self._send("stop")
                except Exception:
                    pass

        wd = threading.Thread(target=watchdog, daemon=True)
        wd.start()
        deadline = time.time() + timeout + 10
        try:
            while time.time() < deadline:
                line = self.proc.stdout.readline()
                if not line:
                    raise EngineError("引擎输出中断")
                line = line.rstrip("\n")
                if line.startswith("info ") and " pv " in line:
                    d = self._parse_info(line)
                    if "pv" in d and d.get("depth", 0) >= 1:
                        k = d.get("multipv", 1) if collect_multi else 1
                        prev = lines.get(k)
                        if prev is None or d.get("depth", 0) >= prev.depth:
                            ln = Line()
                            ln.multipv = k
                            ln.depth = d.get("depth", 0)
                            ln.seldepth = d.get("seldepth", 0)
                            ln.score_cp = d.get("score_cp")
                            ln.mate = d.get("mate")
                            ln.wdl = d.get("wdl")
                            ln.pv = d["pv"]
                            ln.nodes = d.get("nodes", 0)
                            ln.time_ms = d.get("time", 0)
                            lines[k] = ln
                elif line.startswith("bestmove"):
                    tk = line.split()
                    best = tk[1] if len(tk) > 1 else None
                    if len(tk) > 3 and tk[2] == "ponder":
                        ponder = tk[3]
                    break
        finally:
            done.set()
        if best is None:
            raise EngineError("引擎未返回 bestmove（超时）")
        return [lines[k] for k in sorted(lines)], best, ponder

    # ------------------------------------------------------------ 分析
    def _prepare(self, fen, multipv):
        self._send("stop")
        self._send(f"setoption name MultiPV value {multipv}")
        self._send("position fen " + fen)

    def _go_command(self, depth, movetime, nodes, hard_cap=None, searchmoves=None):
        """组装 go 命令。

        注意：UCI 协议规定 searchmoves 必须是 go 命令的【最后一项】，
        它后面的所有 token 都会被引擎当成着法吃掉。放错位置会导致
        depth/movetime 失效，引擎陷入无限搜索。
        """
        go = "go"
        if nodes:
            go += f" nodes {int(nodes)}"
        elif movetime:
            go += f" movetime {int(movetime)}"
        else:
            go += f" depth {int(depth)}"
            if hard_cap:
                go += f" movetime {int(hard_cap)}"
        if searchmoves:
            go += " searchmoves " + " ".join(searchmoves)
        return go

    def analyze(self, fen, depth=18, movetime=None, multipv=4, nodes=None,
                timeout=180, hard_cap=15000):
        """多线分析当前局面。返回 dict"""
        with self._lock:
            self._prepare(fen, multipv)
            self._send(self._go_command(depth, movetime, nodes, hard_cap))
            lines, best, ponder = self._collect(timeout)
        return {"fen": fen, "lines": [l.as_dict() for l in lines],
                "bestmove": best, "ponder": ponder}

    def analyze_move(self, fen, move_uci, depth=18, movetime=None,
                     nodes=None, timeout=180, hard_cap=15000):
        """只分析指定着法（searchmoves 限定根节点），得到它的评分与对手最佳应着"""
        with self._lock:
            self._prepare(fen, 1)
            self._send(self._go_command(depth, movetime, nodes, hard_cap,
                                        searchmoves=[move_uci]))
            lines, best, ponder = self._collect(timeout, collect_multi=False)
        ln = lines[0].as_dict() if lines else {}
        return {"fen": fen, "move": move_uci, "line": ln}

    def quit(self):
        try:
            self._send("quit")
        except Exception:
            pass
        try:
            if self.proc:
                self.proc.terminate()
        except Exception:
            pass
        self.proc = None


_engine = None
_engine_lock = threading.Lock()


def get_engine(cfg=None):
    """全局单例，避免反复启动引擎"""
    global _engine
    with _engine_lock:
        if _engine is None or _engine.proc is None or _engine.proc.poll() is not None:
            cfg = cfg or {}
            _engine = Pikafish(
                exe=cfg.get("engine_path", DEFAULT_ENGINE),
                threads=cfg.get("threads", 8),
                hash_mb=cfg.get("hash_mb", 512),
            )
        return _engine
