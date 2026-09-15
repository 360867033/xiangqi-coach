"""
把大模型输出里的「字母+数字」坐标（a0、h2、b7 这种）改写成中文说法。

为什么要单独做一层：
  棋盘内部（FEN / UCI）用的就是 a0..i9 这套坐标，材料里自然也带着它，
  于是大模型讲棋时会顺手照抄——对只懂中文记谱的棋友来说就是天书。
  提示词已经明令禁止（见 coach.SYS_COACH），但模型偶尔仍会漏，
  所以在流式输出上再加一道兜底翻译：**它偷偷写坐标，观众也只会看到中文**。

两种改写：
  1. 单点   a0      -> 红方九路车（该格有子时带上棋子名）
                    -> 红方九路（黑方1路）  （空格时只报位置）
  2. 两点   a0→h0   -> 车九平二（能当成一步合法着法时直接给中文记谱）
                    -> 红方九路车→红方一路车（转不出记谱就分别翻译）
"""
import re

from . import rules as R

# 坐标：一个字母 a-i + 一个数字 0-9。前后不许再挨着字母/数字，
# 否则会误伤 FEN（如 "1c5c1" 里的 c5）、英文单词或 "A1B" 这种编号。
_SINGLE = re.compile(r"(?<![A-Za-z0-9])([a-iA-I])(\d)(?![A-Za-z0-9])")
# 两点式：坐标 + 连接符（箭头/横线/到/至）+ 坐标
_PAIR = re.compile(
    r"(?<![A-Za-z0-9])([a-iA-I]\d)\s*(?:→|->|—|–|－|-|~|～|到|至)\s*([a-iA-I]\d)(?![A-Za-z0-9])")
# 结尾可能刚好把一个坐标切成两半（如 "...位于 a"），先扣住不发
_TAIL = re.compile(r"(?<![A-Za-z0-9])[a-iA-I]$")

_PIECE_CHARS = set("车马炮相象仕士兵卒帅将")


def _parse_cell(txt):
    """'h2' -> (rank=2, file=7)；越界返回 None"""
    if not txt or len(txt) != 2:
        return None
    f = ord(txt[0].lower()) - 97
    try:
        r = int(txt[1])
    except ValueError:
        return None
    if not (0 <= f <= 8 and 0 <= r <= 9):
        return None
    return r, f


def lane_text(file, red):
    """纵线号的中文说法：红方 a=九路..i=一路，黑方 a=1路..i=9路"""
    if red:
        return R.CN_DIGITS[8 - file] + "路"
    return str(file + 1) + "路"


def coord_to_cn(rank, file, board=None, with_piece=True):
    """坐标 -> 中文说法。

    board 给了就查该格：有子 -> "红方九路车"；空格 -> "红方九路（黑方1路）"。
    """
    red_lane = lane_text(file, True)
    blk_lane = lane_text(file, False)
    if board is not None:
        c = board[rank * 9 + file]
        if c:
            red = R.is_red(c)
            name = (R.RED_NAMES if red else R.BLACK_NAMES)[c.upper()]
            if not with_piece:
                return f"{'红方' if red else '黑方'}{lane_text(file, red)}"
            return f"{'红方' if red else '黑方'}{lane_text(file, red)}{name}"
    return f"红方{red_lane}（黑方{blk_lane}）"


class CoordFilter:
    """流式过滤器：把坐标翻成中文，且不把半截坐标漏出去。

    用法：
        f = CoordFilter(fen)
        for delta in stream:  yield f.feed(delta)
        yield f.flush()
    """

    def __init__(self, fen=None, board=None, red_to_move=None):
        self.board = board
        self.red = red_to_move
        if board is None and fen:
            try:
                self.board, self.red = R.parse_fen(fen)
            except Exception:
                self.board, self.red = None, None
        if self.red is None:
            self.red = True
        self.buf = ""
        self.count = 0            # 改写次数，便于测试与自检
        self._legal = {}

    # -------------------------------------------------- 内部
    def _legal_moves(self, red):
        """某个阵营的合法着法（缓存）。用来判断两点式能不能转成中文记谱"""
        if red not in self._legal:
            if self.board is None:
                self._legal[red] = []
            else:
                try:
                    self._legal[red] = R.legal_moves(list(self.board), red)
                except Exception:
                    self._legal[red] = []
        return self._legal[red]

    def _sub_pair(self, m):
        a, b = _parse_cell(m.group(1)), _parse_cell(m.group(2))
        if a is None or b is None or self.board is None:
            return None
        (r1, f1), (r2, f2) = a, b
        # 讲棋时说的可能是"黑方的车从 a9 开到 a7"，未必是当前走子方，
        # 所以两方都试一遍；只有确实是合法着法才给中文记谱，否则宁可分别翻译。
        for red in (self.red, not self.red):
            c = self.board[r1 * 9 + f1]
            if not c or R.is_red(c) != red:
                continue
            mv = (r1, f1, r2, f2)
            if mv in self._legal_moves(red):
                self.count += 1
                return R.move_to_chinese(self.board, mv)
        return None

    def _sub_single(self, m):
        cell = _parse_cell(m.group(0))
        if cell is None:
            return m.group(0)
        rank, file = cell
        s = m.string or ""
        before = s[:m.start()]
        after = s[m.end():m.end() + 2]
        # 后面已经跟了棋子名（"a0 车"），就别再补一个
        piece_follows = after.lstrip()[:1] in _PIECE_CHARS
        # 前面已经写了阵营（"红方的 a0 车"），就只报路数，避免"红方 红方九路车"
        side = re.search(r"(红方|黑方)的?\s*$", before)
        if piece_follows and side:
            self.count += 1
            return lane_text(file, side.group(1) == "红方")
        self.count += 1
        return coord_to_cn(rank, file, self.board, with_piece=not piece_follows)

    def _rewrite(self, text):
        text = _PAIR.sub(lambda m: self._sub_pair(m) or
                         _SINGLE.sub(self._sub_single, m.group(0)), text)
        return _SINGLE.sub(self._sub_single, text)

    # -------------------------------------------------- 对外
    def feed(self, text):
        """喂一块流式文本，返回可以安全发出的部分（可能少于输入）"""
        if not text:
            return ""
        self.buf += text
        out = self._rewrite(self.buf)
        m = _TAIL.search(out)
        if m:                      # 尾巴可能是被切断的坐标首字母
            self.buf = out[m.start():]
            return out[:m.start()]
        self.buf = ""
        return out

    def flush(self):
        """流结束时把最后一点残余吐干净"""
        out = self._rewrite(self.buf) if self.buf else ""
        self.buf = ""
        return out
