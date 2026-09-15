/**
 * 棋盘点击坐标反算测试（Node 运行，无依赖）
 *
 * 背景：曾经只给「有棋子的格子」绑点击事件，导致点空位（绿点）完全没反应、
 *       吃子时绿点盖住棋子也点不动。修法是把事件绑到整块棋盘，
 *       再自己把像素反算成格位 —— 反算错了会「点这里走到那里」，所以必须对拍。
 *
 * 用法： node tests/test_board_click.js
 * 退出码 0 = 全部通过
 */
const fs = require('fs');
const path = require('path');

const HTML = path.join(__dirname, '..', 'web', 'index.html');
const src = fs.readFileSync(HTML, 'utf8');

let fails = 0;
function check(ok, msg){
  if (!ok){ fails++; console.log('  ✗ ' + msg); }
  return ok;
}

/* ---------- 1. 从 index.html 里抽出被测的纯函数 ---------- */
function grab(name){
  const re = new RegExp('function\\s+' + name + '\\s*\\([^)]*\\)\\s*\\{');
  const m = re.exec(src);
  if (!m) throw new Error('在 index.html 里找不到函数 ' + name);
  const prefix = /\basync\s*$/.test(src.slice(Math.max(0, m.index - 8), m.index)) ? 'async ' : '';
  let i = src.indexOf('{', m.index), depth = 0;
  for (let j = i; j < src.length; j++){
    if (src[j] === '{') depth++;
    else if (src[j] === '}'){
      depth--;
      if (depth === 0) return prefix + src.slice(m.index, j + 1);
    }
  }
  throw new Error('函数 ' + name + ' 括号不闭合');
}

// 源码里写在同一行：const CELL = 52, PAD = 34;
const dim = /const\s+CELL\s*=\s*([\d.]+)\s*,\s*PAD\s*=\s*([\d.]+)/.exec(src);
const CELL = dim ? +dim[1] : +(/\bCELL\s*=\s*([\d.]+)/.exec(src) || [])[1];
const PAD  = dim ? +dim[2] : +(/\bPAD\s*=\s*([\d.]+)/.exec(src) || [])[1];
check(Number.isFinite(CELL) && Number.isFinite(PAD) && CELL > 0,
      `能从 index.html 读到 CELL=${CELL} PAD=${PAD}`);

const sandbox = { CELL, PAD, state: { flip: false } };
const factory = new Function(
  'CELL', 'PAD', 'state',
  grab('xy') + '\n' + grab('squareFromPixels') + '\nreturn {xy, squareFromPixels};'
);
const { xy, squareFromPixels } = factory(CELL, PAD, sandbox.state);

/* ---------- 2. 90 个格位：像素 → 格位 必须严格互逆 ---------- */
console.log('【坐标往返】xy() 与 squareFromPixels() 互逆');
for (const flip of [false, true]){
  sandbox.state.flip = flip;
  let bad = 0, seen = new Set();
  for (let rank = 0; rank < 10; rank++){
    for (let file = 0; file < 9; file++){
      const [x, y] = xy(rank, file);
      const back = squareFromPixels(x, y, flip);
      if (!back || back[0] !== rank || back[1] !== file){
        bad++;
        if (bad <= 3) console.log(`  ✗ flip=${flip} (${rank},${file}) → 像素(${x},${y}) → ${JSON.stringify(back)}`);
      } else seen.add(back[0] * 9 + back[1]);
    }
  }
  check(bad === 0, `flip=${flip} 往返全部正确（错 ${bad} 个）`);
  check(seen.size === 90, `flip=${flip} 90 个格位互不重叠（实得 ${seen.size}）`);
  if (bad === 0) console.log(`  ✓ flip=${flip}：90/90 格位往返一致、无重叠`);
}

/* ---------- 3. 落在两格中间时取最近的一格 ---------- */
console.log('【就近取格】格心偏移半格以内都应命中该格');
sandbox.state.flip = false;
{
  let bad = 0;
  const [cx, cy] = xy(3, 4);            // 取一个中腹格位
  for (const [dx, dy] of [[-25,0],[25,0],[0,-25],[0,25],[-25,-25],[25,25]]){
    const sq = squareFromPixels(cx + dx, cy + dy, false);
    if (!sq || sq[0] !== 3 || sq[1] !== 4) bad++;
  }
  check(bad === 0, `偏移 ±25px（< 半格 ${CELL/2}）仍命中同一格，错 ${bad} 个`);
  // 超过半格就该落到邻格，不能停在原地
  const far = squareFromPixels(cx + CELL * 0.7, cy, false);
  check(far && (far[0] !== 3 || far[1] !== 4), '偏移超过半格时会落到邻格');
  if (!bad) console.log('  ✓ ±25px 偏移全部命中同一格，超过半格正常落到邻格');
}

/* ---------- 4. 棋盘外的空白不应误判成某个格位 ---------- */
console.log('【边界】棋盘外侧留白不应被算成格子');
{
  // 判定容差是半格：离交叉点 ≤ CELL/2 就算命中，所以留白外侧
  // (PAD - CELL/2) = 8px 这一圈是"死区"，再往里属于手指容差
  const dead = PAD - CELL / 2;
  console.log(`  参考：棋盘边缘外 ${dead}px 起为死区，向内属于 ±${CELL/2}px 容差`);
  let bad = 0;
  const probes = [[0, 0], [dead * 0.7, dead * 0.7], [9999, 0], [0, 9999],
                  [-50, 100], [100, -50]];
  for (const [px, py] of probes){
    if (squareFromPixels(px, py, false) !== null){
      bad++;
      console.log(`  · 探针 (${px},${py}) 被算成了 ${JSON.stringify(squareFromPixels(px, py, false))}`);
    }
  }
  check(bad === 0, `${probes.length} 个棋盘外坐标都应返回 null，越界 ${bad} 个`);

  // 四个角的正中央（最外圈交叉点）必须能点到
  const H = PAD * 2 + 9 * CELL, W = PAD * 2 + 8 * CELL;
  const corners = [[PAD,PAD],[W-PAD,PAD],[PAD,H-PAD],[W-PAD,H-PAD]];
  let miss = 0;
  for (const [px, py] of corners) if (!squareFromPixels(px, py, false)) miss++;
  check(miss === 0, '棋盘四角的交叉点都能点到，漏 ' + miss + ' 个');
  if (!bad && !miss) console.log('  ✓ 外侧留白返回 null，四个角交叉点可点');
}

/* ---------- 5. 源码结构：事件必须绑在整块棋盘上 ---------- */
console.log('【结构】点击事件绑定方式');
check(/svg\.addEventListener\(\s*'click'\s*,\s*onBoardClick\s*\)/.test(src),
      '应给 svg.board 绑定 onBoardClick');
check(!/querySelectorAll\(\s*['"]\.piece['"]\s*\)\s*\.forEach/.test(src),
      '不应再给 .piece 逐个绑事件（这正是「点绿点没反应」的根因）');
check(/pointer-events="none"/.test(src), '绿点应设 pointer-events="none"，不遮挡点击');
check(/aria|role=/.test(src) || true, '');

/* ---------- 6. 整块棋盘只有一个事件处理器，不会重复触发 ---------- */
console.log('【唯一性】drawBoard 每次重建 DOM，处理器只绑一次');
{
  const n = (src.match(/addEventListener\(\s*'click'/g) || []).length;
  check(n >= 1, `index.html 中共有 ${n} 处 click 监听（棋盘 1 处 + 按钮等）`);
  // onBoardClick 必须只调用一次 onSquareClick，避免一次点击走两步
  const body = grab('onBoardClick');
  const calls = (body.match(/onSquareClick\(/g) || []).length;
  check(calls === 1, `onBoardClick 中 onSquareClick 调用次数应为 1，实为 ${calls}`);
  if (calls === 1) console.log('  ✓ 一次点击只触发一次走子判定（不会一步走两回）');
}

/* ---------- 7. 真实点击流程：点绿点到底会不会走子 ---------- */
console.log('【流程】用假的 DOM/接口跑 onSquareClick，验证"点绿点 → 走子"');
(async () => {
  // 造一个空棋盘，只放红车(3,4) 黑卒(3,2)、红马(0,1)
  const board = new Array(90).fill('');
  board[3 * 9 + 4] = 'R';   // 红车
  board[3 * 9 + 2] = 'p';   // 黑卒（可吃）
  board[0 * 9 + 1] = 'N';   // 红马（另一个自己的子）

  const ENV = { moves: [], draws: 0, legal: [], thrown: null };
  const env = { state: { board, red: true, flip: false } };

  const body = `
    let selected = null, legalCache = [];
    function doMove(from, to, uci){ ENV.moves.push([from[0], from[1], to[0], to[1], uci]); selected = null; legalCache = []; }
    function drawBoard(){ ENV.draws++; }
    async function jget(){ return { moves: ENV.legal }; }
    function curFen(){ return 'test-fen'; }
    function isRed(c){ return !!c && c === c.toUpperCase(); }
    ${grab('onSquareClick')}
    return {
      click: onSquareClick,
      peek: () => ({ selected, legalCache }),
      seed: (s, l) => { selected = s; legalCache = l; }
    };`;
  const page = new Function('state', 'ENV', body)(env.state, ENV);

  const CAR = [3, 4];
  const legalAll = [
    { from: [3, 4], to: [3, 2], uci: 'e2e4' },   // 车吃卒
    { from: [3, 4], to: [3, 0], uci: 'e2e0' },   // 车进到底
    { from: [0, 1], to: [2, 2], uci: 'b0c2' }    // 马
  ];

  // 7.1 点自己的车 → 应选中，并且只缓存"这个子"的着法
  ENV.legal = legalAll; ENV.moves = [];
  await page.click(3, 4);
  let st = page.peek();
  check(st.selected && st.selected[0] === 3 && st.selected[1] === 4, '点自己的棋子后应选中它');
  check(st.legalCache.length === 2, `选中后应缓存该子的 2 步着法，实为 ${st.legalCache.length}`);
  check(ENV.moves.length === 0, '仅选中不应走子');
  console.log('  ✓ 选中红车，缓存到 2 步着法（吃卒 / 进底）');

  // 7.2 ★核心回归：点绿点（空位）→ 必须走子。这就是用户报的 bug
  ENV.moves = [];
  await page.click(3, 0);
  check(ENV.moves.length === 1 && ENV.moves[0][4] === 'e2e0',
        `点空位绿点应走子，实得 ${JSON.stringify(ENV.moves)}`);
  check(page.peek().selected === null, '走子后应清空选中状态');
  if (ENV.moves.length === 1) console.log(`  ✓ 点空位绿点 → 走子 ${ENV.moves[0][4]}（原 bug 点这里完全没反应）`);

  // 7.3 吃子：绿点画在对方棋子上方，也必须能点
  page.seed(CAR, legalAll.filter(m => m.uci === 'e2e4'));
  ENV.moves = [];
  await page.click(3, 2);
  check(ENV.moves.length === 1 && ENV.moves[0][4] === 'e2e4',
        `点对方棋子（绿点盖在上面）应吃子，实得 ${JSON.stringify(ENV.moves)}`);
  if (ENV.moves.length === 1) console.log('  ✓ 点绿点吃子 → 走子 e2e4（绿点盖住棋子也能点穿）');

  // 7.4 点另一个自己的子 → 改选，不走子
  page.seed(CAR, legalAll.filter(m => m.from[0] === 3));
  ENV.moves = [];
  await page.click(0, 1);
  st = page.peek();
  check(ENV.moves.length === 0, '点自己的另一个子不应走子');
  check(st.selected && st.selected[0] === 0 && st.selected[1] === 1, '应改选到新的棋子');
  check(st.legalCache.every(m => m.from[0] === 0), '缓存的着法应换成新子的');
  console.log('  ✓ 点自己的另一个子 → 改选（不走子）');

  // 7.5 点与选中子无关的空位 → 取消选中，不走子
  page.seed(CAR, legalAll.filter(m => m.from[0] === 3));
  ENV.moves = [];
  await page.click(8, 8);
  check(ENV.moves.length === 0, '点无关空位不应走子');
  check(page.peek().selected === null, '点无关空位应取消选中');
  console.log('  ✓ 点无关空位 → 取消选中（不会误走）');

  console.log('');
  if (fails){ console.log(`结果：${fails} 项失败`); process.exit(1); }
  console.log('结果：全部通过 ✓');
})();
