/* 对弈模式的前端逻辑测试
   ------------------------------------------------------------------
   覆盖：
     1. 棋盘底盘共用（教练 / 对弈两块棋盘画的是同一套网格）
     2. xy() 的翻转是"可换挡"的（对弈有自己的 play.flip）
     3. ★状态隔离：对弈和教练是两盘棋，谁走子都不许动到对方
     4. ★悔棋：退到"又轮到人走"，且不许把 AI 的先手棋退掉（会造成死锁）
     5. ★棋谱导出格式：JS 生成 → Python 的复盘解析器读回（真跨语言对拍）
     6. 读取对弈棋局：局面 / 着法 / 最后一步 / 轮次都能搬进教练模式
     7. 静态约束：对弈深度与讲解深度是两套、自动计算只算不讲、设置项与后端白名单一致
*/
const fs = require('fs');
const os = require('os');
const path = require('path');
const {execFileSync} = require('child_process');

const ROOT = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'web', 'index.html'), 'utf-8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const START = 'rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1';

let fails = 0;
function check(cond, msg){
  if (cond) console.log('  ✓ ' + msg);
  else { console.log('  ✗ ' + msg); fails++; }
}

/* ================= DOM 桩（要够整段脚本跑完顶层） ================= */
const elStub = () => ({
  innerHTML: '', textContent: '', style: {}, value: '', disabled: false,
  dataset: {}, scrollTop: 0, scrollHeight: 0, checked: false,
  classList: {toggle(){}, add(){}, remove(){}},
  addEventListener(){}, appendChild(){}, removeChild(){},
  insertAdjacentHTML(){}, setAttribute(){}, getAttribute(){ return null; },
  querySelector: () => null, querySelectorAll: () => [],
  getBoundingClientRect: () => ({left: 0, top: 0, width: 484, height: 520}),
  viewBox: {baseVal: {width: 484, height: 520}},
  onclick: null, oncontextmenu: null,
});
const store = {};
const getEl = id => (store[id] || (store[id] = elStub()));
const mem = {};
const localStorageStub = {
  getItem: k => (k in mem ? mem[k] : null),
  setItem: (k, v) => { mem[k] = String(v); },
  removeItem: k => { delete mem[k]; },
};
const winObj = {START_FEN: START, START_RED: true};

// 屏蔽 init（它要联网）
const patched = script.replace(/\(async function init\(\)[\s\S]*\}\)\(\);\s*$/,
                               '/* init skipped */');
const api = new Function(
  'document', 'window', 'navigator', 'fetch', 'alert', 'prompt', 'localStorage',
  patched + `
;return {state, play, xy, boardBaseSvg, playReset, playDoMove, playUndo, playText,
         playFen, humanSide, isHumanTurn, loadPlayGame, fenToBoard, drawPlayBoard,
         playCheckStuck, renderPlayMoveList, renderPlayInfo, updateLoadPlayBtn,
         setPlayEditMode, startPlayFromEdit, onPlaySquare, onEditClick, onTrayClick,
         onBoardContext, trayPieces, undoEdit, updatePlayEditUI, playMaybeAi,
         playHasGame, playStartRed, fenMoverRed, setTurn, editClearBoard, editResetBoard,
         setEditMode, edObj, edAny, hand: () => ({piece: handPiece, from: handFrom}),
         freeHand: () => { handPiece = null; handFrom = null; }};`
)(
  {getElementById: getEl, querySelector: () => elStub(), querySelectorAll: () => [],
   createElement: () => elStub(), addEventListener(){}, body: elStub()},
  winObj, {clipboard: {writeText: async () => {}}}, async () => ({ok: true, json: async () => ({})}),
  () => {}, () => null, localStorageStub
);

/* 一个方便的小工具：把对弈棋盘摆成指定走法序列的样子 */
function setup(asHumanRed, moves){
  api.playReset();
  api.play.aiSide = asHumanRed ? 'black' : 'red';
  (moves || []).forEach(m => api.playDoMove(m.from, m.to, m.uci, m.cn));
}

const WALK = [
  {from: [2,7], to: [2,4], uci: 'h2e2', cn: '炮二平五'},
  // 黑方 8 路炮在 file 7（黑方路数从黑方右手边数起），平到 5 路 = file 4
  {from: [7,7], to: [7,4], uci: 'h7e7', cn: '炮8平5'},
  {from: [0,7], to: [2,6], uci: 'h0g2', cn: '马二进三'},
];

/* ================= 1. 底盘共用 ================= */
console.log('【1】棋盘底盘：教练和对弈画的是同一套网格');
check(/function boardBaseSvg\(flip\)/.test(html), '抽出了 boardBaseSvg(flip) 公用底盘');
check(/s \+= boardBaseSvg\(state\.flip\);/.test(html), '教练棋盘调用公用底盘');
check(/s \+= boardBaseSvg\(play\.flip\);/.test(html), '★对弈棋盘调用同一个底盘（不会画出两块不一样的棋盘）');
{
  // 翻转互为镜像：flip=true 的左上角 == flip=false 的右上角
  const a = api.xy(0, 0, true), b = api.xy(9, 8, false);
  check(a[0] === b[0] && a[1] === b[1],
        `xy 支持按参数翻转（真 ${JSON.stringify(a)} vs 假 ${JSON.stringify(b)}）`);
  const c = api.xy(0, 0), d = api.xy(0, 0, false);
  check(c[0] === d[0] && c[1] === d[1],
        '不传 flip 时沿用 state.flip（老调用点不用改）');
}

/* ================= 2. 状态隔离 ================= */
console.log('【2】状态隔离：对弈与教练是两盘棋 ★核心');
{
  api.state.board = api.fenToBoard(START);
  api.state.red = true;
  api.state.history = [{fenBefore: START, uci: 'x', from: [0,0], to: [0,0], chinese: '教练的棋'}];
  const coachBoard = api.state.board.join(',');
  const coachHist = JSON.stringify(api.state.history);

  setup(true, [WALK[0]]);                       // 对弈里走一手

  check(api.state.board.join(',') === coachBoard,
        '★在对弈里走子，教练模式的棋盘一动不动');
  check(JSON.stringify(api.state.history) === coachHist,
        '★教练模式的着法记录也没被写进对弈的手');
  check(api.play.board[2*9+4] === 'C' && !api.play.board[2*9+7],
        '对弈棋盘上炮已从中路走过（原格清空）');
  check(api.play.red === false, '走完一手后轮到黑方');
  check(api.play.history.length === 1 && api.play.history[0].uci === 'h2e2',
        '对弈自己的着法记录写了这一手');
  check(api.play.history[0].chinese === '炮二平五', '记录里存了中文记谱（导出/复盘要用）');
  // 反过来：教练动，对弈不动
  const playBoard = api.play.board.join(',');
  api.state.board = api.fenToBoard(START);
  api.state.board[0] = '';
  check(api.play.board.join(',') === playBoard, '教练模式改棋盘时，对弈棋盘同样不受影响');
}

/* ================= 3. 悔棋 ================= */
console.log('【3】悔棋：退到"又轮到人走"，且不许退掉 AI 的先手棋');
{
  // 人执红（AI 执黑）：人走一手 → 悔棋 → 回开局
  setup(true, [WALK[0]]);
  api.playUndo();
  check(api.play.history.length === 0 && api.play.red === true,
        `人执红：悔棋回到开局、轮到红方（手数 ${api.play.history.length}）`);
  check(api.play.board[2*9+7] === 'C' && api.play.board[2*9+4] === '',
        '悔棋后棋盘上的炮也回到了原位');

  // AI 执红（人执黑）：AI 先手一手 + 人一手 → 悔棋 → 只剩 AI 那手、轮到人
  setup(false, [WALK[0], WALK[1]]);
  api.playUndo();
  check(api.play.history.length === 1,
        `★AI 先手时悔棋只退掉"我那一手"（剩 ${api.play.history.length} 手）`);
  check(api.play.red === false, '悔棋后轮到黑方（人）');

  // 人还没走过棋 → 不许悔（否则退掉 AI 先手后轮到 AI 走，人点棋盘会点不动）
  setup(false, [WALK[0]]);
  const before = api.play.history.length;
  api.playUndo();
  check(api.play.history.length === before && api.play.red === false,
        '★人还没走过棋时悔棋不会退掉 AI 的先手棋（护住"轮到人走"，不会死锁）');

  // AI 思考中禁止悔棋
  setup(true, [WALK[0]]);
  api.play.busy = true;
  api.playUndo();
  check(api.play.history.length === 1, 'AI 思考中悔棋会被挡下（否则状态会串台）');
  api.play.busy = false;
}

/* ================= 4. 棋谱导出 ↔ 复盘解析（跨语言对拍） ================= */
console.log('【4】棋谱导出：JS 生成 → Python 复盘解析器读回 ★跨语言对拍');
{
  setup(true, WALK);
  const txt = api.playText();
  check(/^1\. 炮二平五 炮8平5$/m.test(txt), '棋谱按"1. 红 黑"成对排版');
  check(/^2\. 马二进三$/m.test(txt), '奇数手的最后一手单独成行');
  check(!/[#*]/.test(txt) && !/注释|对弈|深度/.test(txt),
        '★棋谱里没有任何注释行（复盘是按空格切词认着法的，有注释就会报"没识别出合法着法"）');

  const tmp = path.join(os.tmpdir(), 'xq_play_test_' + process.pid + '.txt');
  fs.writeFileSync(tmp, txt, 'utf-8');
  const PY = process.env.PY_EXE || 'python';
  const pyCode = `
import sys, json
sys.path.insert(0, ${JSON.stringify(ROOT)})
from xq import review as RV, rules as R
txt = open(${JSON.stringify(tmp)}, encoding='utf-8').read()
tokens = RV.parse_move_input(txt)
board, red = R.parse_fen(R.START_FEN)
ucis, chinese, unknown = RV.resolve_moves(board, red, tokens)
print(json.dumps({'ucis': ucis, 'unknown': unknown}, ensure_ascii=False))
`;
  let got = null, err = null;
  try{
    const out = execFileSync(PY, ['-c', pyCode], {encoding: 'utf-8', cwd: ROOT});
    got = JSON.parse(out.trim().split('\n').filter(Boolean).pop());
  }catch(e){ err = e; }
  check(!err, '能调起 Python 复盘解析器' + (err ? '：' + String(err.message).slice(0, 120) : ''));
  if (got){
    const want = WALK.map(m => m.uci);
    check(JSON.stringify(got.ucis) === JSON.stringify(want),
          `★导出的棋谱被复盘完整识别：${got.ucis.join(' ')}`);
    check((got.unknown || []).length === 0,
          '★没有被认成"看不懂"的 token（有的话复盘会直接失败）');
  }
  try{ fs.unlinkSync(tmp); }catch(e){}
}

/* ================= 5. 读取对弈棋局 → 教练模式 ================= */
console.log('【5】教练模式「读取对弈棋局」');
{
  setup(true, WALK);
  api.state.board = api.fenToBoard(START);      // 先把教练那边弄成"另一盘棋"
  api.state.red = true;
  api.state.history = [];
  api.state.lastMove = null;
  api.state.facts = {candidates: [], best: null, played: null, cloud: null};
  api.state.factsKey = 'OLD|x';

  api.loadPlayGame();

  check(api.state.history.length === 3,
        `读取后教练模式的着法记录 = 对弈的手数（${api.state.history.length}）`);
  check(api.state.board.join(',') === api.play.board.join(','),
        '★读取后教练棋盘与对弈棋盘完全一致');
  check(api.state.red === api.play.red, '轮次也一并读过来');
  check(api.state.lastMove && api.state.lastMove.uci === 'h0g2',
        '最后一步被读进来（这样「讲解我这一步」立刻能用）');
  check(api.state.facts === null && api.state.factsKey === null,
        '★读取会清掉上一盘棋的分析结果（否则表格里挂的是别的局面的候选着法）');
  // 深拷贝：两边不共享坐标数组
  api.state.history[0].from[0] = 99;
  check(api.play.history[0].from[0] === 2,
        '★着法记录是深拷贝（改教练那边不会串到对弈的坐标）');
}

/* ================= 5b. 对弈模式的「编辑局面」（编辑的第二个目标） ================= */
console.log('【5b】对弈模式「编辑局面」：摆好一个局面再开局 ★核心');
{
  const dims = /const\s+CELL\s*=\s*([\d.]+)\s*,\s*PAD\s*=\s*([\d.]+)/.exec(html);
  const CELL = +dims[1], PAD = +dims[2];
  // 把格位换成鼠标像素（flip=false：列自左向右、行自下向上）
  const evAt = (r, f) => ({clientX: PAD + f * CELL, clientY: PAD + (9 - r) * CELL});

  api.playReset();
  api.play.aiSide = 'black';              // 我执红 → 摆红先局面时 AI 不会抢着走
  api.state.board = api.fenToBoard(START);
  api.state.red = true;
  api.state.editing = false;
  api.state.history = [{fenBefore: START, uci: 'zz', from: [0,0], to: [0,1], chinese: '教练自己的棋'}];
  const coachBoard = api.state.board.join(','), coachMoves = api.state.history.length;

  api.setPlayEditMode(true);
  check(api.play.editing === true, '对弈模式进入编辑态（play.editing）');
  check(api.state.editing === false, '教练模式的编辑态没被一起打开');
  check(api.edAny() === true && api.edObj() === api.play,
        '★edObj() 认得出"此刻编辑的是对弈那盘棋"');

  // 点棋盘 = 摆子（不是走子）
  api.onPlaySquare(0, 0);                 // 选中红车
  const h1 = api.hand();
  check(h1.piece === 'R' && !!h1.from && h1.from[0] === 0 && h1.from[1] === 0,
        `编辑态下点棋子是"选中"（手上拿着 ${h1.piece}）`);
  api.onPlaySquare(4, 0);                 // 放到 (4,0) —— rank 4 是空行
  check(api.play.board[4*9+0] === 'R' && api.play.board[0] === '',
        '★点空位就把子摆下去了（不会被当成走子）');
  check(api.play.history.length === 0 && api.play.started === false,
        '摆过之后着法记录清空、退回"还没开局"（摆出来的局面不算走出来的）');

  // ★最要紧的一条：编辑对弈棋盘，不许碰教练那盘棋
  check(api.state.board.join(',') === coachBoard,
        '★★编辑对弈棋盘完全没动教练棋盘（两盘棋互不干扰）');
  check(api.state.history.length === coachMoves && api.state.editing === false,
        '★★也没动教练的着法记录和编辑态');

  // 右键移出 → 进棋子盒（棋子盒算的是对弈棋盘的账）
  api.onBoardContext(Object.assign(evAt(4, 0), {preventDefault(){}}));
  check(api.play.board[4*9+0] === '', '右键把棋子移出了对弈棋盘');
  check(api.trayPieces().red.includes('R'), '★移出的红车进了棋子盒（盒子按对弈的盘面算）');

  api.undoEdit();
  check(api.play.board[4*9+0] === 'R', '撤销把"移出"退回来了');
  check(api.state.board.join(',') === coachBoard, '撤销也只作用在对弈那盘棋上');

  api.editClearBoard();
  const t = api.trayPieces();
  check(t.red.length === 16 && t.black.length === 16,
        `清空后 32 枚全在棋子盒（红 ${t.red.length} + 黑 ${t.black.length}）`);
  check(api.state.board.join(',') === coachBoard, '★清空对弈棋盘没把教练棋盘一起清掉');

  // 摆一个三子残局：红帅 + 黑将 + 红车，轮到红方
  api.editClearBoard();
  api.onTrayClick('K'); api.onPlaySquare(0, 4);
  api.onTrayClick('k'); api.onPlaySquare(9, 4);
  api.onTrayClick('R'); api.onPlaySquare(2, 4);
  check(api.play.board.filter(Boolean).length === 3, '摆出三子残局（帅 / 将 / 车）');

  // 摆局面期间 AI 一步都不许走：playAiMove 会把 busy 同步置 true，拿它当探针
  api.play.aiSide = 'red'; api.play.red = true; api.play.started = true;
  api.playMaybeAi().catch(() => {});
  check(api.play.busy === false && api.play.history.length === 0,
        '★摆局面期间 AI 不走子（否则你还在摆、它已经动了）');

  // 互斥：两块棋盘共用一枚"手上子"，进了对弈的编辑，教练那边必须自动退出
  api.setPlayEditMode(false);
  api.setEditMode(true);
  check(api.state.editing === true, '先让教练模式进编辑');
  api.setPlayEditMode(true);
  check(api.play.editing === true && api.state.editing === false,
        '★进对弈的编辑会自动退出教练的编辑（两边同时编辑会互相偷子）');
  api.play.aiSide = 'black';                      // 改回人执红，开局后 AI 不会抢手
  api.setTurn(true);                              // 该红方走
  api.startPlayFromEdit();
  check(api.play.editing === false, '开局后自动退出编辑');
  check(api.play.started === true && api.play.history.length === 0, '开局后进入对局状态');
  check(api.play.startFen === api.playFen(),
        `★这一局的起点记成了摆出来的局面（${String(api.play.startFen).split(' ')[0]}）`);
  check(api.play.startFen !== START, '★起点不是标准开局 —— 复盘必须知道这件事');
  check(api.playStartRed() === true && api.fenMoverRed(START) === true,
        '起点轮到红方时按红先编号');
  check(api.fenMoverRed('rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR b - - 0 1') === false,
        '★fenMoverRed 认得出"轮到黑方"（摆出来的残局可能是黑先，编号要跟着变）');

  // 没走子、但摆过局面 → 教练模式也读得走（摆残局直接拿去讲解正是用法之一）
  check(api.playHasGame() === true, '★摆过局面（还没走子）也算"有棋可读"');
  api.loadPlayGame();
  check(api.state.board.filter(Boolean).length === 3,
        '★没走子的残局也能被教练模式读取（3 个子）');
  check(api.state.history.length === 0 && api.state.lastMove === null,
        '读取残局：着法记录为空、没有"上一手"（讲解按钮会跟着禁用）');
}

/* ================= 6. 静态约束 ================= */
console.log('【6】静态约束（防止后面的改动把这几条碰掉）');
{
  check(/id="playBoardHost"/.test(html) && /id="boardHost"/.test(html),
        '两块棋盘各有自己的宿主（playBoardHost / boardHost）');
  // 对弈深度走 play.depth，不能顺手用配置里的 analyze_depth
  check(/jpost\('\/api\/bestmove', \{fen: playFen\(\), depth: play\.depth\}\)/.test(html),
        '★AI 走子用 play.depth（对弈深度），不是讲解深度');
  check(!/bestmove[\s\S]{0,120}analyze_depth/.test(html),
        '★对弈请求里不许出现 analyze_depth（两个深度必须独立）');
  check(/play\.depth = cfg\.play_depth \|\| 12/.test(html),
        '启动时对弈深度取自 config 的 play_depth');
  // 自动计算：必须只算不讲
  check(/function autoCalcOn\(\)/.test(html) && /function runAutoCalc\(\)/.test(html),
        '有「自动计算」的开关判断与执行函数');
  check(/analyze\(false, false\)\.catch\(\(\) => \{\}\);/.test(html),
        '★自动计算调的是 analyze(false, false)（只算不讲，不叫大模型）');
  check(/if \(autoCalcOn\(\)\) runAutoCalc\(\);/.test(html),
        '走子之后触发自动计算');
  check(/id="autoCalc"/.test(html), 'HTML 里有「自动计算」复选框');
  check(/state\.analyzeBusy \|\| state\.preview \|\| state\.editing/.test(html),
        '自动计算会避开"正在算 / 预演中 / 编辑中"三种状态（别把引擎排成一队）');
  // 设置项必须和后端白名单对得上
  const srv = fs.readFileSync(path.join(ROOT, 'server.py'), 'utf-8');
  const spec = srv.match(/SETTINGS_SPEC = \{([\s\S]*?)\n\}/);
  check(!!spec, 'server.py 里有 SETTINGS_SPEC 白名单');
  if (spec){
    const keys = [...spec[1].matchAll(/"([a-z_]+)":\s*\(/g)].map(m => m[1]);
    check(keys.includes('analyze_depth') && keys.includes('play_depth'),
          '★白名单同时含讲解深度和对弈深度（设置界面这两个必须能存）');
    check(!keys.includes('api_key') && !keys.includes('base_url') && !keys.includes('engine_path'),
          '★白名单里没有 api_key / base_url / engine_path（不给网页开后门改凭据和引擎）');
    const ids = ['setAnalyzeDepth', 'setPlayDepth', 'setReviewDepth', 'setMultipv', 'setEffort', 'setCloud'];
    check(ids.every(i => new RegExp(`id="${i}"`).test(html)),
          '设置界面 6 个字段都在 HTML 里');
    check(/post\('\/api\/settings'/.test(html) || /jpost\('\/api\/settings'/.test(html),
          '保存设置走 /api/settings');
  }

  /* 「编辑局面」：同一套逻辑挂两个目标 —— 各复制一份迟早会摆出两种手感 */
  check(/function edObj\(\)/.test(html) && /function edIds\(\)/.test(html),
        '★编辑逻辑抽成"可换目标"的通用实现（edObj / edIds），不是复制一份');
  check(!/function onPlayEditClick/.test(html),
        '★没有给对弈模式另写一套编辑点击（复制就是下一堆 bug 的温床）');
  check(/if \(play\.editing\) return onEditClick\(r, f\);/.test(html),
        '★对弈棋盘在编辑态下点棋盘 = 摆子（不是走子）');
  check(/if \(play\.editing \|\| !play\.started \|\| play\.over \|\| play\.busy\) return;/.test(html),
        '★摆局面期间 AI 不走子（否则你还在摆、它已经动了）');
  check(/if \(state\.editing\) setEditMode\(false\);/.test(html),
        '★进对弈的编辑会先退出教练的编辑（两块棋盘共用一枚手上子，不能同时编辑）');
  check(/id="pHandGhost"/.test(html) && /id="handGhost"/.test(html) &&
        /id="pHoverMark"/.test(html) && /id="hoverMark"/.test(html),
        '★手上子 / 悬停提示各用各的 id（同名的话 getElementById 只会拿到教练那块）');
  check(/id="ptray"/.test(html) && /id="ptrayRed"/.test(html) && /id="ptrayBlack"/.test(html),
        '对弈模式有自己的棋子盒');
  check(/id="btnPlayEdit"/.test(html) && /id="btnPlayStart"/.test(html),
        '对弈模式有「编辑局面」和「用这个局面开局」两个按钮');
  check(/reviewStartFen/.test(html) && /start_fen/.test(html),
        '★送去复盘会带上这一局的起点局面（从残局开局的棋，按标准开局算会整盘全错）');
}

console.log('');
if (fails){
  console.log(`结果：${fails} 项失败`);
  process.exit(1);
}
console.log('结果：全部通过 ✓');
