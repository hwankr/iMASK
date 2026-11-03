/* ==========================================================================
   지킴 테스트 — 주소 기준 모드 · 기준 경로 규칙이 소스에서 깨지지 않았는지 저장소 파일을 읽어 검사한다.
   (a) src/app · src/components · src/lib · src/dev 는 빌드 모드 상수 SERVICE_MODE 를 읽지 않는다
       (화면의 모드 판단은 useServiceMode — 주소 기준).
   (b) 환경변수 NEXT_PUBLIC_IMASK_SERVICE 는 src/services/mode.ts 와 src/components/detail/liveFile.ts
       (pdf.js 묶음 제거용 빌드 분기) 밖에서 읽지 않는다.
   (c) src/app(dev 제외) · src/components 의 화면 코드(테스트 제외)에 이동 주소 리터럴이 없다 — 이동 주소는
       src/lib/routes.ts 함수 + useRouteBase() 로 만든다(`/demo` 아래에서 `/demo` 밖으로 새지 않게).
       · 어디서든: '/analyses…' 로 시작하는 문자열 · 템플릿 리터럴, '/demo' 경로 리터럴
       · 이동 자리(JSX href 속성 값 · href 속성 객체 값 · push( · replace( 첫 인자)의 맨 앞 리터럴이 '/' 로 시작
         (예: '/', '/?review=needed', '/' + x). 구분자로 쓴 '/'(x + '/' + y)는 잡지 않는다.
       · push · replace 는 파일마다 useRouter() 를 받은 이름(const r = useRouter() 의 r, 구조 분해한 push ·
         replace: go — 이름 바꿈 포함)과 이름에 router 가 든 받는 쪽은 인자 수와 상관없이(옵션 인자가 있어도),
         그 밖은 인자가 하나일 때만 본다(글자 처리 text.replace('/', '-') 를 잡지 않게).
   TypeScript 파서로 읽으므로 주석과 JSX 글자는 검사하지 않는다(scripts/check-tokens.mjs 와 같은 방식).
   위반은 '파일:줄 이유' 로 알린다. 검사 함수는 일부러 위반을 넣은 작은 표본으로도 확인한다(정말 잡는지).
   ========================================================================== */

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));

/* 검사할 이름 — 이 파일의 글자가 스스로 걸리지 않게 실행 중에 만든다 */
const MODE_CONST = ['SERVICE', 'MODE'].join('_');
const MODE_ENV = ['NEXT', 'PUBLIC', 'IMASK', 'SERVICE'].join('_');
/** 환경변수를 읽어도 되는 파일 */
const ENV_ALLOWED = new Set(['src/services/mode.ts', 'src/components/detail/liveFile.ts']);

interface Violation {
  file: string;
  line: number;
  reason: string;
}

const show = (v: Violation) => `${v.file}:${v.line} ${v.reason}`;

function parse(file: string, text: string): ts.SourceFile {
  const kind = file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  return ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, kind);
}

/** 모든 노드 — forEachChild 는 주석(trivia · JSDoc)을 거치지 않는다 */
function visit(node: ts.Node, fn: (n: ts.Node) => void): void {
  fn(node);
  ts.forEachChild(node, (child) => visit(child, fn));
}

function lineOf(sf: ts.SourceFile, node: ts.Node): number {
  return sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1;
}

/** 문자열처럼 값이 정해진 리터럴의 글자(일반 문자열 · 치환 없는 템플릿 · 템플릿 머리) */
function literalText(node: ts.Node): string | null {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text;
  if (ts.isTemplateExpression(node)) return node.head.text;
  return null;
}

/** 식의 맨 앞 리터럴 글자들 — 'a' + x 의 'a', 조건식은 두 갈래 모두. 맨 앞이 리터럴이 아니면 없음 */
function leadingTexts(e: ts.Expression | undefined): string[] {
  if (!e) return [];
  if (ts.isParenthesizedExpression(e) || ts.isAsExpression(e) || ts.isSatisfiesExpression(e)) return leadingTexts(e.expression);
  if (ts.isConditionalExpression(e)) return [...leadingTexts(e.whenTrue), ...leadingTexts(e.whenFalse)];
  if (ts.isBinaryExpression(e) && e.operatorToken.kind === ts.SyntaxKind.PlusToken) return leadingTexts(e.left);
  const t = literalText(e);
  return t === null ? [] : [t];
}

/** (a) · (b) — 이름(식별자 또는 정확히 그 글자의 문자열)을 쓴 곳 */
export function findNameUses(file: string, text: string, name: string): Violation[] {
  const sf = parse(file, text);
  const out: Violation[] = [];
  visit(sf, (n) => {
    if ((ts.isIdentifier(n) && n.text === name) || literalText(n) === name) out.push({ file, line: lineOf(sf, n), reason: `${name} 를 읽습니다` });
  });
  return out;
}

const isDemoLiteral = (t: string) => t === '/demo' || /^\/demo[/?#]/.test(t);

/** 라우터 이동 함수 이름 */
const NAV_METHODS = new Set(['push', 'replace']);

/** useRouter() · next.useRouter() 호출인지 */
function isUseRouterCall(e: ts.Expression | undefined): boolean {
  if (!e || !ts.isCallExpression(e)) return false;
  const c = e.expression;
  return (ts.isIdentifier(c) && c.text === 'useRouter') || (ts.isPropertyAccessExpression(c) && c.name.text === 'useRouter');
}

/**
 * 파일 안에서 useRouter() 결과를 받은 이름 — `const r = useRouter()` 의 r(routers),
 * `const { push, replace: go } = useRouter()` 의 push · go(navFns, 이름을 바꾼 것 포함)
 */
function routerNames(sf: ts.SourceFile): { routers: Set<string>; navFns: Set<string> } {
  const routers = new Set<string>();
  const navFns = new Set<string>();
  visit(sf, (n) => {
    if (!ts.isVariableDeclaration(n) || !isUseRouterCall(n.initializer)) return;
    if (ts.isIdentifier(n.name)) routers.add(n.name.text);
    else if (ts.isObjectBindingPattern(n.name)) {
      for (const el of n.name.elements) {
        const key = el.propertyName && ts.isIdentifier(el.propertyName) ? el.propertyName.text : ts.isIdentifier(el.name) ? el.name.text : '';
        if (NAV_METHODS.has(key) && ts.isIdentifier(el.name)) navFns.add(el.name.text);
      }
    }
  });
  return { routers, navFns };
}

/** (c) 이동 주소 리터럴 */
export function findNavLiterals(file: string, text: string): Violation[] {
  const sf = parse(file, text);
  const out: Violation[] = [];
  const { routers, navFns } = routerNames(sf);
  const add = (n: ts.Node, reason: string) => out.push({ file, line: lineOf(sf, n), reason });

  /** 이동 자리의 식 — 맨 앞 리터럴이 '/' 로 시작하면 위반 */
  const checkNavValue = (where: string, e: ts.Expression | undefined, at: ts.Node) => {
    for (const t of leadingTexts(e)) {
      if (t.startsWith('/')) add(at, `${where} 에 이동 주소 리터럴 ${JSON.stringify(t)} — src/lib/routes.ts 함수와 useRouteBase() 로 만드세요`);
    }
  };

  visit(sf, (n) => {
    const t = literalText(n);
    if (t !== null && t.startsWith('/analyses')) add(n, `이동 주소 리터럴 ${JSON.stringify(t)} — detailHref · reportHref · newAnalysisHref(src/lib/routes.ts)를 쓰세요`);
    else if (t !== null && isDemoLiteral(t)) add(n, `기준 경로 리터럴 ${JSON.stringify(t)} — DEMO_BASE · withBase(src/lib/routes.ts)를 쓰세요`);

    // <X href="/…"> · <X href={'/…'}>
    if (ts.isJsxAttribute(n) && n.name.getText(sf) === 'href' && n.initializer) {
      const init = n.initializer;
      if (ts.isStringLiteral(init)) checkNavValue('href 속성', init, init);
      else if (ts.isJsxExpression(init)) checkNavValue('href 속성', init.expression, init);
    }
    // { href: '/…' }
    if (ts.isPropertyAssignment(n) && n.name.getText(sf) === 'href') checkNavValue('href 값', n.initializer, n.initializer);
    // 라우터 이동의 첫 인자 — 인자 수와 상관없이 본다(옵션 인자 { scroll: false } 가 있어도):
    //  · useRouter() 를 받은 이름의 r.push · r.replace, 구조 분해한 push · replace(이름을 바꾼 go 포함)
    //  · 받는 쪽 이름에 router 가 든 x.push · x.replace
    // 그 밖의 push(…) · replace(…) 는 인자가 하나일 때만 본다 — 글자 처리 text.replace('/', '-') 는 인자가 둘이라 잡지 않는다.
    if (ts.isCallExpression(n)) {
      const callee = n.expression;
      const access = ts.isPropertyAccessExpression(callee) ? callee : null;
      const fn = access ? access.name.text : ts.isIdentifier(callee) ? callee.text : '';
      const receiver = access ? access.expression : null;
      const viaRouter =
        (access !== null && NAV_METHODS.has(fn) && receiver !== null && ((ts.isIdentifier(receiver) && routers.has(receiver.text)) || /router/i.test(receiver.getText(sf)))) ||
        (ts.isIdentifier(callee) && navFns.has(callee.text));
      if (viaRouter || (NAV_METHODS.has(fn) && n.arguments.length === 1)) checkNavValue(`${fn}( 첫 인자`, n.arguments[0], n);
    }
  });
  return out;
}

/* ---------- 저장소 파일 ---------- */

function listFiles(dir: string): string[] {
  const abs = join(ROOT, dir);
  const out: string[] = [];
  for (const name of readdirSync(abs)) {
    const p = join(abs, name);
    if (statSync(p).isDirectory()) out.push(...listFiles(relative(ROOT, p)));
    else if (/\.(ts|tsx)$/.test(name)) out.push(relative(ROOT, p).split(sep).join('/'));
  }
  return out;
}

const read = (file: string) => readFileSync(join(ROOT, file), 'utf8');
const isTest = (file: string) => /\.test\.(ts|tsx)$/.test(file);

describe('지킴 — 저장소 소스', () => {
  it(`(a) src/app · src/components · src/lib · src/dev 에 ${MODE_CONST} 가 없다`, () => {
    const files = ['src/app', 'src/components', 'src/lib', 'src/dev'].flatMap(listFiles);
    expect(files.length).toBeGreaterThan(50);
    const found = files.flatMap((f) => findNameUses(f, read(f), MODE_CONST));
    expect(found.map(show)).toEqual([]);
  });

  it(`(b) ${MODE_ENV} 는 mode.ts · liveFile.ts 밖에서 읽지 않는다`, () => {
    const files = listFiles('src');
    const found = files.filter((f) => !ENV_ALLOWED.has(f)).flatMap((f) => findNameUses(f, read(f), MODE_ENV));
    expect(found.map(show)).toEqual([]);
    // 허용된 두 곳은 정말 읽는다(검사 대상 이름이 맞는지)
    for (const f of ENV_ALLOWED) expect(findNameUses(f, read(f), MODE_ENV).length, f).toBeGreaterThan(0);
  });

  it('(c) src/app(dev 제외) · src/components 화면 코드에 이동 주소 리터럴이 없다', () => {
    const files = ['src/app', 'src/components'].flatMap(listFiles).filter((f) => !f.startsWith('src/app/dev/') && !isTest(f));
    expect(files.length).toBeGreaterThan(50);
    const found = files.flatMap((f) => findNavLiterals(f, read(f)));
    expect(found.map(show)).toEqual([]);
  });
});

/* ---------- 검사 함수가 정말 잡는지 — 일부러 위반을 넣은 표본 ---------- */

describe('지킴 검사 함수 — 표본', () => {
  const navSample = [
    "import Link from 'next/link';", // 1
    'export function A({ id, x, y, busy }: { id: string; x: string; y: string; busy: boolean }) {', // 2
    '  const router = useRouter();', // 3
    "  router.push('/');", // 4
    "  router.replace('/?review=needed');", // 5
    '  const d = `/analyses/${id}`;', // 6
    "  const n = '/analyses/new';", // 7
    "  const sep = x + '/' + y;", // 8 — 구분자: 잡지 않음
    "  // router.push('/') 주석은 잡지 않음", // 9
    "  /* href=\"/\" 도 주석 */", // 10
    "  router.push(x + '/report'); router.replace('/', { scroll: false });", // 11 — 앞은 맨 앞이 리터럴이 아님(잡지 않음), 뒤는 잡음
    "  const demo = '/demo';", // 12
    '  return (', // 13
    '    <div>', // 14
    '      <Link href="/">로고</Link>', // 15
    "      <Link href={'/?sort=risk'}>목록</Link>", // 16
    "      <Link href={busy ? '/' : x}>둘 중</Link>", // 17
    '      <p>/analyses/new 로 이동합니다 · href="/" 는 JSX 글자</p>', // 18 — 잡지 않음
    "      <Button href={'/analyses/' + id}>상세</Button>", // 19
    "      <Link href={x}>변수</Link>", // 20 — 잡지 않음
    '    </div>', // 21
    '  );', // 22
    '}', // 23
    "const links = { href: '/' };", // 24
  ].join('\n');

  it('이동 주소 리터럴을 파일:줄과 함께 잡는다', () => {
    const found = findNavLiterals('sample.tsx', navSample);
    const lines = [...new Set(found.map((v) => v.line))].sort((a, b) => a - b);
    expect(lines).toEqual([4, 5, 6, 7, 11, 12, 15, 16, 17, 19, 24]);
    expect(found.filter((v) => v.line === 11)).toHaveLength(1); // 줄 11 은 router.replace('/', …) 하나만
    expect(found.every((v) => v.file === 'sample.tsx')).toBe(true);
    expect(show(found[0])).toMatch(/^sample\.tsx:4 /);
  });

  it('구분자 · 주석 · JSX 글자 · 변수는 잡지 않는다', () => {
    const clean = [
      "const a = x + '/' + y;",
      "const b = ['a', 'b'].join('/');",
      "// router.push('/analyses/new')",
      "/** href='/' */",
      'const c = <p>/analyses/A1 · /demo 안내</p>;',
      "const d = <Link href={listHref(base)}>목록</Link>;",
      "router.push(detailHref(base, id));",
      "const e = <use href=\"#dg-i-x\" />;",
      "const f = text.replace('/', '-');", // 글자 바꾸기(인자 둘, router 아님)
    ].join('\n');
    expect(findNavLiterals('clean.tsx', clean)).toEqual([]);
  });

  it('useRouter() 별칭 · 구조 분해(이름 바꿈 포함) 호출은 옵션 인자가 있어도 잡는다', () => {
    const aliasSample = [
      'export function B({ id, x }: { id: string; x: string }) {', // 1
      "  const { push } = useRouter(); push('/', { scroll: false });", // 2 — 구조 분해
      "  const r = useRouter(); r.replace('/?q=1', { scroll: false });", // 3 — 별칭
      '  const { replace: go, push: nav } = useRouter();', // 4
      "  go('/?review=needed', { scroll: false });", // 5 — 이름을 바꾼 구조 분해
      "  nav('/' + x, { scroll: false });", // 6 — 맨 앞이 '/' 리터럴
      "  useRouter().push('/', { scroll: false });", // 7 — 받은 값에 바로
      "  r.push(x, { scroll: false });", // 8 — 변수: 잡지 않음
      '}', // 9
    ].join('\n');
    const found = findNavLiterals('alias.tsx', aliasSample);
    expect(found.map((v) => v.line)).toEqual([2, 3, 5, 6, 7]);
    expect(found.every((v) => /첫 인자/.test(v.reason))).toBe(true);
  });

  it('라우터가 있는 파일에서도 글자 처리(replace · split · 배열 push)는 잡지 않는다', () => {
    const textSample = [
      'export function C({ id, text, path, arr }: { id: string; text: string; path: string; arr: string[] }) {',
      '  const r = useRouter();',
      '  const { push } = useRouter();',
      "  const a = text.replace('/', '-');", // 글자 바꾸기 — 받는 쪽이 라우터가 아니고 인자 둘
      "  const b = path.replace('/x', '');",
      "  const c = a.split('/');",
      "  arr.push('/a', '/b');", // 배열 push — 인자 둘
      '  r.push(detailHref(base, id), { scroll: false });', // 라우터지만 함수로 만든 주소
      '  push(listHref(base), { scroll: false });',
      '  return [b, c];',
      '}',
    ].join('\n');
    expect(findNavLiterals('text.tsx', textSample)).toEqual([]);
  });

  it(`${MODE_CONST} · ${MODE_ENV} 사용을 잡고 주석은 무시한다`, () => {
    const modeSample = [`import { ${MODE_CONST} } from '@/services/mode';`, `// ${MODE_CONST} 주석은 무시`, `export const isApi = ${MODE_CONST} === 'api';`].join('\n');
    expect(findNameUses('m.tsx', modeSample, MODE_CONST).map((v) => v.line)).toEqual([1, 3]);
    const envSample = [`const a = process.env.${MODE_ENV};`, `/* process.env.${MODE_ENV} */`, `const b = process.env['${MODE_ENV}'];`].join('\n');
    expect(findNameUses('e.ts', envSample, MODE_ENV).map((v) => v.line)).toEqual([1, 3]);
    expect(findNameUses('e.ts', '// 아무것도 없음', MODE_ENV)).toEqual([]);
  });
});
