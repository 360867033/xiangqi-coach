// 在 Node 里模拟浏览器环境，抽出前端的中文记谱函数与 Python 结果对拍
const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'), 'utf-8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

// ---- 极简 DOM 桩 ----
const elStub = () => ({
  innerHTML: '', textContent: '', style: {}, value: '', disabled: false,
  dataset: {}, scrollTop: 0, scrollHeight: 0,
  classList: { toggle(){}, add(){}, remove(){} },
  addEventListener(){}, appendChild(){}, insertAdjacentHTML(){}, onclick: null,
});
global.document = {
  getElementById: () => elStub(),
  querySelector: () => elStub(),
  querySelectorAll: () => [],
  createElement: () => elStub(),
  addEventListener(){},          // 顶层注册的键盘监听（Esc 退出编辑）需要这个桩
};
global.window = {};
global.fetch = async () => ({ json: async () => ({}), ok: true, body: null });
global.alert = () => {};
global.prompt = () => null;
global.navigator = { clipboard: { writeText: async () => {} } };

// 屏蔽 init 的异步启动（需要网络）
const patched = script.replace(/\(async function init\(\)[\s\S]*\}\)\(\);\s*$/,
                               '/* init skipped */');
const fn = new Function(patched + '\nreturn { fenToBoard, guessChinese, boardToFen, isRed };');
const api = fn();

// ---- 对拍 ----
const cases = JSON.parse(fs.readFileSync(path.join(__dirname, '_notation_cases.json'), 'utf-8'));
let total = 0, bad = 0;
const fails = [];
for (const c of cases) {
  for (const m of c.moves) {
    const u = m.uci;
    const from = [+u[1], u.charCodeAt(0) - 97];
    const to = [+u[3], u.charCodeAt(2) - 97];
    const got = api.guessChinese(c.fen, from, to);
    total++;
    if (got !== m.chinese) {
      bad++;
      if (fails.length < 12) fails.push(`${c.fen}  ${u}  JS=${got}  PY=${m.chinese}`);
    }
  }
}
console.log(`对拍着法总数: ${total}`);
console.log(`不一致: ${bad}`);
fails.forEach(f => console.log('  ! ' + f));

// FEN 往返测试
let fenBad = 0;
for (const c of cases) {
  const b = api.fenToBoard(c.fen);
  const back = api.boardToFen(b, c.fen.trim().split(/\s+/)[1] !== 'b');
  if (back !== c.fen) { fenBad++; if (fenBad < 4) console.log('  FEN往返失败:', c.fen, '->', back); }
}
console.log(`FEN 往返不一致: ${fenBad}`);
process.exit(bad || fenBad ? 1 : 0);
