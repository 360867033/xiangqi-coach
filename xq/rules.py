"""
中国象棋规则引擎（纯 stdlib）

坐标约定（与 Pikafish / UCI 一致）：
  file 0..8  = a..i，从红方视角的【左边】到右边
               红方纵线号 = 9 - file （所以 a=九路, i=一路）
               黑方纵线号 = file + 1 （所以 a=1路,  i=9路）
  rank 0..9  = 红方底线(0) 到 黑方底线(9)
  UCI 走法串形如 "h2e2"（炮二平五）、"b9c7"（马8进7）
  内部坐标 = (rank, file)，格子索引 = rank * 9 + file
"""

RED_NAMES = {'R': '车', 'N': '马', 'B': '相', 'A': '仕', 'K': '帅', 'C': '炮', 'P': '兵'}
BLACK_NAMES = {'R': '车', 'N': '马', 'B': '象', 'A': '士', 'K': '将', 'C': '炮', 'P': '卒'}
CN_DIGITS = "一二三四五六七八九"
START_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"

# 子力价值（用于讲解中的粗略物质对比）
PIECE_VALUE = {'R': 900, 'N': 400, 'C': 450, 'A': 200, 'B': 200, 'P': 100, 'K': 0}


# ---------------------------------------------------------------- FEN
def parse_fen(fen):
    """返回 (board, red_to_move)"""
    parts = fen.strip().split()
    rows = parts[0].split('/')
    if len(rows) != 10:
        raise ValueError("FEN 应该是 10 行")
    board = [''] * 90
    for i, row in enumerate(rows):
        rank = 9 - i
        f = 0
        for ch in row:
            if ch.isdigit():
                f += int(ch)
            else:
                if f > 8:
                    raise ValueError("FEN 某一行棋子过多")
                board[rank * 9 + f] = ch
                f += 1
        if f != 9:
            raise ValueError(f"FEN 第 {i + 1} 行宽度不是 9（得到 {f}）")
    side = parts[1].lower() if len(parts) > 1 else 'w'
    return board, side.startswith('w')


def to_fen(board, red_to_move):
    rows = []
    for rank in range(9, -1, -1):
        row, empty = '', 0
        for f in range(9):
            c = board[rank * 9 + f]
            if c:
                if empty:
                    row += str(empty)
                    empty = 0
                row += c
            else:
                empty += 1
        if empty:
            row += str(empty)
        rows.append(row)
    return '/'.join(rows) + (' w' if red_to_move else ' b') + ' - - 0 1'


def side_to_move_fen(board, red_to_move):
    return to_fen(board, red_to_move)


# ---------------------------------------------------------------- 基本工具
def is_red(c):
    return c.isupper()


def find_king(board, red):
    return board.index('K' if red else 'k')


def kings_facing(board):
    try:
        rk = board.index('K')
        bk = board.index('k')
    except ValueError:
        return False
    rr, rf = divmod(rk, 9)
    br, bf = divmod(bk, 9)
    if rf != bf:
        return False
    for r in range(min(rr, br) + 1, max(rr, br)):
        if board[r * 9 + rf]:
            return False
    return True


def in_check(board, red):
    """red 方是否被将军（含将帅照面）"""
    if kings_facing(board):
        return True
    try:
        kpos = find_king(board, red)
    except ValueError:
        return True
    kr, kf = divmod(kpos, 9)
    for r in range(10):
        for f in range(9):
            c = board[r * 9 + f]
            if c and is_red(c) != red:
                for (_, _, tr, tf) in gen_pseudo(board, r, f):
                    if tr == kr and tf == kf:
                        return True
    return False


# ---------------------------------------------------------------- 着法生成
def gen_pseudo(board, r, f):
    """生成伪合法着法（未过滤自将），返回 (fr, ff, tr, tf) 列表"""
    c = board[r * 9 + f]
    if not c:
        return []
    red = is_red(c)
    t = c.upper()
    out = []

    def add(nr, nf):
        if 0 <= nr < 10 and 0 <= nf < 9:
            tgt = board[nr * 9 + nf]
            if not tgt or is_red(tgt) != red:
                out.append((r, f, nr, nf))

    if t == 'K':
        for dr, df in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nf = r + dr, f + df
            if 3 <= nf <= 5 and (0 <= nr <= 2 if red else 7 <= nr <= 9):
                add(nr, nf)
    elif t == 'A':
        for dr, df in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            nr, nf = r + dr, f + df
            if 3 <= nf <= 5 and (0 <= nr <= 2 if red else 7 <= nr <= 9):
                add(nr, nf)
    elif t == 'B':
        for dr, df in ((2, 2), (2, -2), (-2, 2), (-2, -2)):
            nr, nf = r + dr, f + df
            if not (0 <= nr < 10 and 0 <= nf < 9):
                continue
            if red and nr > 4:      # 相不过河
                continue
            if (not red) and nr < 5:
                continue
            if board[(r + dr // 2) * 9 + (f + df // 2)]:   # 塞象眼
                continue
            add(nr, nf)
    elif t == 'N':
        for dr, df, br, bf in ((2, 1, 1, 0), (2, -1, 1, 0), (-2, 1, -1, 0), (-2, -1, -1, 0),
                               (1, 2, 0, 1), (-1, 2, 0, 1), (1, -2, 0, -1), (-1, -2, 0, -1)):
            nr, nf = r + dr, f + df
            if not (0 <= nr < 10 and 0 <= nf < 9):
                continue
            if board[(r + br) * 9 + (f + bf)]:   # 蹩马腿
                continue
            add(nr, nf)
    elif t == 'R':
        for dr, df in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nf = r + dr, f + df
            while 0 <= nr < 10 and 0 <= nf < 9:
                tgt = board[nr * 9 + nf]
                if not tgt:
                    out.append((r, f, nr, nf))
                else:
                    if is_red(tgt) != red:
                        out.append((r, f, nr, nf))
                    break
                nr, nf = nr + dr, nf + df
    elif t == 'C':
        for dr, df in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nf = r + dr, f + df
            while 0 <= nr < 10 and 0 <= nf < 9 and not board[nr * 9 + nf]:
                out.append((r, f, nr, nf))
                nr, nf = nr + dr, nf + df
            if 0 <= nr < 10 and 0 <= nf < 9:      # 越过炮架
                nr, nf = nr + dr, nf + df
                while 0 <= nr < 10 and 0 <= nf < 9:
                    tgt = board[nr * 9 + nf]
                    if tgt:
                        if is_red(tgt) != red:
                            out.append((r, f, nr, nf))
                        break
                    nr, nf = nr + dr, nf + df
    elif t == 'P':
        fwd = 1 if red else -1
        add(r + fwd, f)
        crossed = (r >= 5) if red else (r <= 4)
        if crossed:
            add(r, f - 1)
            add(r, f + 1)
    return out


def apply_move(board, mv):
    fr, ff, tr, tf = mv
    nb = list(board)
    nb[tr * 9 + tf] = nb[fr * 9 + ff]
    nb[fr * 9 + ff] = ''
    return nb


def legal_moves(board, red):
    out = []
    for r in range(10):
        for f in range(9):
            c = board[r * 9 + f]
            if c and is_red(c) == red:
                for mv in gen_pseudo(board, r, f):
                    if not in_check(apply_move(board, mv), red):
                        out.append(mv)
    return out


def is_capture(board, mv):
    return bool(board[mv[2] * 9 + mv[3]])


def move_uid(mv):
    return "".join(chr(97 + mv[i]) + str(mv[i + 1]) for i in (0, 2)) if False else \
        chr(97 + mv[1]) + str(mv[0]) + chr(97 + mv[3]) + str(mv[2])


def uid_to_move(u):
    """'h2e2' -> (2,7,2,4)"""
    u = u.strip().lower()
    if len(u) != 4:
        raise ValueError(f"非法走法串: {u}")
    return (int(u[1]), ord(u[0]) - 97, int(u[3]), ord(u[2]) - 97)


# ---------------------------------------------------------------- 中文记谱
def _file_num(f, red):
    return (9 - f) if red else (f + 1)


def _num_str(n, red):
    return CN_DIGITS[n - 1] if red else str(n)


def move_to_chinese(board, mv):
    """把走法翻译成中文记谱，如 炮二平五 / 马8进7 / 前车进三"""
    fr, ff, tr, tf = mv
    c = board[fr * 9 + ff]
    if not c:
        return "??"
    red = is_red(c)
    t = c.upper()
    name = (RED_NAMES if red else BLACK_NAMES)[t]

    # 同一纵线多个同种子 -> 用 前/中/后
    same = sorted(r for r in range(10) if board[r * 9 + ff] == c)
    prefix = ''
    if len(same) > 1:
        idx = same.index(fr)
        if red:
            order = list(reversed(same))       # 红方：rank 大的算「前」
        else:
            order = same                        # 黑方：rank 小的算「前」
        pos = order.index(fr)
        if len(order) == 2:
            prefix = ['前', '后'][pos]
        elif len(order) == 3:
            prefix = ['前', '中', '后'][pos]
        else:
            prefix = str(pos + 1)
        start = prefix + name
    else:
        start = name + _num_str(_file_num(ff, red), red)

    if tr == fr:
        return f"{start}平{_num_str(_file_num(tf, red), red)}"

    forward = (tr > fr) if red else (tr < fr)
    act = '进' if forward else '退'
    if t in ('R', 'C', 'P', 'K'):
        target = _num_str(abs(tr - fr), red)
    else:                                   # 马、相/象、仕/士：报目标纵线
        target = _num_str(_file_num(tf, red), red)
    return f"{start}{act}{target}"


def describe_line(board, uci_moves, red_to_move=None, limit=12):
    """把一串 UCI 走法翻译成中文记谱，并返回 (记谱列表, 最终局面, 最终子力差)"""
    if red_to_move is None:
        red_to_move = True
    b = list(board)
    red = red_to_move
    out = []
    for u in uci_moves[:limit]:
        try:
            mv = uid_to_move(u)
        except ValueError:
            break
        if not b[mv[0] * 9 + mv[1]]:
            break
        out.append(move_to_chinese(b, mv))
        b = apply_move(b, mv)
        red = not red
    return out, b, material_balance(b)


# ---------------------------------------------------------------- 局面描述
def material_balance(board):
    """返回 (红方物质分, 黑方物质分, 差值[正=红优])"""
    r = s = 0
    for c in board:
        if not c:
            continue
        v = PIECE_VALUE[c.upper()]
        if is_red(c):
            r += v
        else:
            s += v
    return r, s, r - s


def material_summary(board):
    """文字化子力清单"""
    def side(red):
        cnt = {}
        for c in board:
            if c and is_red(c) == red:
                cnt[c.upper()] = cnt.get(c.upper(), 0) + 1
        names = RED_NAMES if red else BLACK_NAMES
        order = ['R', 'C', 'N', 'P', 'A', 'B', 'K']
        return '、'.join(f"{names[k]}{cnt[k]}" for k in order if cnt.get(k))
    return f"红方：{side(True)}；黑方：{side(False)}"


def board_text(board):
    """ASCII 棋盘（rank 9 在上，红方在下），供 LLM 阅读。

    列标只给**红黑双方的纵线号**，不给 a..i。
    原因：以前这里写了 a..i，大模型就照抄成 "红车在 a0" 这种坐标——棋友看不懂。
    连坐标的影子都不给，它才没得抄（配合 coach.SYS_COACH 的铁律 3）。
    """
    lines = []
    for rank in range(9, -1, -1):
        cells = []
        for f in range(9):
            c = board[rank * 9 + f]
            if not c:
                cells.append('·')
            else:
                cells.append((RED_NAMES if is_red(c) else BLACK_NAMES)[c.upper()])
        lines.append(f"r{rank} | " + ' '.join(cells))
    lines.append("      红方路数 " + ' '.join(CN_DIGITS[8 - f] for f in range(9)))
    lines.append("      黑方路数 " + ' '.join(str(f + 1) for f in range(9)))
    lines.append("（上=黑方底线 r9，下=红方底线 r0。红方路数从红方右手边数起，"
                 "黑方路数从黑方右手边数起）")
    return "\n".join(lines)


def piece_positions(board):
    """逐子列出中文位置，给大模型当"标准说法"照着抄。

    输出形如：
      红方 — 九路车（第1条横线）、一路车（第1条横线）、二路炮（第3条横线）…
      黑方 — 1路车（第1条横线）、9路车（第1条横线）、1路卒（第4条横线）…
    横线一律「从自己底线数起」，避免歧义。
    """
    order = ['车', '炮', '马', '兵', '卒', '仕', '士', '相', '象', '帅', '将']
    lines = []
    for red in (True, False):
        names = RED_NAMES if red else BLACK_NAMES
        items = {}
        for rank in range(10):
            for f in range(9):
                c = board[rank * 9 + f]
                if not c or is_red(c) != red:
                    continue
                nm = names[c.upper()]
                lane = _file_num(f, red)
                lane_txt = (CN_DIGITS[lane - 1] if red else str(lane)) + "路"
                line_no = (rank + 1) if red else (10 - rank)
                items.setdefault(nm, []).append((lane, f"{lane_txt}{nm}（第{line_no}条横线）"))
        seq = []
        for nm in order:
            if nm in items:
                seq.extend(t for _, t in sorted(items[nm]))
        lines.append(("红方 — " if red else "黑方 — ") + "、".join(seq))
    return "\n".join(lines)


def evaluate_band(cp, red_perspective=True):
    """把分数翻译成人话"""
    v = cp if red_perspective else -cp
    a = abs(v)
    if a < 40:
        return "均势"
    if a < 120:
        return "略占上风"
    if a < 300:
        return "明显优势"
    if a < 800:
        return "大优"
    return "胜势"


def score_str(cp_or_mate):
    """(score_cp, mate) -> 字符串"""
    cp, mate = cp_or_mate
    if mate is not None:
        return f"杀棋 第{abs(mate)}手" + ("（红方将杀）" if mate > 0 else "（黑方将杀）")
    return f"{cp / 100:+.2f}"


# ---------------------------------------------------------------- 局面校验
MAX_COUNT = {'K': 1, 'A': 2, 'B': 2, 'R': 2, 'N': 2, 'C': 2, 'P': 5}
_CN = {'K': '帅/将', 'A': '仕/士', 'B': '相/象', 'R': '车', 'N': '马', 'C': '炮', 'P': '兵/卒'}


def validate(board, red_to_move=None):
    """检查局面是否合法/合理。返回 (是否合法, [问题列表])

    象棋引擎在「非法局面」上可能出现病态行为（搜索不停、评分失真），
    所以入口处必须先拦一道。"""
    problems = []
    for red, label in ((True, '红方'), (False, '黑方')):
        cnt = {}
        for c in board:
            if c and is_red(c) == red:
                cnt[c.upper()] = cnt.get(c.upper(), 0) + 1
        for k, limit in MAX_COUNT.items():
            n = cnt.get(k, 0)
            if k == 'K':
                if n != 1:
                    problems.append(f"{label}的{_CN[k]}数量为 {n}，应为 1 个")
            elif n > limit:
                problems.append(f"{label}的{_CN[k]}有 {n} 个，最多 {limit} 个")
        # 将/帅必须在九宫内
        king = 'K' if red else 'k'
        if board.count(king) == 1:
            kr, kf = divmod(board.index(king), 9)
            if not (3 <= kf <= 5 and (0 <= kr <= 2 if red else 7 <= kr <= 9)):
                problems.append(f"{label}的{_CN['K']}不在九宫之内")
    if kings_facing(board):
        problems.append("将帅照面（这种局面不可能出现在正常对局中）")
    if red_to_move is not None:
        # 轮到谁走，谁的对方就不应该正被将军（= 上一手非法）
        if in_check(board, not red_to_move):
            problems.append("不该走棋的一方正被将军，说明该局面不合法（上一手是非法着法）")
    return (len(problems) == 0), problems


def fen_problems(fen):
    """对外入口：FEN 字符串 -> (board, red_to_move, 问题列表)"""
    board, red = parse_fen(fen)
    ok, probs = validate(board, red)
    return board, red, ([] if ok else probs)
