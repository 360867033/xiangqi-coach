/**
 * 预演摆盘功能测试（Node 运行，无第三方依赖）
 *
 * 需求：讲解/候选表里给了"引擎预演"这条线（炮八平六 → 车1平2 → …），
 *       想照着摆到棋盘上看一看；但以前一动手，讲解就被清掉了
 *       （编辑局面里第一次改动会触发 clearPlayRecord）。
 *
 * 所以这里的核心硬约束是 **预演期间真实棋盘/着法记录/讲解正文一个都不许动**，
 * 外加「按此线接着下」能把预演落到真实棋盘上、且讲解正文仍然保留。
 *
 * 用法： node tests/test_preview.js
 * 退出码 0 = 全部通过
 */
const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'), 'utf8');
const pySrc = fs.readFileSync(path.join(__dirname, '..', 'xq', 'coach.py'), 'utf8');

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
/* 一条真实开局线：炮二平五 马8进7 马二进三 车9平8 */
const LINE = ['h2e2', 'h9g7', 'h0g2', 'i9h9'];
const LINE_CN = ['炮二平五', '马8进7', '马二进三', '车9平8'];

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
      querySelectorAll: () => [],
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
global.setInterval = () => 1;      // 自动播放不真跑定时器，只测按钮文案切换
global.clearInterval = () => {};

/* ================= 3. 沙箱 ================= */
const body = `
function updateEditUI(){}
function renderMoveList(){ document.getElementById('moveList').innerHTML = 'moves'; }
function setHint(t){ ENV.hints.push(t); }
function escapeHtml(s){ return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function drawBoard(){ document.getElementById('boardHost').innerHTML = 'board'; }
function exitEditSilently(){ state.editing = false; }
/* 自由推演从编辑模式切过来时会走这条路（只在 state.editing 为真时才会被调用） */
function setEditMode(on){ state.editing = !!on; }
function clearTables(){}
function onBoardClick(){}
let selected = null, legalCache = [];
let view = 'coach';
/* 假 /api/legal：默认列不出着法，用例可以往 ENV.moves 里塞"这一步有哪些合法着法" */
async function jget(){ return { ok: true, valid: true, moves: ENV.moves || [] }; }
${grabConst('isRed')}
${grabConst('curFen')}
${grabConst('boardKey')}
${grabConst('RED_CN')}
${grabConst('BLACK_CN')}
${grab('fenToBoard')}
${grab('boardToFen')}
${grab('cpText')}
${grab('bandOf')}
${grab('tagCls')}
${grab('uciToFr')}
${grab('guessChinese')}
${grab('previewStepsFrom')}
${grab('startPreview')}
${grab('previewRed')}
${grab('displayBoard')}
${grab('previewGoto')}
${grab('previewStop')}
${grab('previewPlay')}
${grab('exitPreview')}
${grab('renderPreview')}
${grab('previewKeep')}
${grab('previewFromCandidate')}
${grab('previewFromPlayed')}
${grab('showPrevBar')}
${grab('updatePreviewUI')}
${grab('startFreePreview')}
${grab('freeMove')}
${grab('onFreeSquareClick')}
${grab('toggleFreePreview')}
${grab('renderTables')}
/* 对弈模式：这个沙箱测的是预演，对弈那套只要"别把 refreshAll 拖崩"就够了。
   真正跑一遍对弈前端的是 test_play.js */
function updateLoadPlayBtn(){}
function drawPlayBoard(){}
function renderPlayMoveList(){}
function renderPlayInfo(){}
function updatePlaySideUI(){}
${grab('refreshAll')}
${grab('onSquareClick')}
return {
  start: startPreview, goto: previewGoto, exit: exitPreview, keep: previewKeep,
  display: displayBoard, red: previewRed, steps: previewStepsFrom,
  render: renderPreview, click: onSquareClick, tables: renderTables,
  cand: previewFromCandidate, played: previewFromPlayed,
  refresh: refreshAll,
  /* 自由推演 */
  free: toggleFreePreview, freeClick: onFreeSquareClick, freeMove,
  board: () => state.board.slice(),
  prev: () => state.preview,
};`;

const state = {
  board: [], red: true, history: [], lastMove: null, flip: false,
  facts: null, factsFen: null, analyzeBusy: false,
  editing: false, editDirty: false, editUndo: [], preEdit: null, preview: null,
};
const ENV = { hints: [], START, START_RED: true };
const factory = new Function('CELL', 'PAD', 'W', 'H', 'state', 'ENV', body);
const api = factory(CELL, PAD, W, H, state, ENV);

const at = (b, r, f) => b[r * 9 + f];
const sq = (file, rank) => [rank, 'abcdefghi'.indexOf(file)];   // 'e' + 2 -> [2,4]
const KEY = { e2: sq('e', 2), g7: sq('g', 7), g2: sq('g', 2), h9: sq('h', 9) };

function resetReal(){
  state.board = api.steps(START, [], []).board0.slice();
  state.red = true;
  state.history = [];
  state.lastMove = null;
  state.facts = null; state.factsFen = null; state.factsKey = null;
  state.preview = null;
  el('explainBox').innerHTML = '<p>原来的讲解正文：炮二平五之后……</p>';
  ENV.hints.length = 0; ENV.moves = [];
}
const EXPLAIN_BEFORE = () => '<p>原来的讲解正文：炮二平五之后……</p>';

/* ================= 4. 用例 ================= */
console.log('【1】预演线快照：一步一步算好，连记谱、吃子、轮次都对');
{
  const p = api.steps(START, LINE, LINE_CN);
  check(p.steps.length === 4, `应算出 4 步，实为 ${p.steps.length}`);
  check(JSON.stringify(p.board0) === JSON.stringify(api.steps(START, [], []).board0),
        '起点快照 = 起始局面');
  check(at(p.steps[0].board, KEY.e2[0], KEY.e2[1]) === 'C', '第1步后红炮到 e2（炮二平五）');
  check(at(p.steps[0].board, 2, 7) === '', '第1步后 h2（炮原位）空出来');
  check(p.steps[0].red === true && p.steps[1].red === false,
        '第1步是红方走的、第2步是黑方走的（记谱里用的一二三是红方）');
  check(p.steps[1].chinese === '马8进7' && p.steps[1].redAfter === true,
        '第2步记谱为马8进7，走完轮到红方');
  check(p.steps[3].chinese === '车9平8' && at(p.steps[3].board, KEY.h9[0], KEY.h9[1]) === 'r',
        '第4步后黑车落在 h9（车9平8）');
  console.log('  ✓ 4 步快照、记谱、轮次、落点全部正确');
}

console.log('【2】走不通的着法要中断，不能跳过它接着摆');
{
  /* e4 是空位（开局第 5、6 横线全空）—— 从这里"起子"是走不通的 */
  const p = api.steps(START, ['h2e2', 'e4e5', 'h0g2'], ['炮二平五', 'x', '马二进三']);
  check(p.steps.length === 1,
        `第2步起不了子，应停在 1 步（否则后面的着法全错位），实为 ${p.steps.length}`);
  const bad = api.steps(START, ['e4e5'], ['x']);
  check(bad.steps.length === 0, '开头就走不通 -> 一步都不能有');
  console.log('  ✓ 遇走不通的着法立即中断（与 Python describe_line 行为一致）');
}

console.log('【3】预演期间：真实棋盘 / 着法记录 / 讲解正文 一个都不许动 ★核心');
{
  resetReal();
  const beforeBoard = api.board(), beforeFen = state.facts;
  api.start(START, LINE, LINE_CN, '第 1 名 炮二平五 之后的引擎预演');
  check(state.preview !== null, '进入了预演状态');
  check(JSON.stringify(api.board()) === JSON.stringify(beforeBoard), 'state.board 未被改动');
  check(state.history.length === 0, '着法记录没有多出着法');
  check(state.lastMove === null, 'lastMove 没有被写');
  check(el('explainBox').innerHTML === EXPLAIN_BEFORE(), '讲解正文原样保留');
  check(els['prevBar'].style.display === '', '预演控制条显示出来了');

  for (let i = 0; i < 4; i++){
    api.goto(i);
    check(JSON.stringify(api.board()) === JSON.stringify(beforeBoard),
          `摆到第 ${i + 1} 步时 state.board 仍未被改动`);
    check(state.history.length === 0, `摆到第 ${i + 1} 步时着法记录仍为空`);
    check(el('explainBox').innerHTML === EXPLAIN_BEFORE(),
          `摆到第 ${i + 1} 步时讲解正文仍在`);
  }
  check(JSON.stringify(api.display()) === JSON.stringify(api.steps(START, LINE, LINE_CN).steps[3].board),
        '棋盘（虚拟局面）确实走到了第 4 步');
  check(api.red() === true, '第 4 步后轮到红方（预演视角也在跟着走）');
  console.log('  ✓ 摆满 4 步：真实局面、着法记录、讲解正文全部纹丝不动');
}

console.log('【4】预演中点子无效，并明确提示（不能让点击看起来像失灵）');
{
  resetReal();
  api.start(START, LINE, LINE_CN, 't');
  const before = api.board();
  ENV.hints.length = 0;
  api.click(0, 0);              // a0 上的红车
  check(JSON.stringify(api.board()) === JSON.stringify(before), '预演中点击棋盘不会走子');
  check(ENV.hints.some(h => /预演摆盘/.test(h)), '给出了"预演中点击无效"的提示');
  console.log('  ✓ 棋盘点击被挡住，提示写明用控制条操作');
}

console.log('【5】退出预演 = 棋盘回到真实局面，什么都不变');
{
  resetReal();
  const before = api.board();
  api.start(START, LINE, LINE_CN, 't');
  api.goto(2);
  api.exit();
  check(state.preview === null, '预演状态已清空');
  check(els['prevBar'].style.display === 'none', '控制条收起来了');
  check(JSON.stringify(api.board()) === JSON.stringify(before), '真实棋盘回到原样');
  check(el('explainBox').innerHTML === EXPLAIN_BEFORE(), '讲解正文依旧在');
  console.log('  ✓ 退出后一切如初');
}

console.log('【6】「按此线接着下」：落到真实棋盘 + 讲解正文保留（本功能的意义所在）');
{
  resetReal();
  api.start(START, LINE, LINE_CN, 't');
  api.goto(1);
  api.keep();
  const p = api.steps(START, LINE, LINE_CN);
  check(state.preview === null, '落子后退出预演');
  check(JSON.stringify(api.board()) === JSON.stringify(p.steps[1].board),
        '真实棋盘 = 预演到的那一步');
  check(state.history.length === 2, `着法记录应有 2 手，实为 ${state.history.length}`);
  check(state.history[0].chinese === '炮二平五' && state.history[1].chinese === '马8进7',
        '记谱正确：炮二平五 / 马8进7');
  check(state.red === true, '轮次正确：两步走完轮到红方');
  const txt = el('explainBox').innerHTML;
  check(txt.includes('原来的讲解正文'), '★讲解正文没有被清掉（这正是要修的问题）');
  check(txt.includes('照着讲解的预演走了 2 步'), '加了一条"已按预演走了几步"的说明');
  check(txt.includes('原来那个局面'), '说明里标明这是原来局面的讲解，避免误读');
  check(state.facts === null, '旧候选表对应的局面已变，facts 清空（不会拿错数据）');
  check(els['btnAnalyzeMove'].disabled === false, '可以继续点「讲解我这一步」评价这条线');
  console.log('  ✓ 真实棋盘=预演第2步，着法记录 2 手，讲解正文＋说明都在');
}

console.log('【7】着法条（chips）与当前步高亮');
{
  resetReal();
  api.start(START, LINE, LINE_CN, 't');
  api.goto(2);
  const h = els['prevChips'].innerHTML;
  check((h.match(/class="chip/g) || []).length === 4, '着法条应恰好 4 个');
  check(/1\.炮二平五/.test(h) && /4\.车9平8/.test(h), '着法条内容是中文记谱');
  check((h.match(/class="chip (red|blk) on"/g) || []).length === 1,
        '恰有 1 个"当前步"高亮，实为 ' + (h.match(/class="chip (red|blk) on"/g) || []).length);
  check(/class="chip (red|blk) on"[^>]*>3\.马二进三/.test(h),
        '高亮的正是第 3 步（马二进三）');
  check(els['prevStep'].textContent === '3/4', `步骤读数应为 3/4，实为 ${els['prevStep'].textContent}`);
  check(els['prevNext'].disabled === false && els['prevFirst'].disabled === false,
        '中间步：上一步/下一步都可用');
  api.goto(-1);
  check(els['prevFirst'].disabled === true && els['prevBack'].disabled === true,
        '起点：⏮/◀ 应禁用');
  check(els['prevKeep'].disabled === true, '起点：还没有可落的步子，「按此线接着下」应禁用');
  console.log('  ✓ 着法条 1:1、高亮唯一、边界按钮状态正确');
}

console.log('【8】候选表的「摆一摆」入口');
{
  resetReal();
  const facts = {
    fen: START, side_to_move: '红方', red_to_move: true, material: '双方子力完全一样',
    board_text: 'x', positions: 'x', depth: 18, legal_count: 44,
    candidates: [
      {rank: 1, uci: 'h2e2', chinese: '炮二平五', score_cp: 12, score_red: 12,
       wdl: [40, 55, 5], is_mate: false, capture: false,
       pv_chinese: LINE_CN, pv_uci: LINE},
      {rank: 2, uci: 'b2e2', chinese: '炮八平五', score_cp: 0, score_red: 0,
       wdl: [35, 60, 5], is_mate: false, capture: false,
       pv_chinese: ['炮八平五'], pv_uci: []},        // 没有序列 -> 不该出按钮
    ],
    best: null, played: null,
    cloud: {status: 'skipped', moves: []}, band: '均势',
  };
  state.facts = facts;
  api.tables(facts, true);
  const h = els['candTable'].innerHTML;
  check(/class="btn xs pvbtn" data-idx="0"/.test(h), '第 1 名有「摆一摆」按钮');
  check((h.match(/pvbtn/g) || []).length === 1, '没有着法序列的行不出现按钮');
  api.cand(0);
  check(state.preview && state.preview.steps.length === 4, '点「摆一摆」用该行的序列进入预演');
  check(state.preview.title.includes('第 1 名') && state.preview.title.includes('炮二平五'),
        '预演标题写清了是哪一行的线：' + state.preview.title);
  api.exit();
  state.facts = facts;
  api.played();
  check(!state.preview && ENV.hints.length > 0, '没有"你走的着法"时给出提示而不是报错');
  console.log('  ✓ 候选表入口可用，缺序列的行自动不出按钮');
}

console.log('【9】自由推演：棋盘上双方随你走，真实棋局与讲解一样不动 ★核心');
{
  resetReal();
  const before = api.board();
  api.free();                       // 点「自由推演」
  check(state.preview && state.preview.mode === 'free', '进入了自由推演（mode=free）');
  check(!state.editing, '自由推演不是编辑模式（它压根不动真实棋盘）');
  check(els['btnFree'].textContent === '退出推演', '按钮文案变成「退出推演」');
  check(els['prevStep'].textContent === '起点', '还没走子时步数显示「起点」');
  check(/真实棋局和这份讲解都不受影响/.test(els['prevNote'].innerHTML),
        '说明里写清了"不影响真实棋局和讲解"');
  check(/直接在棋盘上走子/.test(els['prevChips'].innerHTML),
        '着法条位置提示"直接在棋盘上走子"');

  api.freeMove([2, 7], [2, 4], 'h2e2');          // 红：炮二平五
  check(state.preview.steps.length === 1 && state.preview.idx === 0, '走出第 1 步');
  check(at(api.display(), 2, 4) === 'C', '虚拟棋盘上红炮到了 e2');
  check(state.preview.steps[0].chinese === '炮二平五',
        '记谱正确：' + state.preview.steps[0].chinese);
  check(api.red() === false, '轮到黑方（红黑交替，两边都能走）');

  api.freeMove([7, 7], [7, 4], 'b7e7');          // 黑：炮8平5
  check(state.preview.steps.length === 2 && api.red() === true, '黑方也能走，走完又轮到红方');
  check((els['prevChips'].innerHTML.match(/class="chip/g) || []).length === 2,
        '着法条上有 2 步');
  /* 自由推演的着法带 class="chip red/blk free on"（比摆一摆多一个 free），
     所以这里不能用【7】那条正则。当前步必须唯一，且那枚里必须真的有字 */
  const fh = els['prevChips'].innerHTML;
  check((fh.match(/\bon\b/g) || []).length === 1,
        '自由推演里也恰有 1 个"当前步"高亮，实为 ' + (fh.match(/\bon\b/g) || []).length);
  check(/free on"[^>]*>2\.炮8平5/.test(fh),
        '高亮的正是刚走的第 2 步，而且那枚 chip 里带着中文记谱（不能被"金底金字"吃成空白）');
  check(JSON.stringify(api.board()) === JSON.stringify(before), '★真实棋盘一动不动');
  check(state.history.length === 0, '★这些推演步没有被写进着法记录');
  check(state.lastMove === null, '★lastMove 没有被写');
  check(el('explainBox').innerHTML === EXPLAIN_BEFORE(), '★讲解正文原样保留');

  /* 退回去换一种走法：后面那一步要作废，而不是两边都留着 */
  api.goto(0);
  api.freeMove([7, 7], [7, 4], 'b7e7');
  check(state.preview.steps.length === 2,
        `退到第 1 步再走 = 原来的第 2 步作废后重走，仍应是 2 步，实为 ${state.preview.steps.length}`);
  check(state.preview.idx === 1, '当前停在新走的那一步');

  /* 落到棋盘：和「按此线接着下」共用同一套逻辑，讲解正文仍然保留 */
  api.keep();
  check(state.preview === null, '落子后退出推演');
  check(state.history.length === 2, `推演 2 步后着法记录应有 2 手，实为 ${state.history.length}`);
  check(at(api.board(), 2, 4) === 'C', '真实棋盘上红炮确实到了 e2');
  check(el('explainBox').innerHTML.includes('自由推演走了 2 步'),
        '落子说明用的是「自由推演」的说法');
  check(el('explainBox').innerHTML.includes('原来的讲解正文'), '★落子后讲解正文仍在');
  console.log('  ✓ 自由推演：双方都能走、退回重走会作废、落到棋盘后讲解仍在');
}

console.log('【9b】「摆一摆」与「自由推演」互不冲突：摆到第几步就从那儿接着推');
{
  resetReal();
  api.start(START, LINE, LINE_CN, '第 1 名 炮二平五 之后的引擎预演');
  api.goto(2);                                   // 摆到第 3 步
  const snap = api.display().slice();
  check(api.red() === false, '第 3 步（马二进三）走完轮到黑方');
  api.free();                                    // 点「自由推演」
  check(state.preview.mode === 'free', '从「摆一摆」切到自由推演');
  check(state.preview.steps.length === 4, '原来那条线的着法条留着了（没被清掉）');
  check(state.preview.idx === 2, '还停在原来摆到的那一步，可以从这里接着走');
  check(JSON.stringify(api.display()) === JSON.stringify(snap), '棋盘接着那一步的局面');
  check(els['prevKeep'].textContent === '落到棋盘',
        '按钮换成自由推演的说法：' + els['prevKeep'].textContent);
  api.freeMove([9, 8], [9, 7], 'i9h9');          // 黑：车9平8
  check(state.preview.idx === 3 && state.preview.steps.length === 4,
        `从第 3 步接着走 = 原第 4 步作废后再走一步，实为 idx=${state.preview.idx} len=${state.preview.steps.length}`);
  api.free();                                    // 再点一次 = 退出推演
  check(state.preview === null, '再点「退出推演」就回到真实局面');
  check(els['btnFree'].textContent === '自由推演', '按钮文案还原');
  check(el('explainBox').innerHTML === EXPLAIN_BEFORE(), '来回切换也没动过讲解正文');
  console.log('  ✓ 两种预演可以互相接力，谁也不清谁');
}

console.log('【10】静态约束（防止以后改坏）');
{
  const fn = (name) => {
    let i = src.indexOf('function ' + name);
    if (i < 0) return '';
    let d = 0, j = src.indexOf('{', i);
    for (let k = j; k < src.length; k++){
      if (src[k] === '{') d++;
      else if (src[k] === '}'){ d--; if (d === 0) return src.slice(i, k + 1); }
    }
    return '';
  };
  check(/preview/.test(fn('displayBoard')), 'drawBoard 走的是 displayBoard()（预演时画虚拟局面）');
  const db = fn('drawBoard');
  check(/displayBoard\(\)/.test(db), 'drawBoard 确实用 displayBoard()');
  const rf = fn('refreshAll');
  check(/btnEdit/.test(rf) && /disabled = !!pv/.test(rf),
        '预演中要禁用会改真实局面的按钮（编辑/悔棋/分析/粘贴 FEN）');
  const keep = fn('previewKeep');
  check(!/explainBox'\)\.innerHTML = ''/.test(keep) && !/clearPlayRecord/.test(keep),
        '★「按此线接着下」里绝不能清空讲解框、也不能调用 clearPlayRecord');
  check(/staleNote/.test(keep), '落子后给讲解加上"已过期/仅供参考"的说明');
  check(/pv_uci/.test(pySrc), 'coach.py 给前端提供了 pv_uci（预演用的着法序列）');
  const ft = pySrc.slice(pySrc.indexOf('def facts_to_text'),
                         pySrc.indexOf('def build_explain_prompt'));
  check(!/pv_uci/.test(ft),
        '★facts_to_text 不许打印 pv_uci（否则大模型又开始抄字母坐标）');

  /* 页面脚本最顶层那一堆 getElementById(...).onclick = ... 是"漏一个就整页挂掉"的地方
     （预览控制条就是这么接上去的），这里把全部 id 引用对一遍 */
  const ids = new Set();
  for (const m of src.matchAll(/getElementById\(['"]([^'"]+)['"]\)/g)) ids.add(m[1]);
  const missing = [...ids].filter(id => !new RegExp(`id="${id}"`).test(src));
  check(missing.length === 0, '脚本引用的元素 id 都能在 HTML 里找到（缺：' + missing.join(',') + '）');
  ['prevBar', 'prevTitle', 'prevStep', 'prevChips', 'prevNote',
   'prevFirst', 'prevBack', 'prevNext', 'prevPlay', 'prevKeep', 'prevExit'
  ].forEach(id => check(ids.has(id), `预演控制条元素 ${id} 已被脚本绑定`));

  /* ---- 「算」与「讲」拆成两个按钮（用户需求一） ---- */
  const an = fn('analyze');
  check(/withExplain/.test(an), 'analyze 有 withExplain 开关（算/讲分离）');
  const explained = an.match(/if \(withExplain\)\{[^}]*await explain\(\);\s*\}/g) || [];
  check(explained.length === 2,
        `await explain() 只应出现在 if (withExplain) 分支里（2 处），实为 ${explained.length}`);
  check(!/clearPlayRecord|null/.test('') && /已计算（未讲解）/.test(an),
        '只计算的分支会明确写出"已计算（未讲解）"');
  check((an.match(/已计算（未讲解）/g) || []).length >= 2,
        '两条路径（重算 / 命中已算过的局面）都要标出「已计算（未讲解）」');
  check(/state\.factsKey === key/.test(an),
        '★已经算过的局面直接复用结果（点完「计算」再点「分析」不重跑引擎）');
  check(!/analyze\(false\);|analyze\(true\);/.test(src),
        '★不许再出现只传一个参数的 analyze(x)（否则又会变成"算完必讲"）');
  ['btnCalcPos', 'btnAnalyzePos', 'btnAnalyzeMove'].forEach(id =>
    check(new RegExp(`getElementById\\('${id}'\\)\\.onclick = \\(\\) => analyze\\(`).test(src),
          `${id} 已绑到 analyze(...)`));
  check(/btnCalcPos'\)\.onclick = \(\) => analyze\(false, false\)/.test(src),
        '「计算当前局面」= analyze(false, false)：只跑引擎 + 云库');
  check(/btnAnalyzePos'\)\.onclick = \(\) => analyze\(false, true\)/.test(src),
        '「分析当前局面」= analyze(false, true)：计算 + 讲解');
  check(/btnAnalyzeMove'\)\.onclick = \(\) => analyze\(true, true\)/.test(src),
        '「讲解我这一步」= analyze(true, true)');
  ['btnCalcPos', 'btnAnalyzePos', 'btnAnalyzeMove'].forEach(id =>
    check(new RegExp(`id="${id}"`).test(src), `HTML 里有按钮 ${id}`));
  check(/\['btnCalcPos', 'btnAnalyzePos', 'btnEdit', 'btnUndo', 'btnPasteFen'\]/.test(src),
        '预演中要连同「计算当前局面」一起禁用（它也会改到真实局面）');

  /* ---- 自由推演（用户需求二） ---- */
  check(/id="btnFree"/.test(src), 'HTML 里有「自由推演」按钮');
  const freeBtnPos = src.indexOf('id="btnFree"'), editBtnPos = src.indexOf('id="btnEdit"');
  check(freeBtnPos > 0 && freeBtnPos - editBtnPos < 80,
        '「自由推演」紧跟在「编辑局面」后面（就在它旁边）');
  const editRow = src.slice(src.indexOf('id="btnEdit"') - 200, src.indexOf('id="editPanel"'));
  check(/id="btnEdit"/.test(editRow) && /id="btnFree"/.test(editRow),
        '「自由推演」就在「编辑局面」旁边（同一行）');
  check(!/'btnFree'/.test(fn('refreshAll')),
        '★预演中不能禁用 btnFree —— 它是"摆一摆→自由推演→退出"的开关');
  check(/if \(state\.preview\.mode === 'free'\) return onFreeSquareClick\(r, f\)/.test(fn('onSquareClick')),
        '★点棋盘时自由推演走 onFreeSquareClick，摆一摆仍旧挡住并提示');
  check(/p\.steps = p\.steps\.slice\(0, p\.idx \+ 1\)/.test(fn('freeMove')),
        '自由推演退回重走时，后面的着法要作废（否则着法条自相矛盾）');
  check(/boardToFen\(displayBoard\(\), previewRed\(\)\)/.test(fn('onFreeSquareClick')),
        '自由推演也用同一套规则引擎判合法着法（不自己发明一套走法规则）');
  /* ---- 追问记录：摆放位置 + 清空点收口（用户需求） ---- */
  const iAskBox = src.indexOf('id="askBox"'), iAskRow = src.indexOf('id="askRow"');
  check(iAskBox > 0 && iAskRow > iAskBox,
        '★#askBox 排在 #askRow 之前（输入框跟在最新一条追问下方，不能固定在讲解下方）');
  check(iAskBox > src.indexOf('id="explainBox"'), '追问记录在讲解之后');
  check(/id="askInput"/.test(src.slice(iAskBox, iAskRow + 400)), '输入框就在追问记录后面');
  check(/function clearAskHistory\(\)/.test(src) && /function bindAskHistory\(key\)/.test(src),
        '有 clearAskHistory / bindAskHistory 两个收口函数');
  const nClear = (src.match(/clearAskHistory\(\);/g) || []).length;
  check(nClear === 6,
        `★clearAskHistory 恰好被调 6 次（编辑局面/复盘跳转/新开一局/载入 FEN/分析/读取对弈棋局），实为 ${nClear}`);
  check((src.match(/window\.askHistory = \[\];/g) || []).length === 1,
        '★window.askHistory 只在 clearAskHistory 里清（不许再有裸清，漏一处就会残留）');
  check(/bindAskHistory\(key\)/.test(fn('analyze')),
        '★analyze 开头把追问记录绑到本次局面（换局面就清）');
  check(/askQ/.test(fn('ask')), '追问那一行用了 .askQ（带虚线分隔）');

  /* ---- 着法条「当前步」必须看得见（金底 + 金字 = 空白）★踩过 ---- */
  /* 先剥掉 CSS 注释：注释里可能写了 .chip.xxx{color:…} 这类示例，
     剥掉才是对的，否则那对大括号会被当成规则边界（自己踩过） */
  const styleTxt = ((src.match(/<style>([\s\S]*?)<\/style>/) || ['', ''])[1])
    .replace(/\/\*[\s\S]*?\*\//g, ' ');
  const cssRules = [...styleTxt.matchAll(/([^{}]*)\{([^{}]*)\}/g)]
    .map(m => ({sel: m[1].trim(), body: m[2], at: m.index}));
  const chipRules = cssRules.filter(r => /\.chip(?![\w-])/.test(r.sel));
  const onRule = chipRules.find(r => /\.chip\.on(?![\w-])/.test(r.sel) && /(?:^|;)\s*color\s*:/.test(r.body));
  check(!!onRule, 'CSS 里有 .chip.on 的配色规则（当前步高亮）');
  const onColor = onRule
    ? ((onRule.body.match(/(?:^|;)\s*color\s*:\s*([^;]+)/) || [])[1] || '').trim() : '';
  check(onColor && onColor !== 'var(--accent)' && !/#(f|e|d)[0-9a-f]{2}/i.test(onColor),
        `当前步的字色不能等于底色（否则金字压金底、看着像空白），实为 ${onColor || '空'}`);
  /* 关键：任何排在 .chip.on 之后、同样只带类名的 .chip.xxx{color:…}
     都会把字色改回主题色 —— 自由推演的 .chip.free 就是这么坏的 */
  const offenders = chipRules.filter(r =>
    onRule && r.at > onRule.at && /(?:^|;)\s*color\s*:/.test(r.body) &&
    !/\.on/.test(r.sel) && /\.chip\.[\w-]+/.test(r.sel));
  check(offenders.length === 0,
        '★没有 .chip.xxx{color:…} 排在 .chip.on 之后（有的话当前步会变成金底金字看不见）' +
        (offenders.length ? '：' + offenders.map(o => o.sel).join(' / ') : ''));
  check(/\.chip\.free:not\(\.on\)/.test(styleTxt),
        '自由推演着法配色写成 :not(.on)（让步于当前步）');

  console.log('  ✓ 关键约束已写进代码结构里');
}

console.log('【11】整页脚本语法（漏一个括号整页就白屏）');
{
  const scripts = [...src.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
  check(scripts.length > 0, '找得到内联脚本');
  scripts.forEach((code, i) => {
    let err = null;
    try { new Function(code); } catch (e) { err = e; }   // 只解析不执行
    check(!err, `第 ${i + 1} 段脚本语法正确` + (err ? '：' + err.message : ''));
  });
  console.log(`  ✓ ${scripts.length} 段内联脚本语法通过`);
}

console.log('【12】整页脚本在假 DOM 里跑一遍初始化（顶层绑定写错就会白屏）');
(async () => {
  /* 这套假 DOM 对任何 id 都返回一个"什么都有"的元素：
     真浏览器里 getElementById 返回 null 才是问题，所以这里只测"跑得完不炸"，
     "id 是否真的存在"由【9】那条静态检查负责 */
  const store = {};
  const mkEl = (id) => ({
    id, innerHTML: '', textContent: '', style: {}, value: '', disabled: false,
    dataset: {}, classList: mkClassList(), scrollTop: 0, scrollHeight: 0,
    addEventListener(){}, appendChild(){}, insertAdjacentHTML(){},
    querySelectorAll: () => [], setAttribute(){}, getAttribute(){ return null; },
    onclick: null, oncontextmenu: null,
  });
  const getEl = id => (store[id] || (store[id] = mkEl(id)));
  const fakeBoard = {
    getBoundingClientRect: () => ({ left: 0, top: 0, width: W, height: H }),
    viewBox: { baseVal: { width: W, height: H } },
    addEventListener(){}, style: {},
  };
  const allScript = [...src.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).join('\n');
  const winObj = {};          // 当 window 传进去，好从外面看 askHistory / askKey
  /* 假 fetch：/api/analyze 直接返回失败（不真跑引擎），其他接口返回健康信息 */
  const fakeFetch = async url => ({
    ok: true,
    json: async () => (String(url).includes('/api/analyze')
      ? {ok: false, error: '(测试桩：不真跑引擎)'}
      : {ok: true, engine: 'Pikafish.exe', model: 'deepseek-flash',
         analyze_depth: 18, review_depth: 14, multipv: 4, cloud: true,
         start_fen: START}),
  });
  let bootErr = null, api2 = null;
  try {
    const run = new Function('document', 'window', 'navigator', 'fetch', 'alert',
      allScript + '\n;return {state, analyze, ask, clearAskHistory, bindAskHistory};');
    api2 = run(
      { getElementById: getEl,
        querySelector: sel => (sel === 'svg.board' ? fakeBoard : getEl('q:' + sel)),
        querySelectorAll: () => [], createElement: () => mkEl('tmp'),
        addEventListener(){} },
      winObj, { clipboard: { writeText: async () => {} } },
      fakeFetch,
      () => {});
  } catch (e){ bootErr = e; }
  check(!bootErr, '整页脚本初始化不抛异常' + (bootErr ? '：' + bootErr.message : ''));

  if (!bootErr){
    /* init 是 async 的，等它的微任务跑完再看结果 */
    await new Promise(r => setImmediate(r));
    check(api2.state.board.filter(Boolean).length === 32,
          `启动后棋盘应是开局 32 枚，实为 ${api2.state.board.filter(Boolean).length}`);
    check(api2.state.preview === null, '启动后不处于预演状态');
    /* 假 DOM 不解析 HTML 属性，所以"默认收起"要用文档本身来验 */
    check(/id="prevBar"[^>]*style="display:none"/.test(src),
          '空局面下预演控制条默认是收起的（HTML 里的 display:none）');
    check(getEl('engInfo').textContent.includes('Pikafish.exe'), '顶栏引擎信息已填（init 跑通了）');
    let clickErr = null;
    try { getEl('prevNext').onclick(); } catch (e){ clickErr = e; }   // 没预演时点"下一步"
    check(!clickErr, '没在预演时点「下一步」不报错' + (clickErr ? '：' + clickErr.message : ''));
    try { getEl('prevExit').onclick(); } catch (e){ clickErr = e; }
    check(!clickErr, '没在预演时点「退出预演」不报错');
    console.log('  ✓ 整页脚本能跑完 init（顶栏信息 + 新开局），控制条不缺绑定');

    /* ---- 追问记录的寿命：换局面重新分析时，旧问答必须消失（用户报过的 bug） ---- */
    const askBoxEl = getEl('askBox');
    winObj.askHistory = [{role: 'user', content: '上一个局面的问题'}];
    winObj.askKey = 'OLD_FEN|x';
    askBoxEl.innerHTML = '<div class="askQ muted">你：上一个局面的问题</div>';
    await api2.analyze(false, false);            // 只计算（少一步流式），照样要清
    check(askBoxEl.innerHTML === '',
          '★换局面重新分析时，界面上的旧追问记录被清掉（否则新讲解下挂着上一个局面的问答）');
    check((winObj.askHistory || []).length === 0,
          '★window.askHistory 同步清空（不清的话旧问答还会被带给模型）');
    check(winObj.askKey && winObj.askKey !== 'OLD_FEN|x', 'askKey 已改指本次分析的局面');

    /* 同一个局面重复分析（先「计算」再「分析」）→ 这是同一组，问答要留着 */
    api2.state.facts = {candidates: [], played: null, cloud: null, best: null};
    api2.state.factsKey = winObj.askKey;
    winObj.askHistory = [{role: 'user', content: '这一组的问题'}];
    askBoxEl.innerHTML = '<div class="askQ muted">你：这一组的问题</div>';
    await api2.analyze(false, false);
    check(askBoxEl.innerHTML.includes('这一组的问题'),
          '同一局面重复分析不清追问记录（「计算」→「分析」还是同一组）');
    check((winObj.askHistory || []).length === 1, 'askHistory 也照样留着');

    /* 还没分析就点「追问」：要给提示，不能静默无反应 */
    api2.state.facts = null;
    getEl('askInput').value = '随便问一句';
    let askErr = null;
    try { await api2.ask(); } catch (e){ askErr = e; }
    check(!askErr, '没分析时点「追问」不报错' + (askErr ? '：' + askErr.message : ''));
    check(/先点/.test(getEl('statusHint').innerHTML),
          '没分析时点「追问」会提示"先点分析"，而不是点了没反应');
    winObj.askHistory = [];
    console.log('  ✓ 追问记录：换局面清空、同局面保留、没分析时给提示');

    /* 自由推演的完整点击链路：点棋子 → 点目标格（走的是虚拟局面） */
    resetReal();
    const beforeFree = api.board();
    ENV.moves = [{from: [2, 7], to: [2, 4], uci: 'h2e2'}];
    api.free();
    await api.click(2, 7);                 // 点红炮：选中 + 问后端要合法着法
    await api.click(2, 4);                 // 点目标格：走子
    check(state.preview && state.preview.steps.length === 1,
          '自由推演里点棋盘能走子（点击链路通）');
    check(at(api.display(), 2, 4) === 'C', '虚拟棋盘上红炮到了 e2');
    check(JSON.stringify(api.board()) === JSON.stringify(beforeFree),
          '★点棋盘走子也不会改到真实棋盘');
    check(el('explainBox').innerHTML === EXPLAIN_BEFORE(), '★点棋盘走子不清讲解');
    check(state.preview.mode === 'free', '仍然是自由推演状态（没有被 doMove 顶掉）');
    api.exit(); ENV.moves = [];
  }

  console.log('');
  if (fails){ console.log(`结果：${fails} 项失败`); process.exit(1); }
  console.log('结果：全部通过 ✓');
})();
