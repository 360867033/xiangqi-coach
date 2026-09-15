/**
 * 局面编辑功能的流程测试（Node 运行，无第三方依赖）
 *
 * 需求（照搬鲨鱼象棋的习惯）：
 *   1. 左键选中棋子，再左键放在鼠标位置
 *   2. 右键直接把棋子移出棋盘放到边上（棋子盒），可再左键选中棋子盒里的子放到棋盘
 *   3. 选中时点其他棋子 = 切换选中；点自身 = 取消选中
 *
 * 做法：从 index.html 里抽出编辑相关函数，套一个假 DOM 真跑一遍，
 *       断言棋盘数组、手上状态、棋子盒内容 —— 不看代码"像不像"，只看行为对不对。
 *
 * 用法： node tests/test_edit_mode.js
 * 退出码 0 = 全部通过
 */
const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'), 'utf8');

let fails = 0;
function check(ok, msg){
  if (!ok){ fails++; console.log('  ✗ ' + msg); }
  return ok;
}

/* ================= 1. 从 index.html 抽源码 ================= */
function grab(name){
  const re = new RegExp('function\\s+' + name + '\\s*\\([^)]*\\)\\s*\\{');
  const m = re.exec(src);
  if (!m) throw new Error('在 index.html 里找不到函数 ' + name);
  const prefix = /\basync\s*$/.test(src.slice(Math.max(0, m.index - 8), m.index)) ? 'async ' : '';
  let i = src.indexOf('{', m.index), depth = 0;
  for (let j = i; j < src.length; j++){
    if (src[j] === '{') depth++;
    else if (src[j] === '}'){ depth--; if (depth === 0) return prefix + src.slice(m.index, j + 1); }
  }
  throw new Error('函数 ' + name + ' 括号不闭合');
}
/* 抽单行箭头函数常量，如 const boardKey = b => ...; */
function grabConst(name){
  const m = new RegExp('const\\s+' + name + '\\s*=').exec(src);
  if (!m) throw new Error('找不到 const ' + name);
  const line = src.slice(m.index, src.indexOf('\n', m.index));
  const semi = line.indexOf(';');
  if (semi < 0) throw new Error('const ' + name + ' 似乎是多行，抽不出来');
  return line.slice(0, semi + 1);
}

const dims = /const\s+CELL\s*=\s*([\d.]+)\s*,\s*PAD\s*=\s*([\d.]+)/.exec(src);
const CELL = +dims[1], PAD = +dims[2];
const W = PAD * 2 + 8 * CELL, H = PAD * 2 + 9 * CELL;
const START = 'rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1';

/* ================= 2. 假 DOM ================= */
const els = {};
function mkClassList(){
  const s = new Set();
  return {
    toggle(c, f){ if (f === undefined){ s.has(c) ? s.delete(c) : s.add(c); } else if (f) s.add(c); else s.delete(c); },
    add: c => s.add(c), remove: c => s.delete(c), has: c => s.has(c),
  };
}
function el(id){
  if (!els[id]){
    els[id] = { id, innerHTML: '', textContent: '', style: {}, value: '', disabled: false,
      dataset: {}, classList: mkClassList(), scrollTop: 0, scrollHeight: 0,
      addEventListener(){}, appendChild(){}, insertAdjacentHTML(){},
      setAttribute(){}, getAttribute(){ return null; }, onclick: null };
  }
  return els[id];
}
const boardEl = {
  getBoundingClientRect: () => ({ left: 0, top: 0, width: W, height: H }),
  viewBox: { baseVal: { width: W, height: H } },
  addEventListener(){}, style: {},
};
global.document = {
  getElementById: el,
  querySelector: sel => (sel === 'svg.board' ? boardEl : el('q:' + sel)),
  querySelectorAll: () => [],
  createElement: () => el('tmp:' + Math.random()),
  addEventListener(){},
};
global.window = {};

/* ================= 3. 沙箱：把编辑函数装进来 ================= */
const body = `
function refreshAll(){ drawBoard(); updateEditUI(); }
async function jget(){ return { ok: true, valid: true, problems: [] }; }
function setHint(t){ ENV.hints.push(t); }
function escapeHtml(s){ return String(s); }
function onBoardClick(){}          // drawBoard 会绑定它，这里只需要存在
function onSquareClick(){}
/* 预演摆盘的行为另有 tests/test_preview.js 专测；这里只需要它存在
   （编辑模式/清记录时会调用它把预演收掉） */
function exitPreview(){ state.preview = null; }
/* 追问记录的收口函数（clearPlayRecord 会调用；行为由 test_preview.js 【12】专测），
   这里用真源码，免得写成空桩掩盖问题 */
${grab('clearAskHistory')}
${grab('bindAskHistory')}
let handPiece = null, handFrom = null;
let selected = null, legalCache = [];
let cursorVb = null, validateTimer = null;
let playValidateTimer = null;
/* 编辑会话现在能挂在两个目标上（教练的 state / 对弈的 play）。
   这个套件只测教练那一侧，所以 play 给个最小的空壳就行 ——
   但必须存在：edIsPlay() 一上来就要读 play.editing。 */
const play = {editing: false, history: [], board: [], red: true, lastMove: null,
              lastEval: null, over: false, result: '', selected: null, legalCache: [],
              started: false, startFen: '', flip: false,
              editDirty: false, editUndo: [], preEdit: null};
${grab('edIds')}
${grabConst('edIsPlay')}
${grab('edObj')}
${grab('edAny')}
${grabConst('edFlip')}
${grab('edDraw')}
${grab('edUI')}
${grabConst('edId')}
${grab('edById')}
${grab('edBoardSvg')}
${grab('edAfterChange')}
${grab('edValidate')}
${grabConst('edHint')}
${grabConst('isRed')}
${grabConst('curFen')}
${grabConst('boardKey')}
${grabConst('RED_CN')}
${grabConst('BLACK_CN')}
${grabConst('SET_COUNT')}
${grabConst('TYPE_ORDER')}
${grab('fenToBoard')}
${grab('boardToFen')}
${grab('xy')}
${grab('boardBaseSvg')}
${grab('squareFromPixels')}
${grab('eventToSquareIn')}
${grab('eventToSquare')}
${grab('pieceMarkup')}
${grab('describePiece')}
${grab('displayBoard')}
${grab('drawBoard')}
${grab('clearHand')}
${grab('editMutate')}
${grab('clearPlayRecord')}
${grab('onEditClick')}
${grab('placeHand')}
${grab('onBoardContext')}
${grab('trayPieces')}
${grab('renderTray')}
${grab('onTrayClick')}
${grab('positionGhost')}
${grab('onBoardMove')}
${grab('onBoardLeave')}
${grab('setEditMode')}
${grab('exitEditSilently')}
${grab('updateEditUI')}
${grab('setTurn')}
${grab('scheduleValidate')}
${grab('validateNow')}
${grab('undoEdit')}
return {
  fenToBoard, trayPieces, setTurn,
  click: onEditClick, ctx: onBoardContext, trayClick: onTrayClick,
  move: onBoardMove, leave: onBoardLeave, undo: undoEdit,
  mode: setEditMode, clear: () => { clearHand(); editMutate(() => { state.board = new Array(90).fill(''); }); drawBoard(); updateEditUI(); },
  hand: () => ({ piece: handPiece, from: handFrom }),
  board: () => state.board.slice(),
  reset: () => { clearHand(); state.board = fenToBoard(ENV.START); state.red = true; drawBoard(); updateEditUI(); },
};`;

const state = {
  board: [], red: true, history: [], lastMove: null, flip: false,
  facts: null, factsBusy: false, analyzeBusy: false,
  editing: false, editDirty: false, editUndo: [], preEdit: null,
  preview: null,          // 预演摆盘：这个测试里不用，但 drawBoard 会读它
};
const ENV = { hints: [], START };
const factory = new Function('CELL', 'PAD', 'W', 'H', 'state', 'ENV', body);
const api = factory(CELL, PAD, W, H, state, ENV);

/* 工具 */
const at = (b, r, f) => b[r * 9 + f];
const setAt = (r, f, v) => { ENV.STARTACTION = true; api.board(); state.board[r * 9 + f] = v; };
function pieceCounts(){
  const on = { red: 0, black: 0 };
  for (const c of state.board){ if (c) on[isRedChar(c) ? 'red' : 'black']++; }
  const t = api.trayPieces();
  return { on, off: { red: t.red.length, black: t.black.length }, tray: t };
}
function isRedChar(c){ return c === c.toUpperCase(); }
/* 鼠标事件：屏幕像素 == viewBox 坐标（假 DOM 里 scale=1） */
const evAt = (r, f) => ({ clientX: PAD + f * CELL, clientY: PAD + (9 - r) * CELL, preventDefault(){} });

/* ================= 4. 用例 ================= */
console.log('【守恒基线】开局 32 枚全在盘上、棋子盒是空的');
api.reset();
{
  const c = pieceCounts();
  check(c.on.red === 16 && c.on.black === 16, `盘上应 16+16 枚，实为 ${c.on.red}+${c.on.black}`);
  check(c.off.red === 0 && c.off.black === 0, '开局棋子盒应为空');
  console.log(`  ✓ 盘上 ${c.on.red} 红 + ${c.on.black} 黑，棋子盒 0 枚`);
}

console.log('【开关】没改动就退出 → 局面与着法记录原样还原');
{
  state.history = [{ fenBefore: ENV.START, uci: 'h2e2', from: [2, 7], to: [2, 4], chinese: '炮二平五' }];
  state.lastMove = { from: [2, 7], to: [2, 4], uci: 'h2e2', fenBefore: ENV.START, chinese: '炮二平五' };
  const key0 = state.board.join(',');
  api.mode(true);
  check(state.editing, '应进入编辑模式');
  check(el('tray').style.display === '', '进入编辑模式应显示棋子盒');
  api.mode(false);
  check(!state.editing, '应退出编辑模式');
  check(state.board.join(',') === key0, '没改动时退出应还原局面');
  check(state.history.length === 1 && state.lastMove && state.lastMove.uci === 'h2e2',
        '没改动时退出应还原着法记录');
  console.log('  ✓ 进出手续无副作用（局面/着法记录都回来了）');
  state.history = []; state.lastMove = null;
}

console.log('【规则1】左键选中 → 再左键点空位 → 棋子移过去');
api.reset(); api.mode(true);
{
  const before = api.board();
  api.click(2, 1);                       // 红炮在 (2,1)
  let h = api.hand();
  check(h.piece === 'C' && h.from && h.from[0] === 2 && h.from[1] === 1,
        `应选中红炮(2,1)，实为 ${JSON.stringify(h)}`);
  check(at(api.board(), 2, 1) === 'C', '选中时棋子还没离开原格（只是"拿在手上"）');
  api.click(5, 4);                       // 空格
  h = api.hand();
  const b = api.board();
  check(h.piece === null, '放下后手上应清空');
  check(at(b, 5, 4) === 'C', '炮应落到 (5,4)');
  check(at(b, 2, 1) === '', '原格 (2,1) 应清空');
  const c0 = before.filter(Boolean).length, c1 = b.filter(Boolean).length;
  check(c0 === c1, `棋子总数不应变化（${c0} → ${c1}）`);
  console.log('  ✓ 红炮 (2,1) → (5,4)，原格清空、总数不变');
}

console.log('【规则3】选中时点其他棋子 = 切换选中（旧子留在原处）');
{
  api.reset();
  api.click(0, 0);                       // 红车
  check(api.hand().piece === 'R' && api.hand().from[0] === 0, '先选中红车');
  api.click(0, 1);                       // 红马 → 切换选中
  const h = api.hand(), b = api.board();
  check(h.piece === 'N' && h.from[0] === 0 && h.from[1] === 1, '应改为选中红马');
  check(at(b, 0, 0) === 'R', '被切换掉的红车必须留在原处（不能丢）');
  check(at(b, 0, 1) === 'N', '红马仍在原处（没被搬走）');
  check(b.filter(Boolean).length === 32, '切换选中不该改变棋子数量');
  console.log('  ✓ 红车 → 红马：选中切换，两枚棋子都在原位');
}

console.log('【规则3】选中时点它自己 = 取消选中（棋子留在原处）');
{
  api.reset();
  api.click(0, 0);
  api.click(0, 0);
  const h = api.hand(), b = api.board();
  check(h.piece === null, '点自身应取消选中');
  check(at(b, 0, 0) === 'R', '取消选中后红车应留在原处');
  console.log('  ✓ 点自身取消选中，棋子没丢也没动');
}

console.log('【规则2】右键把棋子移出棋盘 → 出现在棋子盒里');
{
  api.reset();
  api.ctx(evAt(0, 0));                   // 右键红车
  const b = api.board(), c = pieceCounts();
  check(at(b, 0, 0) === '', '右键后该格应清空');
  check(c.tray.red.includes('R'), '棋子盒里应出现红车');
  check(c.on.red === 15, `盘上红方应剩 15 枚，实为 ${c.on.red}`);
  check(c.on.red + c.off.red === 16, '红方棋子必须守恒（盘上 + 盒中 = 16）');
  console.log('  ✓ 红车进棋子盒，红方 15 在盘 + 1 在盒');
  // 空格右键不报错、不产生变化
  const n0 = api.board().filter(Boolean).length;
  api.ctx(evAt(5, 5));
  check(api.board().filter(Boolean).length === n0, '对空格右键不应改变局面');
}

console.log('【规则2】左键点棋子盒里的子 → 再点空位 → 放上棋盘');
{
  const t0 = api.trayPieces().red.length;
  api.trayClick('R');
  let h = api.hand();
  check(h.piece === 'R' && h.from === null, '棋子盒点选后应"拿起来"，且不来自棋盘');
  check(api.trayPieces().red.length === t0, '拿在手上时盒子里的数量不变，放下才减');
  api.click(4, 4);
  const b = api.board();
  check(at(b, 4, 4) === 'R', '棋子应放到 (4,4)');
  check(api.trayPieces().red.length === t0 - 1, '放下后盒子里应少一枚红车');
  check(api.board().filter(Boolean).length === 32, '放回后总数应回到 32');
  console.log('  ✓ 棋子盒 → 棋盘：红车放回 (4,4)，总数回到 32');
}

console.log('【棋子盒再点一次】取消选中，不多子不少子');
{
  api.reset();
  api.ctx(evAt(2, 1)); api.ctx(evAt(2, 7));           // 两门红炮都移出棋盘
  check(api.trayPieces().red.filter(p => p === 'C').length === 2, '盒中应有两门红炮');
  api.trayClick('C');
  check(api.hand().piece === 'C' && api.hand().from === null, '应从盒中拿起一门红炮');
  api.trayClick('C');
  check(api.hand().piece === null, '再点同一枚应取消选中');
  check(api.trayPieces().red.filter(p => p === 'C').length === 2, '取消后两门红炮仍在盒中（没丢）');
  check(api.board().filter(Boolean).length === 30, `盘上应仍是 30 枚，实为 ${api.board().filter(Boolean).length}`);
  console.log('  ✓ 盒中点选/取消：棋子不增不减');
}

console.log('【盒里没有的子】拿不起来（防止凭空造子）');
{
  api.reset();                                        // 开局两门红炮都在盘上
  const n0 = api.board().filter(Boolean).length;
  api.trayClick('C');
  check(api.hand().piece === null, '盒里没有的子不该能拿起来');
  check(api.board().filter(Boolean).length === n0, '凭空拿子不应改变局面');
  console.log('  ✓ 盒中没有的棋子拿不起来（不会多出一枚）');
}

console.log('【棋子盒内容】标准子力 - 盘上子力（清空棋盘 = 32 枚全在盒里）');
{
  api.reset();
  api.clear();
  const b = api.board(), c = pieceCounts();
  check(b.every(x => x === ''), '清空后棋盘应为空');
  check(c.off.red === 16 && c.off.black === 16, `清空后棋子盒应 16+16 枚，实为 ${c.off.red}+${c.off.black}`);
  const redTiles = (el('trayRed').innerHTML.match(/class="tp/g) || []).length;
  const blkTiles = (el('trayBlack').innerHTML.match(/class="tp/g) || []).length;
  check(redTiles === 16 && blkTiles === 16, `渲染出来的棋子盒格子应为 16+16，实为 ${redTiles}+${blkTiles}`);
  console.log('  ✓ 清空棋盘：16 红 + 16 黑 全部进盒，界面渲染一致');
}

console.log('【不设限制】编辑模式允许摆出引擎认为"非法"的局面');
{
  api.reset();
  api.ctx(evAt(0, 4));                   // 右键把红帅移出
  api.ctx(evAt(9, 4));                   // 右键把黑将移出
  api.click(0, 0); api.click(5, 4);      // 用红车占位，确认九宫外照样能放
  api.reset();
  api.ctx(evAt(9, 4));                   // 移走黑将
  api.click(0, 4);                       // 拿起红帅
  api.click(9, 4);                       // 放到黑方底线（九宫之外）
  const b = api.board();
  check(at(b, 9, 4) === 'K', '红帅应能放到九宫之外（编辑模式不做合法性限制）');
  check(!b.includes('k'), '黑将此时已不在盘上，形成"缺帅/缺将"的非法局面');
  console.log('  ✓ 红帅可摆到九宫外、可摆出缺将局面（校验交给退出时提示）');
}

console.log('【清记录】编辑后旧着法记录必须清掉（否则"讲解我这一步"会张冠李戴）');
{
  api.reset();
  api.mode(false);                       // 先干净退出，保证下面进编辑时 editDirty=false
  state.history = [{ fenBefore: ENV.START, uci: 'h2e2', from: [2, 7], to: [2, 4], chinese: '炮二平五' }];
  state.lastMove = { from: [2, 7], to: [2, 4], uci: 'h2e2', fenBefore: ENV.START };
  api.mode(true);                        // 注意：只是进编辑模式，还不算改动
  check(state.history.length === 1, '仅进入编辑模式不应清空着法记录');
  api.click(0, 0); api.click(4, 4);      // 真的动了棋子
  check(state.editing && state.editDirty, '改过之后应标记为 dirty');
  check(state.history.length === 0 && state.lastMove === null, '改动后应清空着法记录与上一手');
  check(el('btnAnalyzeMove').disabled === true, '改动后「讲解我这一步」应被禁用');
  console.log('  ✓ 第一次真实改动才清记录，且只清一次（进编辑不误伤）');
}

console.log('【撤销编辑】一步一步退回去');
{
  const before = api.board().join(',');
  api.click(4, 4); api.click(5, 3);      // 把 (4,4) 的红车挪到 (5,3)
  const after = api.board().join(',');
  check(before !== after, '应真的产生了一次改动');
  api.undo();
  check(api.board().join(',') === before, '撤销后应回到上一次编辑前的局面');
  console.log('  ✓ 撤销编辑回到上一步');
}

console.log('【退出编辑】改过之后退出 → 保留局面，并提示校验');
{
  api.mode(false);
  check(!state.editing, '应退出编辑模式');
  check(el('tray').style.display === 'none', '退出后棋子盒应隐藏');
  check(state.board.join(',') !== ENV.START, '保留编辑后的局面（而不是还原）');
  console.log('  ✓ 改过就保留、没改就还原 —— 两条路径都符合预期');
}

console.log('【悬停预告】点下去会发生什么，鼠标移上去就说明白');
{
  api.reset(); api.mode(true);
  api.click(0, 0);                                   // 手上拿着红车
  api.move(evAt(5, 5));                              // 悬停空格
  check(el('hoverText').textContent === '放下', `空格上应提示"放下"，实为 ${el('hoverText').textContent}`);
  api.move(evAt(0, 1));                              // 悬停到红马上
  check(el('hoverText').textContent === '改为选中这个子',
        `有子的格应提示切换选中，实为 ${el('hoverText').textContent}`);
  api.move(evAt(0, 0));                              // 回到自己原格
  check(el('hoverText').textContent === '取消选中',
        `原格应提示取消选中，实为 ${el('hoverText').textContent}`);
  api.leave();
  check(el('hoverText').style.display === 'none', '鼠标离开棋盘后提示应收起');
  console.log('  ✓ 三态提示：放下 / 改为选中这个子 / 取消选中');
}

console.log('【手上子】重新绘制后仍然跟着鼠标（不会闪回原点）');
{
  api.reset(); api.mode(true);
  api.click(0, 0);
  api.move(evAt(3, 3));
  const html = el('boardHost').innerHTML;
  check(/id="handGhost"/.test(html), '手上子应有独立的覆盖层元素');
  check(/stroke-dasharray="5 4"/.test(html), '被拿起棋子的原格应画成虚线（提示它离开了原位）');
  check(/id="ovl"/.test(html), '编辑模式应有覆盖层（手上子 + 落点提示）');
  console.log('  ✓ 覆盖层里的手上子 + 原格虚线都在');
  api.leave();
  api.mode(false);
  check(!/id="handGhost"/.test(el('boardHost').innerHTML), '退出编辑后覆盖层应消失');
}

console.log('【棋子盒守恒】随机操作 200 次，棋子总数永远是 32');
{
  api.reset(); api.mode(true);
  let bad = 0, badMsg = '';
  for (let i = 0; i < 200; i++){
    const r = (i * 37) % 10, f = (i * 53) % 9;
    const act = i % 4;
    if (act === 0) api.click(r, f);
    else if (act === 1) api.ctx(evAt(r, f));
    else if (act === 2) api.trayClick('P');
    else api.trayClick('C');
    if (api.hand().piece) api.click((r + 3) % 10, (f + 4) % 9);
    const total = state.board.filter(Boolean).length + api.trayPieces().red.length + api.trayPieces().black.length;
    if (total !== 32){ bad++; if (!badMsg) badMsg = `第 ${i} 步总数变成了 ${total}`; }
    const t = api.trayPieces();
    for (const [side, arr] of [['红', t.red], ['黑', t.black]]){
      for (const k of ['R','N','C','B','A','K','P']){
        const c = arr.filter(p => p.toUpperCase() === k).length;
        if (c > 5) { bad++; if (!badMsg) badMsg = `${side}方 ${k} 在盒里出现 ${c} 枚`; }
      }
    }
  }
  check(bad === 0, `200 次随机编辑后棋子必须守恒：${badMsg}`);
  if (!bad) console.log('  ✓ 200 次随机操作：盘上 + 盒中恒等于 32，且每类不超标准');
}

console.log('【标记】生成的 SVG 必须标签闭合（拼字符串最容易漏 </g>）');
{
  function unbalanced(html){
    const stack = [], re = /<\/?([a-zA-Z][\w:-]*)((?:"[^"]*"|'[^']*'|[^>"'])*?)(\/?)>/g;
    let m;
    while ((m = re.exec(html))){
      const name = m[1], selfClose = m[3] === '/', closing = m[0].startsWith('</');
      if (closing){
        const top = stack.pop();
        if (top !== name) return `</${name}> 与 <${top}> 不匹配`;
      } else if (!selfClose) stack.push(name);
    }
    return stack.length ? '未闭合：' + stack.join(' > ') : null;
  }
  const cases = [];
  api.reset(); api.mode(true);
  cases.push(['编辑模式·空盘棋盘', el('boardHost').innerHTML]);
  cases.push(['棋子盒·红方', el('trayRed').innerHTML]);
  cases.push(['棋子盒·黑方', el('trayBlack').innerHTML]);
  api.click(0, 0); api.move(evAt(3, 3));
  cases.push(['编辑模式·手上有子', el('boardHost').innerHTML]);
  api.mode(false);
  cases.push(['对局模式棋盘', el('boardHost').innerHTML]);
  let bad = 0;
  for (const [name, html] of cases){
    const err = unbalanced(html);
    if (err){ bad++; console.log(`  · ${name}: ${err}`); }
  }
  check(bad === 0, `${cases.length} 段生成标记都应闭合，错 ${bad} 段`);
  if (!bad) console.log(`  ✓ ${cases.length} 段标记（棋盘/棋子盒/手持）全部闭合`);
}

console.log('【布局】棋子盒必须在棋盘右侧，不能堆在下面（否则要上下滚动页面）');
{
  // 1. 结构：.boardRow 里先棋盘后棋子盒，且两者是同一行的兄弟节点
  const iRow = src.indexOf('<div class="boardRow">');
  check(iRow >= 0, '棋盘外面应有一层 .boardRow 容器');
  const iBoard = src.indexOf('id="boardHost"', iRow);
  const iTray = src.indexOf('class="tray" id="tray"', iRow);
  check(iBoard > iRow && iTray > iBoard, '.boardRow 里应先棋盘、后棋子盒');
  // boardHost 与 tray 之间不能再有别的容器（否则棋子盒就被挪到棋盘卡片外了）
  const between = src.slice(iBoard, iTray);
  check((between.match(/<\/div>/g) || []).length === 1,
        '棋盘与棋子盒之间只应隔着 #boardHost 自己的闭合标签，不应插进别的容器');
  console.log('  ✓ 结构：.boardRow > [棋盘, 棋子盒]，同一行的左右关系');

  // 2. 样式：横向排列 + 棋盘列变宽以容纳棋子盒
  const rowCss = /\.boardRow\{([^}]*)\}/.exec(src);
  check(rowCss && /display:flex/.test(rowCss[1]), '.boardRow 必须是 flex 横排');
  const trayCss = /\.tray\{([^}]*)\}/.exec(src);
  check(trayCss && !/margin-top/.test(trayCss[1]),
        '.tray 不应再带 margin-top（那说明它还被当成棋盘下面的一块）');
  const wide = /#viewCoach\.editing[^{]*\{[^}]*grid-template-columns:\s*(\d+)px/.exec(src);
  check(!!wide, '编辑模式应有 #viewCoach.editing 加宽左栏的规则');
  // 对弈模式的「编辑局面」用的是同一个棋子盒，加宽规则和教练模式写在一起
  check(/#viewCoach\.editing\s*,\s*#viewPlay\.editing\s*\{[^}]*grid-template-columns/.test(src),
        '★对弈模式的编辑局面（#viewPlay.editing）也要加宽左栏 —— 它同样要摆棋子盒');
  if (wide){
    const need = W + 12 + +(/width:(\d+)px/.exec(trayCss[1]) || [])[1] + 28;
    check(+wide[1] >= need,
          `加宽后的左栏 ${wide[1]}px 应容得下 棋盘${W} + 间距12 + 棋子盒 + 卡片内边距28 = ${need}px`);
  }
  // 3. 棋子盒内部：4 列网格，最坏情况（16 枚全在盒里）不撑破面板
  const grid = /\.tray \.tgrid\{([^}]*)\}/.exec(src);
  const rep = grid && /repeat\((\d+),\s*(\d+)px\)/.exec(grid[1]);
  check(!!rep, '棋子盒应用固定列数的网格，避免被 16 枚棋子撑变形');
  if (rep && trayCss){
    const cols = +rep[1], cell = +rep[2];
    const avail = +(/width:(\d+)px/.exec(trayCss[1]) || [])[1] - 2 * 8 - 2;
    const used = cols * cell + (cols - 1) * 2;
    check(used <= avail, `${cols} 列 × ${cell}px = ${used}px 应放得下（面板可用 ${avail}px）`);
    check(Math.ceil(16 / cols) * (cell + 2) <= H,
          `最坏情况 16 枚 / ${cols} 列 = ${Math.ceil(16 / cols)} 行，应不超过棋盘高度 ${H}px`);
  }
  // 4. 窄屏回落：放不下时回到棋盘下方
  check(/@media\(max-width:740px\)[\s\S]{0,220}\.boardRow\{[^}]*flex-wrap:wrap/.test(src),
        '窄屏（≤740px）应允许棋盘盒回落到棋盘下方');
  console.log('  ✓ 样式：横排 + 左栏加宽 + 4 列网格 + 窄屏回落');

  // 5. 行为：只有编辑模式才加宽（对局模式不该白占宽度）
  api.reset(); api.mode(false);
  check(!el('viewCoach').classList.has('editing'), '非编辑模式不该加宽左栏');
  api.mode(true);
  check(el('viewCoach').classList.has('editing'), '进入编辑模式应给 #viewCoach 加 editing 类');
  api.mode(false);
  check(!el('viewCoach').classList.has('editing'), '退出编辑应摘掉 editing 类');
  console.log('  ✓ 行为：只有进编辑才加宽左栏，退出即还原');
}

console.log('【双栏独立滚动】整页不滚，左右两栏各自滚（看长讲解时棋盘留在视野里）');
{
  const css = /<style>([\s\S]*?)<\/style>/.exec(src)[1];
  const rule = sel => {
    const m = new RegExp(sel.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\{([^}]*)\\}').exec(css);
    return m ? m[1] : null;
  };
  // 1. 外壳：整页不滚
  check(/html\{\s*height:100%/.test(css), 'html 必须撑满高度（否则内层容器算不出剩余空间）');
  const body = rule('body');
  check(body && /display:flex/.test(body) && /flex-direction:column/.test(body),
        'body 应是纵向 flex（顶栏 + 内容区）');
  check(body && /overflow:hidden/.test(body), 'body 必须 overflow:hidden（整页不再滚动）');
  check(!/position:sticky/.test(rule('.topbar') || ''),
        '顶栏在宽屏下不该再用 sticky（flex 布局里它本来就固定）');
  console.log('  ✓ 外壳：body 纵向 flex + overflow:hidden，顶栏固定');

  // 2. 两栏容器：高度必须被钉死，否则子栏的 overflow-y:auto 永不触发
  const wrap = rule('.wrap');
  check(wrap && /flex:1 1 auto/.test(wrap), '.wrap 应吃掉顶栏以下的剩余高度');
  check(wrap && /min-height:0/.test(wrap), '.wrap 必须有 min-height:0（flex 子项的默认最小高度会撑破容器）');
  check(wrap && /grid-template-rows:minmax\(0,1fr\)/.test(wrap),
        '.wrap 的行高必须钉死为 minmax(0,1fr)，否则 auto 行会被内容撑高、子栏永远不滚动');
  const col = rule('.wrap>div');
  check(col && /overflow-y:auto/.test(col), '两栏各自应 overflow-y:auto');
  check(col && /overscroll-behavior:contain/.test(col),
        '应加 overscroll-behavior:contain，滚到底不会把滚动"传染"给整页');
  console.log('  ✓ 两栏：高度钉死 + 各自 overflow-y:auto（行高不钉死会失效）');

  // 3. 左栏内部：优先压缩着法记录，而不是滚动整栏把棋盘顶走
  check(/display:flex/.test(rule('#viewCoach>div:first-child') || ''),
        '左栏应是纵向 flex，才能让棋盘卡片固定、着法记录吃掉剩余空间');
  check(/flex:0 0 auto/.test(rule('#viewCoach>div:first-child>.card:first-child') || ''),
        '棋盘卡片必须 flex:0 0 auto（不参与压缩，棋盘永远完整）');
  const mvCard = rule('#viewCoach>div:first-child>.card:last-child');
  check(mvCard && /flex:0 1 auto/.test(mvCard) && /min-height/.test(mvCard),
        '着法记录卡片应可压缩（flex:0 1 auto + min-height）');
  const mvList = rule('#viewCoach>div:first-child>.card:last-child>.movelist');
  check(mvList && /max-height:none/.test(mvList),
        '.movelist 要解除 190px 上限，改由 flex 撑满卡片，否则压缩后留白');
  console.log('  ✓ 左栏：棋盘卡片不压缩，着法记录让位并自己滚动');

  // 4. 窄屏回落：单栏下"独立滚动"更难用，回到整页滚动
  const mq = /@media\(max-width:1180px\)\{([\s\S]*?)\n\}/.exec(css);
  check(!!mq, '应有 ≤1180px 的媒体查询');
  if (mq){
    const t = mq[1];
    check(/body\{[^}]*overflow:auto/.test(t), '窄屏应让 body 恢复 overflow:auto（整页滚动）');
    check(/\.wrap\{[^}]*overflow:visible/.test(t), '窄屏应让 .wrap 恢复 overflow:visible');
    check(/\.wrap>div\{[^}]*overflow:visible/.test(t), '窄屏应让两栏恢复自然高度');
  }
  console.log('  ✓ 窄屏（≤1180px）回落到整页滚动');
}

console.log('');
if (fails){ console.log(`结果：${fails} 项失败`); process.exit(1); }
console.log('结果：全部通过 ✓');
