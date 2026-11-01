#!/usr/bin/env node
/* ==========================================================================
   토큰 규칙 검사 — `npm run check:tokens`
   BRIEF §3 '토큰 규칙':
   - src/**\/*.css (src/styles/tokens.css 제외) — CSS 토큰 단위로 읽는다(CSS Syntax 3 방식).
       · 색 리터럴: 16진수(#rgb·#rgba·#rrggbb·#rrggbbaa), rgb()/rgba()/hsl()/hsla()/hwb()/lab()/
         lch()/oklab()/oklch()/color(), 색 속성·사용자 정의 속성의 이름 색(CSS 이름 색 148개)
       · 허용 밖 길이 — 허용: 0, ±1px, ±2px, %, fr, vh/vw(dvh·svh·lvh·dvw·svw·lvw 포함), var()
         숫자는 지수 표기까지 읽는다(1e2px = 100px, 2e-1s = .2s).
       · 시간 리터럴(.2s, 120ms …, 0 제외)
       · 곡선: cubic-bezier()·steps() 는 어디서나, 곡선 키워드(ease, ease-in, ease-out, ease-in-out,
         linear, step-start, step-end)와 linear() 는 transition·animation 계열·사용자 정의 속성에서
         금지 — var(--ease…) 토큰만 쓴다.
       · 단위 없는 숫자: z-index, line-height, font-weight, font 축약형(굵기, '/' 뒤 줄 간격)
       · 예외: 선택자·@media 등 at-rule 조건, @keyframes·@property 블록 안
   - src/**\/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs} (src/config/app.ts 제외, .d.ts 포함)
       · TypeScript 파서로 문자열·템플릿 리터럴만 골라(정규식 리터럴·주석·JSX 글자는 제외)
         실행 시 값에서 색 리터럴(16진수, rgb(·rgba(·hsl(·hsla(·hwb(·lab(·lch(·oklab(·oklch()을 잡는다.
         · 일반 문자열·템플릿: 이스케이프를 푼 값(TypeScript 의 node.text)
         · 태그가 붙은 템플릿(String.raw`…`, css`…`): 원문 그대로(strings.raw)와, 이스케이프가 모두
           올바를 때만 생기는 푼 값(strings[i]) 둘 다
         · JSX 속성 문자열(<a title="…">): JSX 규칙 — 역슬래시는 이스케이프가 아니고 HTML 문자 참조
           (&#35; &#x23; &amp; &quot; &apos; &lt; &gt;)만 풀린다
         잘못된 이스케이프가 있어도 예외를 던지지 않는다. 원문 위치 대응을 만들 수 없으면 TypeScript 값을
         검사하고 위치는 그 리터럴이 시작하는 줄로 알린다.
   - 예외: 위반이 있는 줄 끝에 **실제 주석** `tokens-ok: <이유>` 가 있으면 통과한다.
       CSS 는 블록 주석, TS 는 줄 주석(// …) 또는 블록 주석 안에 `tokens-ok: 이유` 를 쓴다.
       주석 뒤에는 공백·`;`·`}` 만 올 수 있다. 문자열 안의 같은 글자는 주석이 아니므로 무효.
   - 종료 코드: 0 = 위반 없음, 1 = 위반 있음(파일:줄과 이유를 출력),
       2 = 읽거나 검사하지 못한 파일·폴더가 있음(그 경로와 오류를 출력하고, 나머지 파일은 끝까지 검사한다).
   ========================================================================== */

import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import ts from 'typescript';

const CSS_EXCLUDE = new Set(['src/styles/tokens.css']);
const TS_EXCLUDE = new Set(['src/config/app.ts']);
const CSS_FILE_RE = /\.css$/;
const TS_FILE_RE = /\.(ts|tsx|mts|cts|js|jsx|mjs|cjs)$/;

/* ---------- 공통 ---------- */

/** 줄 시작 위치 목록 */
function lineStarts(text) {
  const out = [0];
  for (let i = 0; i < text.length; i++) if (text.charCodeAt(i) === 10) out.push(i + 1);
  return out;
}

/** offset → 1부터 세는 줄 번호 */
function lineAt(starts, offset) {
  let lo = 0;
  let hi = starts.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (starts[mid] <= offset) lo = mid;
    else hi = mid - 1;
  }
  return lo + 1;
}

const WAIVER_RE = /tokens-ok:\s*(.*)$/s;

/** 주석 글자에 이유가 있는 tokens-ok 가 들어 있는지 */
function isWaiverComment(commentText) {
  const body = commentText.startsWith('/*') ? commentText.slice(2, -2) : commentText.replace(/^\/\//, '');
  const m = WAIVER_RE.exec(body);
  return !!m && m[1].trim().length > 0;
}

/**
 * 실제 주석 목록에서 tokens-ok 예외가 걸린 줄 번호 모음을 만든다.
 * 주석이 그 줄에서 시작하고 끝나며, 주석 뒤에는 공백·`;`·`}` 만 있어야 한다(줄 끝 주석).
 * @param {string} text
 * @param {{ start: number, end: number }[]} comments
 */
function waivedLines(text, comments) {
  const starts = lineStarts(text);
  const out = new Set();
  for (const c of comments) {
    const raw = text.slice(c.start, c.end);
    if (!isWaiverComment(raw)) continue;
    const line = lineAt(starts, c.start);
    if (lineAt(starts, Math.max(c.start, c.end - 1)) !== line) continue; // 여러 줄 주석은 인정하지 않는다
    const lineEnd = line < starts.length ? starts[line] - 1 : text.length;
    const rest = text.slice(c.end, lineEnd);
    if (/^[\s;}]*$/.test(rest)) out.add(line);
  }
  return out;
}

const HEX_RE = /(?<![\w&#-])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![0-9a-zA-Z_-])/g;
const TS_COLOR_FN_RE = /(?<![\w-])(rgba?|hsla?|hwb|lab|lch|oklab|oklch)\(/gi;

/* ---------- CSS: 토큰 나누기 ---------- */

const isDigit = (c) => c >= '0' && c <= '9';
const isHexDigit = (c) => /^[0-9a-fA-F]$/.test(c);
const isNameStart = (c) => c !== undefined && (/[A-Za-z_]/.test(c) || c.charCodeAt(0) >= 0x80);
const isNameChar = (c) => c !== undefined && (isNameStart(c) || isDigit(c) || c === '-');
const isWs = (c) => c === ' ' || c === '\t' || c === '\n' || c === '\r' || c === '\f';
const validEscape = (a, b) => a === '\\' && b !== '\n' && b !== undefined;

/** 이 위치에서 식별자가 시작하는가(CSS Syntax 3 §4.3.9) */
function startsIdent(s, i) {
  const c = s[i];
  if (c === '-') return isNameStart(s[i + 1]) || s[i + 1] === '-' || validEscape(s[i + 1], s[i + 2]);
  if (isNameStart(c)) return true;
  return validEscape(c, s[i + 1]);
}

/** 이 위치에서 숫자가 시작하는가(§4.3.10) */
function startsNumber(s, i) {
  const c = s[i];
  if (c === '+' || c === '-') return isDigit(s[i + 1]) || (s[i + 1] === '.' && isDigit(s[i + 2]));
  if (c === '.') return isDigit(s[i + 1]);
  return isDigit(c);
}

/** 식별자 이름을 읽는다(이스케이프 포함). 반환: { end, name } */
function readName(s, i) {
  let name = '';
  while (i < s.length) {
    const c = s[i];
    if (isNameChar(c)) { name += c; i++; continue; }
    if (validEscape(c, s[i + 1])) {
      let j = i + 1;
      if (isHexDigit(s[j])) {
        let hex = '';
        while (hex.length < 6 && isHexDigit(s[j])) hex += s[j++];
        if (isWs(s[j])) j++;
        const cp = parseInt(hex, 16);
        // §4.3.7: 0, 서로게이트, 0x10FFFF 초과는 U+FFFD
        name += String.fromCodePoint(cp === 0 || (cp >= 0xd800 && cp <= 0xdfff) || cp > 0x10ffff ? 0xfffd : cp);
      } else {
        name += s[j++];
      }
      i = j;
      continue;
    }
    break;
  }
  return { end: i, name };
}

/** 숫자를 읽는다(부호·소수·지수). 반환: { end, value } */
function readNumber(s, i) {
  const start = i;
  if (s[i] === '+' || s[i] === '-') i++;
  while (isDigit(s[i])) i++;
  if (s[i] === '.' && isDigit(s[i + 1])) {
    i++;
    while (isDigit(s[i])) i++;
  }
  if ((s[i] === 'e' || s[i] === 'E') && (isDigit(s[i + 1]) || ((s[i + 1] === '+' || s[i + 1] === '-') && isDigit(s[i + 2])))) {
    i += 2;
    while (isDigit(s[i])) i++;
  }
  return { end: i, value: Number(s.slice(start, i)), raw: s.slice(start, i) };
}

/**
 * CSS 텍스트를 토큰으로 나눈다.
 * 토큰 type: ws, comment, string, url, number, percentage, dimension, ident, function, at, hash,
 *            delim, ( ) [ ] { } : ; ,
 * @returns {{ type: string, start: number, end: number, value?: any, unit?: string, raw?: string }[]}
 */
export function tokenizeCss(s) {
  const out = [];
  let i = 0;
  const n = s.length;
  const push = (type, start, end, extra = {}) => out.push({ type, start, end, ...extra });
  while (i < n) {
    const c = s[i];
    const start = i;
    if (c === '/' && s[i + 1] === '*') {
      const e = s.indexOf('*/', i + 2);
      i = e < 0 ? n : e + 2;
      push('comment', start, i);
      continue;
    }
    if (isWs(c)) {
      while (i < n && isWs(s[i])) i++;
      push('ws', start, i);
      continue;
    }
    if (c === '"' || c === "'") {
      i++;
      while (i < n && s[i] !== c && s[i] !== '\n') {
        if (s[i] === '\\') i++;
        i++;
      }
      if (s[i] === c) i++;
      push('string', start, i);
      continue;
    }
    if (startsNumber(s, i)) {
      const num = readNumber(s, i);
      i = num.end;
      if (startsIdent(s, i)) {
        const u = readName(s, i);
        i = u.end;
        push('dimension', start, i, { value: num.value, unit: u.name.toLowerCase(), raw: s.slice(start, i) });
      } else if (s[i] === '%') {
        i++;
        push('percentage', start, i, { value: num.value, raw: s.slice(start, i) });
      } else {
        push('number', start, i, { value: num.value, raw: num.raw });
      }
      continue;
    }
    if (startsIdent(s, i)) {
      const nm = readName(s, i);
      i = nm.end;
      if (s[i] === '(') {
        if (nm.name.toLowerCase() === 'url') {
          let j = i + 1;
          while (isWs(s[j])) j++;
          if (s[j] !== '"' && s[j] !== "'") {
            // 따옴표 없는 url(…) 은 통째로 하나의 토큰
            while (j < n && s[j] !== ')') {
              if (s[j] === '\\') j++;
              j++;
            }
            i = Math.min(j + 1, n);
            push('url', start, i);
            continue;
          }
        }
        i++;
        push('function', start, i, { value: nm.name.toLowerCase() });
      } else {
        push('ident', start, i, { value: nm.name });
      }
      continue;
    }
    if (c === '@' && startsIdent(s, i + 1)) {
      const nm = readName(s, i + 1);
      i = nm.end;
      push('at', start, i, { value: nm.name.toLowerCase() });
      continue;
    }
    if (c === '#' && (isNameChar(s[i + 1]) || validEscape(s[i + 1], s[i + 2]))) {
      const nm = readName(s, i + 1);
      i = nm.end;
      push('hash', start, i, { value: nm.name });
      continue;
    }
    if ('()[]{}:;,'.includes(c)) {
      i++;
      push(c, start, i);
      continue;
    }
    i++;
    push('delim', start, i, { value: c });
  }
  return out;
}

/* ---------- CSS: 규칙 ---------- */

/** CSS Color 4 이름 색 148개 */
const NAMED_COLORS = new Set(`aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue
blueviolet brown burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue
darkcyan darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid
darkred darksalmon darkseagreen darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink
deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite gold
goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki lavender lavenderblush
lawngreen lemonchiffon lightblue lightcoral lightcyan lightgoldenrodyellow lightgray lightgreen lightgrey
lightpink lightsalmon lightseagreen lightskyblue lightslategray lightslategrey lightsteelblue lightyellow lime
limegreen linen magenta maroon mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen
mediumslateblue mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin
navajowhite navy oldlace olive olivedrab orange orangered orchid palegoldenrod palegreen paleturquoise
palevioletred papayawhip peachpuff peru pink plum powderblue purple rebeccapurple red rosybrown royalblue
saddlebrown salmon sandybrown seagreen seashell sienna silver skyblue slateblue slategray slategrey snow
springgreen steelblue tan teal thistle tomato turquoise violet wheat white whitesmoke yellow yellowgreen`.split(/\s+/));

/** 이름 색을 검사하는 속성(색을 받는 속성 + 사용자 정의 속성) */
const COLOR_PROPS = /^(color|background(-.+)?|border(-.+)?|outline(-.+)?|fill|stroke|box-shadow|text-shadow|text-decoration(-.+)?|text-emphasis(-.+)?|caret-color|accent-color|column-rule(-.+)?|stop-color|flood-color|lighting-color|scrollbar-color|mask(-.+)?|filter|backdrop-filter|-webkit-text-fill-color|-webkit-text-stroke(-.+)?|-webkit-tap-highlight-color|--.+)$/i;

const COLOR_FNS = new Set(['rgb', 'rgba', 'hsl', 'hsla', 'hwb', 'lab', 'lch', 'oklab', 'oklch', 'color', 'device-cmyk']);

const LENGTH_UNITS = new Set([
  'px', 'em', 'rem', 'ch', 'ex', 'ic', 'cap', 'lh', 'rlh', 'rex', 'rch', 'ric', 'rcap', 'vmin', 'vmax', 'vi', 'vb',
  'svmin', 'svmax', 'lvmin', 'lvmax', 'dvmin', 'dvmax', 'svi', 'svb', 'lvi', 'lvb', 'dvi', 'dvb',
  'cqw', 'cqh', 'cqi', 'cqb', 'cqmin', 'cqmax', 'pt', 'pc', 'cm', 'mm', 'in', 'q',
]);
/* 허용 단위: vh·vw·dvh·svh·lvh·dvw·svw·lvw(LENGTH_UNITS 에 없음), fr, 각도·해상도 등 길이·시간이 아닌 단위 */
const TIME_UNITS = new Set(['s', 'ms']);

/** 곡선 키워드를 막는 속성: transition·animation 계열 + 사용자 정의 속성 */
const MOTION_PROPS = /^(-webkit-)?(transition|animation)(-.+)?$|^--.+$/i;
const TIMING_KEYWORDS = new Set(['ease', 'ease-in', 'ease-out', 'ease-in-out', 'linear', 'step-start', 'step-end']);

/** 단위 없는 숫자를 토큰으로만 쓰는 속성 */
const UNITLESS_TOKEN_PROPS = {
  'z-index': '--z-*',
  'line-height': '--lh-*',
  'font-weight': '--fw-*',
};

const fmtNum = (t) => t.raw ?? String(t.value);

/**
 * 선언 하나를 검사한다.
 * @param {string} s 원문
 * @param {object[]} toks 선언에 속한 토큰(주석 제외)
 * @param {(offset: number, reason: string) => void} add
 */
function checkCssDecl(s, toks, add) {
  const sig = toks.filter((t) => t.type !== 'ws');
  if (sig.length < 2 || sig[0].type !== 'ident' || sig[1].type !== ':') return; // 선언이 아님(at-rule 문 등)
  const prop = sig[0].value.toLowerCase();
  const colonIdx = toks.indexOf(sig[1]);
  const value = toks.slice(colonIdx + 1);
  const colorProp = COLOR_PROPS.test(prop);
  const motionProp = MOTION_PROPS.test(prop);
  const unitlessToken = UNITLESS_TOKEN_PROPS[prop];

  let prevSig = null; // 바로 앞의 공백 아닌 토큰
  for (const t of value) {
    if (t.type === 'ws') continue;
    switch (t.type) {
      case 'hash':
        if (/^(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(t.value)) add(t.start, `색 리터럴 #${t.value}`);
        break;
      case 'function':
        if (COLOR_FNS.has(t.value)) add(t.start, `색 리터럴 ${t.value}()`);
        else if (t.value === 'cubic-bezier' || t.value === 'steps') add(t.start, `곡선 리터럴 ${t.value}() — --ease 토큰을 쓰세요`);
        else if (t.value === 'linear' && motionProp) add(t.start, '곡선 리터럴 linear() — --ease 토큰을 쓰세요');
        break;
      case 'ident': {
        const v = t.value.toLowerCase();
        if (colorProp && NAMED_COLORS.has(v)) add(t.start, `이름 색 리터럴 '${t.value}'`);
        if (motionProp && TIMING_KEYWORDS.has(v)) add(t.start, `곡선 키워드 '${t.value}' — var(--ease…) 토큰을 쓰세요`);
        break;
      }
      case 'dimension': {
        const abs = Math.abs(t.value);
        if (LENGTH_UNITS.has(t.unit)) {
          if (abs === 0) break;
          if (t.unit === 'px' && (abs === 1 || abs === 2)) break;
          add(t.start, `허용 밖 길이 ${fmtNum(t)} — 토큰(var(--…))을 쓰세요`);
        } else if (TIME_UNITS.has(t.unit) && abs !== 0) {
          add(t.start, `시간 리터럴 ${fmtNum(t)} — --dur-* 토큰을 쓰세요`);
        }
        // vh·vw 계열·fr·각도 등 나머지 단위는 허용
        break;
      }
      case 'number':
        if (unitlessToken) {
          add(t.start, `${prop} 숫자 리터럴 ${fmtNum(t)} — ${unitlessToken} 토큰을 쓰세요`);
        } else if (prop === 'font') {
          const afterSlash = prevSig && prevSig.type === 'delim' && prevSig.value === '/';
          add(
            t.start,
            afterSlash
              ? `font 축약형의 줄 간격 숫자 ${fmtNum(t)} — --lh-* 토큰을 쓰세요`
              : `font 축약형의 굵기 숫자 ${fmtNum(t)} — --fw-* 토큰을 쓰세요`,
          );
        }
        break;
      default:
        break;
    }
    prevSig = t;
  }
}

/**
 * CSS 텍스트를 검사한다.
 * @returns {{ line: number, reason: string, text: string }[]}
 */
export function checkCss(text) {
  const toks = tokenizeCss(text);
  const comments = toks.filter((t) => t.type === 'comment');
  const waived = waivedLines(text, comments);
  const starts = lineStarts(text);
  const lines = text.split('\n');
  const out = [];
  const add = (offset, reason) => {
    const line = lineAt(starts, offset);
    if (waived.has(line)) return;
    out.push({ line, reason, text: (lines[line - 1] ?? '').trim() });
  };

  const stack = []; // { exempt }
  let buf = [];
  let depth = 0; // 괄호 깊이(괄호 안의 ; { } 는 구분자가 아님)
  const flush = () => {
    const inExempt = stack.length > 0 && stack[stack.length - 1].exempt;
    if (stack.length > 0 && !inExempt && buf.length) checkCssDecl(text, buf, add);
    buf = [];
  };
  for (const t of toks) {
    if (t.type === 'comment') continue;
    if (t.type === '(' || t.type === 'function' || t.type === '[') depth++;
    else if ((t.type === ')' || t.type === ']') && depth > 0) depth--;
    if (depth === 0 && t.type === '{') {
      const first = buf.find((b) => b.type !== 'ws');
      const parentExempt = stack.length > 0 && stack[stack.length - 1].exempt;
      const exempt = parentExempt || (first?.type === 'at' && /^(-webkit-|-moz-)?keyframes$|^property$/.test(first.value));
      stack.push({ exempt });
      buf = [];
      continue;
    }
    if (depth === 0 && (t.type === ';' || t.type === '}')) {
      flush();
      if (t.type === '}') stack.pop();
      continue;
    }
    buf.push(t);
  }
  return out;
}

/* ---------- TS / TSX ---------- */

function scriptKindOf(fileName) {
  if (/\.tsx$/i.test(fileName)) return ts.ScriptKind.TSX;
  if (/\.jsx$/i.test(fileName)) return ts.ScriptKind.JSX;
  if (/\.(js|mjs|cjs)$/i.test(fileName)) return ts.ScriptKind.JS;
  return ts.ScriptKind.TS;
}

function parseTs(text, fileName) {
  return ts.createSourceFile(fileName, text, ts.ScriptTarget.Latest, true, scriptKindOf(fileName));
}

const HEX_ONLY_RE = /^[0-9a-fA-F]+$/;
const isOctal = (c) => c >= '0' && c <= '7';
/** 역슬래시 뒤에 오면 줄 이어 쓰기가 되는 글자: LF, U+2028, U+2029(CR·CRLF 는 따로 본다) */
const LINE_CONTINUATION = new Set(['\n', '\u2028', '\u2029']);
const SIMPLE_ESCAPES = { n: '\n', t: '\t', r: '\r', b: '\b', f: '\f', v: '\v' };

/**
 * JS 문자열·템플릿 원문(raw)의 이스케이프를 풀고, 푼 값의 각 글자가 원문 어디서 왔는지 대응표를 만든다.
 * 이스케이프가 잘못됐으면 예외를 던지지 않고 null 을 돌려준다:
 *   닫는 `}` 가 없음, 16진수가 아니거나 자릿수가 모자람, 코드 포인트가 0x10FFFF 를 넘음,
 *   끝에 홀로 남은 역슬래시, 템플릿 안의 8진 이스케이프·`\8`·`\9`.
 * 원문을 앞에서 뒤로 한 번만 지나가므로 어떤 입력에서도 끝난다.
 * @param {string} raw 따옴표·백틱·`${`·`}` 를 뺀 원문
 * @param {{ template?: boolean }} [opts] template = 템플릿 리터럴 규칙(8진 이스케이프 없음)
 * @returns {{ cooked: string, map: number[] } | null} map[k] = cooked[k] 가 온 원문 위치(raw 기준)
 */
export function cookWithMap(raw, { template = false } = {}) {
  let cooked = '';
  const map = [];
  const emit = (str, at) => {
    for (let k = 0; k < str.length; k++) map.push(at);
    cooked += str;
  };
  let i = 0;
  while (i < raw.length) {
    const c = raw[i];
    if (c === '\r') {
      // 템플릿 원문의 CRLF·CR 은 LF 로 바뀐다(일반 문자열에는 역슬래시 없는 CR 이 올 수 없다)
      emit('\n', i);
      i += raw[i + 1] === '\n' ? 2 : 1;
      continue;
    }
    if (c !== '\\') {
      emit(c, i);
      i++;
      continue;
    }
    const at = i;
    const d = raw[i + 1];
    if (d === undefined) return null;
    if (LINE_CONTINUATION.has(d)) { i += 2; continue; }
    if (d === '\r') { i += raw[i + 2] === '\n' ? 3 : 2; continue; }
    if (d === 'u' && raw[i + 2] === '{') {
      const close = raw.indexOf('}', i + 3);
      if (close < 0) return null;
      const hex = raw.slice(i + 3, close);
      if (!HEX_ONLY_RE.test(hex)) return null;
      const cp = parseInt(hex, 16);
      if (!(cp <= 0x10ffff)) return null;
      emit(String.fromCodePoint(cp), at);
      i = close + 1;
      continue;
    }
    if (d === 'u' || d === 'x') {
      const len = d === 'u' ? 4 : 2;
      const hex = raw.slice(i + 2, i + 2 + len);
      if (hex.length !== len || !HEX_ONLY_RE.test(hex)) return null;
      emit(String.fromCharCode(parseInt(hex, 16)), at);
      i += 2 + len;
      continue;
    }
    if (isDigit(d)) {
      if (d === '0' && !isDigit(raw[i + 2])) { emit('\0', at); i += 2; continue; }
      if (template) return null; // 템플릿에는 8진 이스케이프와 \8·\9 가 없다
      if (d === '8' || d === '9') { emit(d, at); i += 2; continue; }
      // 옛 8진 이스케이프(\1 … \377). 엄격 모드에서는 문법 오류지만 값은 만든다
      let j = i + 1;
      let oct = '';
      while (j < raw.length && oct.length < 3 && isOctal(raw[j]) && parseInt(oct + raw[j], 8) <= 255) oct += raw[j++];
      emit(String.fromCharCode(parseInt(oct, 8)), at);
      i = j;
      continue;
    }
    emit(SIMPLE_ESCAPES[d] ?? d, at);
    i += 2;
  }
  return { cooked, map };
}

/** JSX 속성 문자열에서 풀리는 문자 참조: 10진·16진 숫자 참조와, ASCII 글자가 되는 이름 참조 5개 */
const JSX_ENTITY_RE = /&(?:#(\d+)|#x([0-9a-fA-F]+)|(quot|amp|apos|lt|gt));/y;
const JSX_NAMED_ENTITIES = { quot: '"', amp: '&', apos: "'", lt: '<', gt: '>' };

/**
 * JSX 속성 문자열(`<a title="…">` 의 따옴표 안)의 실행 시 값과 위치 대응표.
 * JSX 규칙대로 역슬래시는 그냥 글자다. TypeScript 의 JSX 변환처럼 `&#35;`·`&#x23;`·`&amp;` 같은 문자 참조를 푼다.
 * 그 밖의 이름 참조(`&nbsp;` 등)는 ASCII 가 아닌 글자가 되어 색 리터럴을 만들거나 끊지 못하므로 원문 그대로 둔다.
 * 코드 포인트가 0x10FFFF 를 넘는 숫자 참조도 풀지 않는다. 예외를 던지지 않는다.
 * @param {string} raw 따옴표를 뺀 원문
 * @returns {{ value: string, map: number[] }}
 */
export function decodeJsxAttribute(raw) {
  let value = '';
  const map = [];
  let i = 0;
  while (i < raw.length) {
    if (raw[i] === '&') {
      JSX_ENTITY_RE.lastIndex = i;
      const m = JSX_ENTITY_RE.exec(raw);
      let ch = null;
      if (m && m[3]) ch = JSX_NAMED_ENTITIES[m[3]];
      else if (m) {
        const cp = m[1] !== undefined ? parseInt(m[1], 10) : parseInt(m[2], 16);
        if (cp <= 0x10ffff) ch = String.fromCodePoint(cp);
      }
      if (ch !== null) {
        for (let k = 0; k < ch.length; k++) map.push(i);
        value += ch;
        i += m[0].length;
        continue;
      }
    }
    value += raw[i];
    map.push(i);
    i++;
  }
  return { value, map };
}

const STRING_KINDS = new Set([
  ts.SyntaxKind.StringLiteral,
  ts.SyntaxKind.NoSubstitutionTemplateLiteral,
  ts.SyntaxKind.TemplateHead,
  ts.SyntaxKind.TemplateMiddle,
  ts.SyntaxKind.TemplateTail,
]);
const TEMPLATE_KINDS = new Set([
  ts.SyntaxKind.NoSubstitutionTemplateLiteral,
  ts.SyntaxKind.TemplateHead,
  ts.SyntaxKind.TemplateMiddle,
  ts.SyntaxKind.TemplateTail,
]);
/** TypeScript 가 템플릿 조각에 남기는 '잘못된 이스케이프' 표시(태그 템플릿이면 그 조각의 strings[i] 는 undefined) */
const INVALID_ESCAPE_FLAG = ts.TokenFlags?.ContainsInvalidEscape ?? 0;

/** 태그가 붙은 템플릿(String.raw`…`, css`…`)의 조각인가. 태그 자리에 놓인 템플릿(`a``b` 의 `a`)은 아니다 */
function isTaggedTemplatePart(node) {
  let tpl = node;
  if (node.kind === ts.SyntaxKind.TemplateHead) tpl = node.parent; // TemplateExpression
  else if (node.kind === ts.SyntaxKind.TemplateMiddle || node.kind === ts.SyntaxKind.TemplateTail) tpl = node.parent?.parent; // TemplateSpan → TemplateExpression
  const p = tpl?.parent;
  return !!p && p.kind === ts.SyntaxKind.TaggedTemplateExpression && p.template === tpl;
}

/** 리터럴 노드의 원문 내용 범위(따옴표·`${`·`}` 제외) */
function rawRange(node, sf) {
  const start = node.getStart(sf) + 1;
  let end = node.end - 1; // 닫는 따옴표·백틱
  if (node.kind === ts.SyntaxKind.TemplateHead || node.kind === ts.SyntaxKind.TemplateMiddle) end = node.end - 2; // `${`
  return { start, end: Math.max(start, end) };
}

/**
 * 리터럴 노드 하나를 실행 시 값과 위치 대응표로 바꾼다. 예외를 던지지 않는다.
 * 대응표를 만들 수 없으면(문법 오류 등으로 직접 푼 값이 TypeScript 값과 다름) map = null 이고,
 * 값은 TypeScript 가 준 node.text 를 쓴다.
 */
function describeLiteral(node, sf, text) {
  const { start, end } = rawRange(node, sf);
  const raw = text.slice(start, end);
  const tsText = typeof node.text === 'string' ? node.text : null;
  if (node.kind === ts.SyntaxKind.StringLiteral && node.parent?.kind === ts.SyntaxKind.JsxAttribute) {
    const { value, map } = decodeJsxAttribute(raw);
    return { start, end, kind: 'jsx-attribute', raw, value, map };
  }
  const template = TEMPLATE_KINDS.has(node.kind);
  const cooked = cookWithMap(raw, { template });
  const mapped = cooked !== null && cooked.cooked === tsText ? cooked.map : null;
  if (template && isTaggedTemplatePart(node)) {
    // 태그 함수는 strings.raw(원문)와 strings[i](푼 값)를 받는다. 잘못된 이스케이프가 있으면 푼 값은 없다.
    const invalid = INVALID_ESCAPE_FLAG ? ((node.templateFlags ?? 0) & INVALID_ESCAPE_FLAG) !== 0 : cooked === null;
    return { start, end, kind: 'tagged-template', raw, value: invalid ? null : tsText, map: invalid ? null : mapped };
  }
  return { start, end, kind: template ? 'template' : 'string', raw, value: tsText ?? cooked?.cooked ?? raw, map: mapped };
}

/**
 * TS/TSX 텍스트에서 문자열·템플릿 리터럴을 모은다(TypeScript 파서 사용).
 * 정규식 리터럴·주석·JSX 글자는 문자열이 아니므로 들어가지 않는다.
 * @returns {{ start: number, end: number, kind: 'string' | 'template' | 'tagged-template' | 'jsx-attribute',
 *             raw: string, value: string | null, map: number[] | null }[]}
 *   raw = 원문 내용(start 부터), value = 실행 시 값(태그 템플릿에 잘못된 이스케이프가 있으면 null),
 *   map[k] = value[k] 가 온 원문 위치(start 기준). 대응을 만들 수 없으면 null
 */
export function collectStrings(text, fileName = 'input.tsx') {
  const sf = parseTs(text, fileName);
  const out = [];
  const visit = (node) => {
    if (STRING_KINDS.has(node.kind)) out.push(describeLiteral(node, sf, text));
    ts.forEachChild(node, visit);
  };
  visit(sf);
  return out.sort((a, b) => a.start - b.start);
}

/** 글자열에서 색 리터럴을 찾는다(앞에서부터 순서대로). */
function findColors(str) {
  const found = [];
  for (const m of str.matchAll(HEX_RE)) found.push({ idx: m.index, reason: `문자열 안 색 리터럴 ${m[0]}` });
  for (const m of str.matchAll(TS_COLOR_FN_RE)) found.push({ idx: m.index, reason: `문자열 안 색 리터럴 ${m[1]}(` });
  return found.sort((a, b) => a.idx - b.idx);
}

/**
 * 리터럴 하나의 색 리터럴. 반환: 원문 위치(리터럴 내용 시작 기준)와 이유, 위치 순.
 * - 실행 시 값(value)을 보고 대응표로 위치를 찾는다. 대응표가 없으면 위치는 리터럴 시작(0)이다.
 * - 태그 템플릿은 원문(strings.raw)도 본다. 값에서 이미 같은 자리의 같은 색을 찾았으면 한 번만 센다.
 */
function colorHits(s) {
  const hits = [];
  if (s.value !== null) {
    for (const h of findColors(s.value)) hits.push({ offset: s.map ? (s.map[h.idx] ?? 0) : 0, reason: h.reason });
  }
  if (s.kind === 'tagged-template') {
    const known = new Set(hits.map((h) => `${h.offset}:${h.reason}`));
    for (const h of findColors(s.raw)) if (!known.has(`${h.idx}:${h.reason}`)) hits.push({ offset: h.idx, reason: h.reason });
  }
  return hits.sort((a, b) => a.offset - b.offset);
}

/**
 * 실제 주석(줄·블록)의 범위를 모두 모은다.
 * 모든 낱말(토큰)의 앞 trivia(leading)와 같은 줄 뒤 trivia(trailing)에서 주석을 찾는다.
 * JSX 글자 안의 `//`·`/*` 는 주석이 아니므로 JSX 글자 범위에서 시작하는 것은 버린다.
 */
function collectTsComments(text, sf) {
  const seen = new Map();
  const jsxText = []; // [pos, end)
  const add = (ranges) => {
    for (const r of ranges ?? []) if (!seen.has(r.pos)) seen.set(r.pos, { start: r.pos, end: r.end });
  };
  const isJsDoc = (node) => node.kind >= ts.SyntaxKind.FirstJSDocNode && node.kind <= ts.SyntaxKind.LastJSDocNode;
  const visit = (node) => {
    if (isJsDoc(node)) return; // JSDoc 은 아래 trivia 검사에서 주석 하나로 잡힌다
    if (node.kind === ts.SyntaxKind.JsxText) {
      jsxText.push([node.pos, node.end]);
      return;
    }
    const kids = node.getChildren(sf);
    if (kids.length === 0) {
      add(ts.getLeadingCommentRanges(text, node.pos));
      add(ts.getTrailingCommentRanges(text, node.end));
      return;
    }
    for (const k of kids) visit(k);
  };
  visit(sf);
  const inJsxText = (p) => jsxText.some(([a, b]) => p >= a && p < b);
  return [...seen.values()].filter((c) => !inJsxText(c.start));
}

/**
 * TS/TSX 텍스트를 검사한다.
 * @param {string} text
 * @param {string} [fileName] 파서 종류를 고르는 데 쓴다(.tsx/.jsx = JSX 허용). 기본 input.tsx
 * @returns {{ line: number, reason: string, text: string }[]}
 */
export function checkTs(text, fileName = 'input.tsx') {
  const sf = parseTs(text, fileName);
  const starts = lineStarts(text);
  const lines = text.split('\n');
  const waived = waivedLines(text, collectTsComments(text, sf));
  const out = [];
  for (const s of collectStrings(text, fileName)) {
    for (const h of colorHits(s)) {
      const offset = s.start + h.offset;
      const line = lineAt(starts, offset);
      if (waived.has(line)) continue;
      out.push({ line, reason: `${h.reason} — var(--토큰)을 쓰세요(색 값은 tokens.css·config/app.ts에만)`, text: (lines[line - 1] ?? '').trim() });
    }
  }
  return out;
}

/* ---------- 파일 순회 ---------- */

const errorMessage = (e) => (e instanceof Error ? e.message : String(e)).split('\n')[0];

/**
 * 폴더 아래 파일을 모은다. 읽지 못한 폴더는 errors 에 담고 나머지는 계속 돈다.
 * 가리키는 대상이 없는 심볼릭 링크는 검사할 내용이 없으므로 건너뛴다.
 */
function walk(dir, files, errors) {
  let names;
  try {
    names = readdirSync(dir);
  } catch (e) {
    errors.push({ path: dir, message: errorMessage(e) });
    return files;
  }
  for (const name of names) {
    if (name === 'node_modules' || name.startsWith('.')) continue;
    const p = join(dir, name);
    let st;
    try {
      st = statSync(p);
    } catch (e) {
      if (e?.code === 'ENOENT') continue; // 깨진 심볼릭 링크
      errors.push({ path: p, message: errorMessage(e) });
      continue;
    }
    if (st.isDirectory()) walk(p, files, errors);
    else files.push(p);
  }
  return files;
}

/**
 * 저장소의 src 폴더를 검사한다. src 가 없으면 빈 목록.
 * 읽거나 검사하지 못한 파일·폴더는 `error: true` 항목으로 돌려준다(그래도 나머지 파일은 끝까지 검사한다).
 * @returns {{ file: string, line: number, reason: string, text: string, error?: true }[]}
 */
export function checkRepo(root) {
  const srcDir = join(root, 'src');
  const results = [];
  if (!existsSync(srcDir)) return results;
  const rel = (abs) => relative(root, abs).split(sep).join('/');
  const errors = [];
  const files = walk(srcDir, [], errors);
  for (const e of errors) results.push({ file: rel(e.path), line: 0, reason: `읽지 못함 — ${e.message}`, text: '', error: true });
  for (const abs of files.sort()) {
    const file = rel(abs);
    const isCss = CSS_FILE_RE.test(file);
    if (isCss ? CSS_EXCLUDE.has(file) : !TS_FILE_RE.test(file) || TS_EXCLUDE.has(file)) continue;
    try {
      const text = readFileSync(abs, 'utf8');
      for (const v of isCss ? checkCss(text) : checkTs(text, file)) results.push({ file, ...v });
    } catch (e) {
      results.push({ file, line: 0, reason: `검사하지 못함 — ${errorMessage(e)}`, text: '', error: true });
    }
  }
  return results;
}

function main() {
  const root = process.argv[2] ? process.argv[2] : join(fileURLToPath(new URL('.', import.meta.url)), '..');
  const results = checkRepo(root);
  if (results.length === 0) {
    console.log('check:tokens — 위반 없음');
    return 0;
  }
  const errors = results.filter((r) => r.error);
  const violations = results.filter((r) => !r.error);
  for (const r of violations) console.error(`${r.file}:${r.line}: ${r.reason}\n    ${r.text}`);
  for (const r of errors) console.error(`${r.file}: ${r.reason}`);
  if (violations.length) {
    console.error(`\ncheck:tokens — 위반 ${violations.length}건. 값은 src/styles/tokens.css 의 토큰을 쓰고, 꼭 필요한 예외는 줄 끝에 'tokens-ok: <이유>' 주석을 단다.`);
  }
  if (errors.length) {
    console.error(`\ncheck:tokens — 검사하지 못한 파일·폴더 ${errors.length}개(위 경로). 읽기 권한이나 파일 상태를 확인한다.`);
    return 2;
  }
  return 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = main();
}
