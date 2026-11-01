import { spawnSync } from 'node:child_process';
import { chmodSync, mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterAll, describe, expect, it } from 'vitest';
import { checkCss, checkRepo, checkTs, collectStrings, cookWithMap, decodeJsxAttribute, tokenizeCss } from './check-tokens.mjs';

const SCRIPT = fileURLToPath(new URL('./check-tokens.mjs', import.meta.url));

const reasons = (list) => list.map((v) => `${v.line}:${v.reason}`);

describe('checkCss — 위반', () => {
  it('16진수·rgb()·hsl() 색을 잡는다', () => {
    const r = checkCss('.a {\n  color: #fff;\n  background: rgba(0,0,0,.5);\n  border-color: hsl(10 20% 30%);\n}\n');
    expect(r).toHaveLength(3);
    expect(r.map((v) => v.line)).toEqual([2, 3, 4]);
  });

  it('색 속성의 이름 색을 잡는다', () => {
    expect(checkCss('.a { color: white; }')).toHaveLength(1);
    expect(checkCss('.a { border: 1px solid black; }')).toHaveLength(1);
  });

  it('허용 밖 길이를 잡는다(13px, 1.5px, em, rem, calc 안)', () => {
    const r = checkCss('.a { padding: 13px; box-shadow: inset 0 0 0 1.5px var(--x); letter-spacing: -0.03em; margin: 1rem; width: calc(100% - 8px); }');
    expect(r.map((v) => v.reason.split(' ')[3])).toEqual(['13px', '1.5px', '-0.03em', '1rem', '8px']);
  });

  it('시간·곡선 리터럴을 잡는다', () => {
    const r = checkCss('.a { transition: color .15s cubic-bezier(.2,.8,.2,1); animation: dg-in 450ms both; }');
    expect(r).toHaveLength(3);
  });

  it('z-index·line-height 숫자를 잡는다', () => {
    expect(checkCss('.a { z-index: 5; line-height: 1.6; }')).toHaveLength(2);
  });

  it('@media 블록 안의 선언은 검사한다', () => {
    const r = checkCss('@media (max-width: 767.98px) {\n  .a { padding: 16px; }\n}');
    expect(reasons(r)).toEqual(['2:허용 밖 길이 16px — 토큰(var(--…))을 쓰세요']);
  });

  it('지역 사용자 정의 속성에 리터럴을 넣어도 잡는다', () => {
    expect(checkCss('.a { --my-color: #123456; --gap: 12px; }')).toHaveLength(2);
  });
});

describe('checkCss — 통과', () => {
  it('토큰·허용 값만 쓴 규칙', () => {
    const css = `
.a {
  color: var(--ink);
  padding: var(--space-12) 0;
  border: 1px solid var(--line);
  outline: 2px solid var(--accent);
  margin: -1px;
  width: 100%;
  height: 100vh;
  min-height: 100dvh;
  grid-template-columns: var(--left-w) minmax(0, 1fr) var(--right-w);
  transition: background-color var(--dur-150) var(--ease);
  line-height: var(--lh-160);
  z-index: var(--z-modal);
  background: transparent;
  color: currentColor;
  font-size: var(--fs-13-5);
  line-height: var(--lh-20px);
  animation-delay: 0s;
  transform: scale(.97) rotate(180deg);
  opacity: .5;
  box-shadow: 0 0 0 2px var(--accent);
  background: color-mix(in srgb, var(--accent) 24%, transparent);
}`;
    expect(checkCss(css)).toEqual([]);
  });

  it('선택자·@media 조건의 값은 보지 않는다', () => {
    expect(checkCss('#fff .b:nth-child(2n+1) { color: var(--ink); }\n@media (min-width: 1200px) and (max-width: 1399.98px) { .a { color: var(--ink); } }')).toEqual([]);
  });

  it('@keyframes·@property 블록 안은 예외', () => {
    const css = '@property --dg-n { syntax: "<integer>"; inherits: false; initial-value: 0; }\n@keyframes dg-in { from { opacity: 0; transform: translateY(12px); } }\n@keyframes dg-ring { 0% { box-shadow: 0 0 0 2px #F04438; } }';
    expect(checkCss(css)).toEqual([]);
  });

  it('주석 안의 값과 url()·문자열은 보지 않는다', () => {
    expect(checkCss('/* color: #fff; padding: 13px */\n.a { background: url("x#fff.svg"); content: "13px #fff"; }')).toEqual([]);
  });

  it('줄 끝 tokens-ok 주석은 통과(이유 필요)', () => {
    expect(checkCss('.a { padding: 13px; /* tokens-ok: 원문 서식 고정 */ }')).toEqual([]); // 닫는 } 앞도 줄 끝으로 본다
    expect(checkCss('.a { padding: 13px; /* tokens-ok: 원문 서식 고정 */ margin: 14px; }')).toHaveLength(2); // 주석 뒤에 값이 더 있으면 줄 끝이 아니다
    expect(checkCss('.a {\n  padding: 13px; /* tokens-ok: 원문 서식 고정 */\n}')).toEqual([]);
    expect(checkCss('.a {\n  padding: 13px; /* tokens-ok: */\n}')).toHaveLength(1);
  });
});

describe('collectStrings', () => {
  it('문자열·템플릿 조각을 모으고 주석·정규식은 건너뛴다', () => {
    const src = "const a = 'x'; // '#fff'\n/* \"#000\" */ const re = /[\",\\n]/.test(s); const t = `a${b}c`;\nconst d = x / 2 / 3; const e = \"y\";";
    expect(collectStrings(src).map((s) => s.value)).toEqual(['x', 'a', 'c', 'y']);
  });
});

describe('checkTs', () => {
  it('따옴표 안의 색을 잡는다', () => {
    const src = [
      "const a = '#fff';",
      'const b = "#00845C";',
      'const c = `rgba(0,0,0,.4)`;',
      "const d = { color: 'hsl(10, 20%, 30%)' };",
      '<div style={{ background: "#FFF5D6" }} />',
    ].join('\n');
    expect(checkTs(src).map((v) => v.line)).toEqual([1, 2, 3, 4, 5]);
  });

  it('var(--토큰)·주석·따옴표 밖은 통과', () => {
    const src = [
      "const fg = 'var(--hi)';",
      "// const old = '#fff';",
      '<span>#FFF5D6</span>',
      "const id = '#section-2';",
      "const h = 'dg-i-check';",
    ].join('\n');
    expect(checkTs(src)).toEqual([]);
  });

  it('줄 끝 tokens-ok 주석은 통과', () => {
    expect(checkTs("const a = '#fff'; // tokens-ok: 외부 SVG 데이터")).toEqual([]);
    expect(checkTs("const a = '#fff'; // tokens-ok:")).toHaveLength(1);
  });
});

describe('checkRepo', () => {
  const root = mkdtempSync(join(tmpdir(), 'check-tokens-'));
  afterAll(() => rmSync(root, { recursive: true, force: true }));

  it('tokens.css·config/app.ts 는 빼고 src 아래를 검사한다', () => {
    mkdirSync(join(root, 'src/styles'), { recursive: true });
    mkdirSync(join(root, 'src/config'), { recursive: true });
    mkdirSync(join(root, 'src/components'), { recursive: true });
    writeFileSync(join(root, 'src/styles/tokens.css'), ':root { --ink: #141B2D; --space-13: 13px; }');
    writeFileSync(join(root, 'src/config/app.ts'), "export const CONFIG = { accent: '#00845C' };");
    writeFileSync(join(root, 'src/components/Bad.module.css'), '.a {\n  color: #fff;\n  padding: 13px;\n}\n');
    writeFileSync(join(root, 'src/components/Bad.tsx'), "export const x = '#fff';\n");
    writeFileSync(join(root, 'src/components/Good.module.css'), '.a { color: var(--ink); }');
    const r = checkRepo(root);
    expect(r.map((v) => `${v.file}:${v.line}`)).toEqual([
      'src/components/Bad.module.css:2',
      'src/components/Bad.module.css:3',
      'src/components/Bad.tsx:1',
    ]);
  });
});

/* ==========================================================================
   T1-fix1 회귀 — 검증 1차 M2·m1 (reports/T1-verify-1.md)
   ========================================================================== */

/**
 * 임시 저장소에 파일을 만들고 CLI(`node scripts/check-tokens.mjs <root>`)를 돌린다.
 * 검사기가 멈추면 20초 뒤 끊는다(status = null, signal = 'SIGTERM').
 * @param {Record<string, string>} files
 * @param {(root: string) => void} [prepare] CLI 전에 임시 저장소를 더 만지는 함수
 */
function runCli(files, prepare) {
  const root = mkdtempSync(join(tmpdir(), 'check-tokens-cli-'));
  try {
    for (const [rel, content] of Object.entries(files)) {
      mkdirSync(dirname(join(root, rel)), { recursive: true });
      writeFileSync(join(root, rel), content);
    }
    prepare?.(root);
    const r = spawnSync(process.execPath, [SCRIPT, root], { encoding: 'utf8', timeout: 20000 });
    return { status: r.status, signal: r.signal, out: `${r.stdout}${r.stderr}` };
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

describe('M2 회귀 — 검증 보고서의 우회 입력 6개는 CLI 종료 코드 1', () => {
  const cases = [
    ['지수 표기 길이 1e2px', 'src/components/Scientific.module.css', '.a { padding:1e2px; }', '허용 밖 길이 1e2px'],
    ['지수 표기 시간 2e-1s', 'src/components/ScientificTime.module.css', '.a { transition-duration:2e-1s; }', '시간 리터럴 2e-1s'],
    ['문자열 안의 가짜 tokens-ok 표식', 'src/components/FakeWaiver.ts', "export const value='#fff'; export const label='// tokens-ok: text';", '문자열 안 색 리터럴 #fff'],
    ['transition 축약형의 곡선 키워드', 'src/components/Curve.module.css', '.a { transition:opacity var(--dur-color) ease-in; }', "곡선 키워드 'ease-in'"],
    ['font 축약형의 /줄 간격', 'src/components/Font.module.css', '.a { font:var(--fw-regular) var(--fs-body)/1.55 var(--sans); }', 'font 축약형의 줄 간격 숫자 1.55'],
    ['.d.ts 파일의 색 문자열', 'src/components/Example.d.ts', "export type Accent = '#fff';", '문자열 안 색 리터럴 #fff'],
  ];
  for (const [name, rel, content, expected] of cases) {
    it(name, () => {
      const r = runCli({ [rel]: content });
      expect(r.status).toBe(1);
      expect(r.out).toContain(`${rel}:1: ${expected}`);
    });
  }
});

describe('m1 회귀 — 정규식 리터럴 안의 따옴표는 문자열이 아니다(CLI 종료 코드 0)', () => {
  it('if (...) 뒤의 정규식', () => {
    const r = runCli({ 'src/components/Regex.ts': "const ok = true;\nconst text = 'demo';\nif (ok) /'#fff'/.test(text);\n" });
    expect(r.out).toContain('위반 없음');
    expect(r.status).toBe(0);
  });
  it('대입식의 정규식', () => {
    const r = runCli({
      'src/components/RegexAssign.ts': "let re: RegExp;\nre = /'#fff'|\"rgb(0,0,0)\"/g;\nconst re2 = /#000/;\nexport const m = (s: string) => re.test(s) || re2.test(s);\n",
    });
    expect(r.out).toContain('위반 없음');
    expect(r.status).toBe(0);
  });
  it('함수에서도 같다(checkTs)', () => {
    expect(checkTs("if (ok) /'#fff'/.test(text);")).toEqual([]);
    expect(checkTs("x = /'#fff'/;\nconst y = { a: /\"hsl(0 0% 0%)\"/ };")).toEqual([]);
  });
});

describe('기존 통과 사례 — CLI 종료 코드 0', () => {
  it('tokens.css·config/app.ts 의 리터럴, 유효한 주석 예외, @keyframes·@property·@media 예외', () => {
    const r = runCli({
      'src/styles/tokens.css': ':root { --ink: #141B2D; --space-13: 13px; --ease: cubic-bezier(.2,.8,.2,1); --ease-linear: linear; --lh-155: 1.55; }',
      'src/config/app.ts': "export const CONFIG = { accent: '#00845C' } as const;\n",
      'src/components/Waiver.module.css': '.a {\n  padding: 13px; /* tokens-ok: 원문 서식 고정 */\n}\n.b { color: #fff; } /* tokens-ok: 외부 위젯 색 */\n',
      'src/components/Waiver.tsx': "export const a = '#fff'; // tokens-ok: 외부 SVG 데이터\nexport const B = () => <i style={{ color: '#000' }} />; /* tokens-ok: 외부 */\n",
      'src/components/Exempt.module.css': [
        '@property --dg-n { syntax: "<integer>"; inherits: false; initial-value: 0; }',
        '@keyframes dg-in { from { opacity: 0; transform: translateY(12px); animation-timing-function: ease-in; } }',
        '@media (min-width: 1200px) and (max-width: 1399.98px) { .a { padding: var(--space-12); } }',
        '.b { animation: dg-in var(--dur-enter) var(--ease) both; }',
      ].join('\n'),
    });
    expect(r.out).toContain('위반 없음');
    expect(r.status).toBe(0);
  });
});

describe('checkCss — 숫자 문법(지수 표기)', () => {
  it('지수 표기 길이·시간을 값으로 읽는다', () => {
    const r = checkCss('.a { margin: 1E+1px -.5e1px .2e1em; animation-delay: 1e2ms; width: calc(1e1% + 8e0px); }');
    expect(r.map((v) => v.reason.split(' — ')[0])).toEqual([
      '허용 밖 길이 1E+1px',
      '허용 밖 길이 -.5e1px',
      '허용 밖 길이 .2e1em',
      '시간 리터럴 1e2ms',
      '허용 밖 길이 8e0px',
    ]);
  });
  it('값이 0·1px·2px 이면 지수 표기여도 허용', () => {
    expect(checkCss('.a { margin: 0e3px 1e0px 2e0px -1e0px; transition-delay: 0e1s; }')).toEqual([]);
  });
  it('em 단위는 지수로 읽지 않는다(1em = 길이)', () => {
    expect(checkCss('.a { margin: 1em; }').map((v) => v.reason.split(' — ')[0])).toEqual(['허용 밖 길이 1em']);
  });
});

describe('checkCss — 곡선', () => {
  it('곡선 키워드 7개를 transition·animation 계열에서 잡는다', () => {
    for (const kw of ['ease', 'ease-in', 'ease-out', 'ease-in-out', 'linear', 'step-start', 'step-end']) {
      expect(checkCss(`.a { transition-timing-function: ${kw}; }`), kw).toHaveLength(1);
      expect(checkCss(`.a { animation: dg-spin var(--dur-spin) ${kw} infinite; }`), kw).toHaveLength(1);
    }
    expect(checkCss('.a { -webkit-animation-timing-function: linear; transition: color var(--dur-color) EASE-OUT; }')).toHaveLength(2);
  });
  it('cubic-bezier()·steps()·linear() 를 잡는다', () => {
    expect(checkCss('.a { transition: color var(--dur-color) cubic-bezier(.2,.8,.2,1); animation-timing-function: steps(4, end); }')).toHaveLength(2);
    expect(checkCss('.a { animation-timing-function: linear(0, .5 50%, 1); }')).toHaveLength(1);
  });
  it('사용자 정의 속성에 넣은 곡선 키워드도 잡는다', () => {
    expect(checkCss('.a { --spin-ease: linear; }')).toHaveLength(1);
  });
  it('var(--ease…) 토큰과 다른 속성의 같은 글자는 통과', () => {
    expect(checkCss('.a { transition: transform var(--dur-press) var(--ease), opacity var(--dur-color) var(--ease-io); animation: dg-spin var(--dur-spin) var(--ease-linear) infinite; background: linear-gradient(var(--a), var(--b)); }')).toEqual([]);
  });
});

describe('checkCss — 단위 없는 숫자', () => {
  it('font 축약형의 굵기와 /줄 간격', () => {
    const r = checkCss('.a { font: 700 var(--fs-body)/1.55 var(--sans); }');
    expect(r.map((v) => v.reason.split(' — ')[0])).toEqual(['font 축약형의 굵기 숫자 700', 'font 축약형의 줄 간격 숫자 1.55']);
  });
  it('font 축약형의 길이 줄 간격은 길이 규칙으로 잡는다', () => {
    expect(checkCss('.a { font: var(--fw-bold) var(--fs-body)/20px var(--sans); }').map((v) => v.reason.split(' — ')[0])).toEqual(['허용 밖 길이 20px']);
  });
  it('line-height·font-weight·z-index 숫자', () => {
    expect(checkCss('.a { line-height: 1.55; font-weight: 700; z-index: 40; }')).toHaveLength(3);
  });
  it('토큰으로 쓴 font 축약형·굵기·줄 간격은 통과', () => {
    expect(checkCss('.a { font: var(--fw-bold) var(--fs-body)/var(--lh-155) var(--sans); font-weight: var(--fw-semibold); line-height: var(--lh-body); }')).toEqual([]);
  });
});

describe('checkCss — 색과 예외 주석', () => {
  it('CSS 이름 색 148개(rebeccapurple 포함)를 색 속성·사용자 정의 속성에서 잡는다', () => {
    expect(checkCss('.a { color: RebeccaPurple; background: linear-gradient(white, var(--x)); --tone: red; fill: tan; }')).toHaveLength(4);
    expect(checkCss('.a { color: transparent; background: currentColor; grid-area: red; }')).toEqual([]);
  });
  it('문자열 안의 tokens-ok 는 예외가 아니다', () => {
    expect(checkCss('.a { color:#fff; content:"// tokens-ok: text"; }')).toHaveLength(1);
    expect(checkCss(".a { color:#fff; content:'/* tokens-ok: text */'; }")).toHaveLength(1);
  });
  it('예외 주석은 그 줄에만 걸린다', () => {
    expect(checkCss('.a { color: #fff; } /* tokens-ok: 이유 */\n.b { color: #000; }').map((v) => v.line)).toEqual([2]);
  });
  it('주석 안·url()·문자열의 값은 보지 않는다', () => {
    expect(checkCss(".a { background: url(data:image/svg+xml;utf8,<svg fill='%23fff'>); mask: url('#m'); }")).toEqual([]);
  });
});

describe('checkTs — TypeScript 파서', () => {
  it('이스케이프로 쓴 색도 잡는다', () => {
    expect(checkTs(String.raw`const a = '#fff'; const b = '\x23abcdef'; const c = '\u{23}000';`)).toHaveLength(3);
  });
  it('여러 줄 템플릿은 색이 있는 줄을 알려 준다', () => {
    const src = 'const a = `\n#fff\n${b} rgba(0,0,0,.5)\n`;';
    expect(checkTs(src).map((v) => v.line)).toEqual([2, 3]);
  });
  it('중첩 템플릿·JSX 속성 문자열을 잡는다', () => {
    expect(checkTs('const a = `color: ${x ? "#fff" : `${"#000"}`}`;')).toHaveLength(2);
    expect(checkTs('const A = () => <div data-c="#fff" style={{ color: `rgb(0 0 0)` }} />;')).toHaveLength(2);
  });
  it('JSX 글자는 문자열이 아니고, 그 안의 // 는 주석이 아니다', () => {
    expect(checkTs('const A = () => <span>#FFF5D6</span>;')).toEqual([]);
    expect(checkTs("const A = () => <span>// tokens-ok: 글자</span>; const y = '#fff';")).toHaveLength(1);
  });
  it('JSX 주석 예외 {/* tokens-ok: … */} 는 통과', () => {
    expect(checkTs("const A = () => (\n  <i style={{ color: '#fff' }} /> {/* tokens-ok: 외부 위젯 */}\n);")).toEqual([]);
  });
  it('주석이 줄 끝이 아니거나 이유가 없으면 예외가 아니다', () => {
    expect(checkTs("const a = '#fff'; /* tokens-ok: 이유 */ foo();")).toHaveLength(1);
    expect(checkTs("const a = '#fff'; /* tokens-ok: */")).toHaveLength(1);
    expect(checkTs("/* tokens-ok: 위 줄 */\nconst a = '#fff';")).toHaveLength(1);
  });
  it('JSDoc·주석 안의 색은 보지 않는다', () => {
    expect(checkTs("/** 예: '#fff' */\nexport const a = 1;\n// '#000'\n")).toEqual([]);
  });
  it('.ts 파일은 JSX 없이 읽는다(형 단언 <T>x)', () => {
    expect(checkTs("const a = <string>'#fff';", 'src/a.ts')).toHaveLength(1);
  });
});

describe('collectStrings — 정규식·주석 제외', () => {
  it('if 문·대입식 뒤의 정규식 안 따옴표는 문자열이 아니다', () => {
    expect(collectStrings("if (ok) /'#fff'/.test(t); x = /\"#000\"/; const s = 'y';").map((s) => s.value)).toEqual(['y']);
  });
});

describe('checkRepo — .d.ts 도 검사한다', () => {
  const root = mkdtempSync(join(tmpdir(), 'check-tokens-dts-'));
  afterAll(() => rmSync(root, { recursive: true, force: true }));
  it('src/**/*.d.ts', () => {
    mkdirSync(join(root, 'src/types'), { recursive: true });
    writeFileSync(join(root, 'src/types/accent.d.ts'), "export type Accent = '#fff';\n");
    expect(checkRepo(root).map((v) => `${v.file}:${v.line}`)).toEqual(['src/types/accent.d.ts:1']);
  });
});

/* ==========================================================================
   T1-fix2 회귀 — 검증 2차 m2 (reports/T1-verify-2.md)
   정상 코드에서 검사기가 예외·멈춤 없이 끝나야 한다.
   ========================================================================== */

/** 결정적 의사 난수(mulberry32) — 무작위 입력을 매번 같게 만든다 */
function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const randomText = (next, alphabet, maxLen) =>
  Array.from({ length: Math.floor(next() * (maxLen + 1)) }, () => alphabet[Math.floor(next() * alphabet.length)]).join('');

/** 태그 템플릿·JSX 속성에서는 정상이지만 JS 이스케이프로는 잘못된 모양 */
const INVALID_ESCAPES = [
  '\\u{', '\\u{41', '\\u{}', '\\u{-1}', '\\u{1g}', '\\u{ 41}', '\\u{110000}', '\\u{FFFFFFFFFFFF}',
  '\\u', '\\u12', '\\uZZ', '\\x', '\\x4', '\\xZZ', '\\01', '\\1', '\\8', '\\9',
];

describe('m2 회귀 — 검증 보고서의 두 입력은 CLI 종료 코드 0', () => {
  it('태그 템플릿의 raw 조각: String.raw`\\u{110000}`', () => {
    const r = runCli({ 'src/components/RawTemplate.ts': 'export const value = String.raw`\\u{110000}`;\n' });
    expect(r.out).toContain('위반 없음');
    expect(r.out).not.toContain('Error');
    expect(r.status).toBe(0);
  });
  it('JSX 속성 문자열: <span title="\\u{ZZ}">', () => {
    const r = runCli({ 'src/components/RawAttribute.tsx': 'export const Value = () => <span title="\\u{ZZ}">text</span>;\n' });
    expect(r.out).toContain('위반 없음');
    expect(r.out).not.toContain('Error');
    expect(r.status).toBe(0);
  });
});

describe('m2 회귀 — 잘못된 이스케이프 모양 모음도 예외·멈춤 없이 끝난다', () => {
  const sub = '${1}';
  const tsSource = INVALID_ESCAPES.flatMap((s, i) => [
    `export const t${i} = String.raw\`${s}\`;`, // 치환 없는 템플릿
    `export const h${i} = String.raw\`${s}${sub}x\`;`, // head
    `export const m${i} = String.raw\`a${sub}${s}${sub}b\`;`, // middle
    `export const e${i} = String.raw\`a${sub}${s}\`;`, // tail
  ]).join('\n');
  const tsxSource = INVALID_ESCAPES.map((s, i) => `export const J${i} = () => <i title="${s}" data-k='${s}' />;`).join('\n');

  it('입력은 TypeScript 문법 오류가 없는 정상 코드다', async () => {
    const { default: ts } = await import('typescript');
    for (const [fileName, src] of [['a.ts', tsSource], ['b.tsx', tsxSource]]) {
      const r = ts.transpileModule(src, { fileName, reportDiagnostics: true, compilerOptions: { jsx: ts.JsxEmit.ReactJSX } });
      expect(r.diagnostics.map((d) => d.messageText), fileName).toEqual([]);
    }
  });
  it('CLI 종료 코드 0 — `\\u{41` 처럼 닫는 괄호가 없어도 멈추지 않는다', () => {
    const r = runCli({ 'src/components/Shapes.ts': `${tsSource}\n`, 'src/components/Shapes.tsx': `${tsxSource}\n` });
    expect(r.signal).toBeNull();
    expect(r.out).toContain('위반 없음');
    expect(r.status).toBe(0);
  });
  it('문법 오류인 일반 문자열·템플릿도 예외 없이 TypeScript 값으로 검사한다(위치는 리터럴 시작 줄)', () => {
    for (const s of INVALID_ESCAPES) {
      expect(() => checkTs(`const a = '${s}'; const b = \`${s}\`;`, 'src/a.ts'), s).not.toThrow();
    }
    expect(checkTs("const a = '\\u{ZZ} #fff';", 'src/a.ts').map((v) => v.line)).toEqual([1]);
    expect(checkTs('const a = 1;\nconst b = `\\u{110000}\n#fff`;', 'src/a.ts').map((v) => v.line)).toEqual([2]);
  });
});

describe('m2 — 태그 템플릿: 원문(strings.raw)과 푼 값(strings[i])을 나눠 본다', () => {
  it('collectStrings 가 종류와 실행 시 값을 알려 준다', () => {
    const src = 'const a = String.raw`\\u{110000}`; const b = css`\\x23fff`; const c = `\\x23fff`; const d = `a``b`;';
    expect(collectStrings(src, 'src/a.ts').map((s) => [s.kind, s.value, s.raw])).toEqual([
      ['tagged-template', null, '\\u{110000}'], // 잘못된 이스케이프 → strings[0] 은 undefined, raw 만 있다
      ['tagged-template', '#fff', '\\x23fff'],
      ['template', '#fff', '\\x23fff'],
      ['template', 'a', 'a'], // 태그 자리의 템플릿은 일반 템플릿
      ['tagged-template', 'b', 'b'],
    ]);
  });
  it('푼 값의 색을 잡는다(이스케이프 색 포함)', () => {
    expect(checkTs('const a = css`color: \\x23fff`;', 'src/a.ts')).toHaveLength(1);
    expect(checkTs('const a = css`${x} \\u{72}gb(0 0 0)`;', 'src/a.ts')).toHaveLength(1);
  });
  it('푼 값이 없으면 원문의 색을 잡는다', () => {
    expect(checkTs('const a = String.raw`\\u{110000} #fff`;', 'src/a.ts')).toHaveLength(1);
    expect(checkTs('const a = tag`${x}\\u{ZZ} rgb(0 0 0)`;', 'src/a.ts')).toHaveLength(1);
  });
  it('원문과 푼 값의 같은 색은 한 번만 센다', () => {
    expect(checkTs('const a = String.raw`#fff ${x} #000`;', 'src/a.ts')).toHaveLength(2);
  });
  it('여러 줄 태그 템플릿은 색이 있는 줄을 알려 주고, 그 줄의 예외 주석이 걸린다', () => {
    const src = 'const a = String.raw`\\u{ZZ}\n#fff\n${x} rgb(0 0 0)`;';
    expect(checkTs(src, 'src/a.ts').map((v) => v.line)).toEqual([2, 3]);
    expect(checkTs('const a = String.raw`\\u{ZZ} #fff`; // tokens-ok: 외부 형식', 'src/a.ts')).toEqual([]);
  });
});

describe('m2 — JSX 속성 문자열은 JSX 규칙으로 읽는다', () => {
  it('역슬래시는 이스케이프가 아니다(실행 시 값에 색이 없다)', () => {
    expect(checkTs('const A = () => <span title="\\x23fff" data-c="\\u{23}000" />;')).toEqual([]);
  });
  it('중괄호 안의 JS 문자열은 JS 규칙이다', () => {
    expect(checkTs('const A = () => <span title={"\\x23fff"} />;')).toHaveLength(1);
  });
  it('문자 참조(&#35; &#x23; &#40;)로 만든 색을 잡는다', () => {
    expect(checkTs('const A = () => <span title="&#x23;fff" data-a="&#35;000" data-b="rgb&#40;0 0 0)" />;')).toHaveLength(3);
  });
  it('기존처럼 그냥 쓴 색도 잡고, 여러 줄 속성은 색이 있는 줄을 알려 준다', () => {
    expect(checkTs('const A = () => <div data-c="#fff" />;')).toHaveLength(1);
    expect(checkTs('const A = () => (\n  <span\n    title="a\n#fff"\n  />\n);').map((v) => v.line)).toEqual([4]);
  });
  it('decodeJsxAttribute — 범위 밖·모르는 참조는 그대로 두고 예외가 없다', () => {
    expect(decodeJsxAttribute('&#x110000;&#99999999999999999999;&nbsp;&#xZZ;&amp;&#35;').value).toBe('&#x110000;&#99999999999999999999;&nbsp;&#xZZ;&#');
    const { value, map } = decodeJsxAttribute('a&#x23;b');
    expect(value).toBe('a#b');
    expect(map).toEqual([0, 1, 7]);
  });
});

describe('m2 — cookWithMap: 잘못된 이스케이프는 null, 예외 없음', () => {
  it('잘못된 모양은 템플릿 규칙에서 모두 null', () => {
    for (const s of INVALID_ESCAPES) expect(cookWithMap(s, { template: true }), s).toBeNull();
    expect(cookWithMap('ab\\')).toBeNull(); // 끝에 홀로 남은 역슬래시
  });
  it('올바른 이스케이프는 값과 위치를 만든다', () => {
    expect(cookWithMap('a\\u{1F600}\\x23\\u0041\\0\\n')).toEqual({ cooked: 'a\u{1F600}#A\0\n', map: [0, 1, 1, 10, 14, 20, 22] });
    expect(cookWithMap('\\101\\8', { template: false })?.cooked).toBe('A8'); // 일반 문자열의 옛 8진·\8
  });
  it('무작위 입력 4000개: 템플릿·문자열 모두 JS 엔진과 같은 값을 만들고, 잘못된 것만 null', () => {
    const next = rng(20261101);
    const alphabet = ['\\', '\\', 'u', 'x', '{', '}', '0', '1', '3', '7', '8', '9', 'a', 'F', 'g', 'Z', '-', ' ', '#', '\n', '\r', '\u2028'];
    let compared = 0;
    for (let n = 0; n < 4000; n++) {
      const raw = randomText(next, alphabet, 14);
      for (const template of [true, false]) {
        const got = cookWithMap(raw, { template });
        if (got) {
          expect(got.map.length).toBe(got.cooked.length);
          expect(got.map.every((p) => p >= 0 && p < raw.length)).toBe(true);
        }
        let engine;
        try {
          // 템플릿: 태그 함수가 받는 strings[0](잘못된 이스케이프면 undefined). 문자열: 비엄격 모드 문자열 값
          engine = template ? new Function(`return ((s) => s[0])\`${raw}\`;`)() : new Function(`return "${raw}";`)();
        } catch {
          continue; // JS 에서도 문법 오류(끝나지 않은 리터럴 등)
        }
        compared++;
        expect(got?.cooked ?? undefined, JSON.stringify({ raw, template })).toBe(engine);
      }
    }
    expect(compared).toBeGreaterThan(2000);
  });
  it('무작위 원문을 태그 템플릿·JSX 속성에 넣어도 checkTs 가 예외 없이 끝난다', () => {
    const next = rng(7);
    const alphabet = ['\\', 'u', 'x', '{', '}', '0', '1', '9', 'f', 'Z', '#', '&', ';', '(', 'r', 'g', 'b', '\n'];
    for (let n = 0; n < 300; n++) {
      const raw = randomText(next, alphabet, 16);
      const src = `export const a = String.raw\`${raw}\`;\nexport const B = () => <i title="${raw}" />;\nexport const c = '${raw}';`;
      expect(() => checkTs(src, 'src/x.tsx'), JSON.stringify(raw)).not.toThrow();
    }
  });
});

describe('m2 — 이스케이프로 쓴 색 검출은 그대로', () => {
  it('일반 문자열·템플릿', () => {
    expect(checkTs(String.raw`const a = '\x23fff'; const b = '\u0023000'; const c = '\u{23}abc'; const d = ${'`'}\x72gb(0 0 0)${'`'};`)).toHaveLength(4);
  });
});

describe('checkRepo — 파일을 읽지 못해도 조용히 통과하지 않는다', () => {
  it('깨진 심볼릭 링크가 있어도 다른 파일의 위반을 알린다(전에는 위반 없음·종료 코드 0)', () => {
    const r = runCli({ 'src/components/Bad.ts': "export const x = '#fff';\n" }, (root) =>
      symlinkSync(join(root, 'nowhere.ts'), join(root, 'src/components/Broken.ts')),
    );
    expect(r.out).toContain('src/components/Bad.ts:1: 문자열 안 색 리터럴 #fff');
    expect(r.status).toBe(1);
  });
  it('깨진 심볼릭 링크만 있으면 위반 없음', () => {
    const r = runCli({ 'src/components/Good.ts': "export const x = 'var(--ink)';\n" }, (root) =>
      symlinkSync(join(root, 'nowhere.ts'), join(root, 'src/components/Broken.ts')),
    );
    expect(r.status).toBe(0);
  });
  const canDropPermissions = process.platform !== 'win32' && process.getuid?.() !== 0;
  it.skipIf(!canDropPermissions)('읽을 수 없는 파일·폴더는 경로를 알리고 종료 코드 2, 나머지는 끝까지 검사한다', () => {
    const root = mkdtempSync(join(tmpdir(), 'check-tokens-perm-'));
    const lockedDir = join(root, 'src/locked');
    try {
      mkdirSync(lockedDir, { recursive: true });
      mkdirSync(join(root, 'src/components'), { recursive: true });
      writeFileSync(join(root, 'src/components/Bad.ts'), "export const x = '#fff';\n");
      writeFileSync(join(root, 'src/components/Locked.ts'), "export const y = '#000';\n");
      chmodSync(join(root, 'src/components/Locked.ts'), 0o000);
      chmodSync(lockedDir, 0o000);
      const r = spawnSync(process.execPath, [SCRIPT, root], { encoding: 'utf8', timeout: 20000 });
      const out = `${r.stdout}${r.stderr}`;
      expect(out).toContain('src/components/Bad.ts:1: 문자열 안 색 리터럴 #fff');
      expect(out).toMatch(/src\/components\/Locked\.ts: 검사하지 못함 — EACCES/);
      expect(out).toMatch(/src\/locked: 읽지 못함 — EACCES/);
      expect(r.status).toBe(2);
    } finally {
      chmodSync(lockedDir, 0o755);
      rmSync(root, { recursive: true, force: true });
    }
  });
});

describe('tokenizeCss — 이스케이프 코드 포인트 범위(CSS Syntax 3 §4.3.7)', () => {
  it('0·서로게이트·0x10FFFF 초과는 U+FFFD', () => {
    expect(tokenizeCss('a\\d800 b').find((t) => t.type === 'ident')?.value).toBe('a\uFFFDb');
    expect(tokenizeCss('\\110000').find((t) => t.type === 'ident')?.value).toBe('\uFFFD');
    expect(tokenizeCss('\\72 ed').find((t) => t.type === 'ident')?.value).toBe('red');
  });
});
