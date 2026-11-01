/* ==========================================================================
   ③ 샘플 데이터 경계 — eslint.config.mjs 의 no-restricted-imports + no-restricted-syntax
   화면(src/components/ 등)은 샘플을 정적·동적·재내보내기 어느 방식으로도 import하지 못하고,
   src/services/demo/**·src/samples/** 만 예외다. (T1-fix1 M3)
   ESLint Node API 로 실제 설정 파일을 읽어 검사한다(파일은 만들지 않는다).
   ========================================================================== */

import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { ESLint } from 'eslint';
import { beforeAll, describe, expect, it } from 'vitest';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const BOUNDARY_RULES = new Set(['no-restricted-imports', 'no-restricted-syntax']);
const TIMEOUT = 60_000;

/** 정적 import·재내보내기 */
const STATIC_CASES = [
  ['정적 import(별칭)', "import { x } from '@/samples/x';\nexport const y = x;\n"],
  ['정적 import(별칭 폴더)', "import * as s from '@/samples';\nexport const y = s;\n"],
  ['정적 import(상대 경로)', "import { x } from '../samples/x';\nexport const y = x;\n"],
  ['정적 import(깊은 상대 경로)', "import { x } from '../../src/samples/data/a';\nexport const y = x;\n"],
  ['type import', "import type { X } from '@/samples/x';\nexport type Y = X;\n"],
  ['부수 효과 import', "import '@/samples/register';\n"],
];
const REEXPORT_CASES = [
  ['export { } from', "export { x } from '@/samples/x';\n"],
  ['export * from', "export * from '../samples';\n"],
  ['export * as from', "export * as s from '@/samples/x';\n"],
  ['export type { } from', "export type { X } from '@/samples/x';\n"],
];
const DYNAMIC_CASES = [
  ['동적 import(별칭)', "export const load = () => import('@/samples/x');\n"],
  ['동적 import(별칭 폴더)', "export const load = () => import('@/samples');\n"],
  ['동적 import(상대 경로)', "export const load = () => import('../samples/x');\n"],
  ['동적 import(템플릿, 치환 없음)', 'export const load = () => import(`@/samples/x`);\n'],
  ['동적 import(템플릿, 치환 있음)', 'export const load = (n: string) => import(`@/samples/${n}`);\n'],
  ['require()', "export const s = require('@/samples/x');\n"],
  ['import x = require()', "import s = require('../samples/x');\nexport const y = s;\n"],
  ['타입 위치의 import()', "export type S = typeof import('@/samples/x');\n"],
];
const ALL_CASES = [...STATIC_CASES, ...REEXPORT_CASES, ...DYNAMIC_CASES];

/** 샘플이 아닌 비슷한 경로는 막지 않는다 */
const NEAR_MISS = [
  "import { useService } from '@/services/react';",
  "import { SampleBadge } from '@/components/ui/SampleBadge';",
  "export const a = () => import('@/components/samples-list');",
  "export const b = () => import('./sample');",
  "export const c = () => import('@/samplesx');",
].join('\n');

let eslint;
beforeAll(() => {
  eslint = new ESLint({ cwd: ROOT });
});

async function lint(code, rel) {
  const [result] = await eslint.lintText(code, { filePath: join(ROOT, rel) });
  const fatal = result.messages.filter((m) => m.fatal);
  return { fatal, boundary: result.messages.filter((m) => BOUNDARY_RULES.has(m.ruleId)) };
}

describe('화면(src/components/)은 샘플을 import하지 못한다', () => {
  for (const [name, code] of ALL_CASES) {
    it(name, { timeout: TIMEOUT }, async () => {
      const r = await lint(code, 'src/components/__boundary_probe.tsx');
      expect(r.fatal).toEqual([]);
      expect(r.boundary.length).toBeGreaterThanOrEqual(1);
      expect(r.boundary[0].message).toContain('③ 샘플 데이터');
      expect(r.boundary.every((m) => m.severity === 2)).toBe(true);
    });
  }

  it('정적·동적 import 는 각각 다른 규칙이 잡는다', { timeout: TIMEOUT }, async () => {
    const r = await lint(
      "import { x } from '@/samples/x';\nexport const y = x;\nexport const load = () => import('@/samples/x');\n",
      'src/components/__boundary_probe.tsx',
    );
    expect(r.boundary.map((m) => `${m.line}:${m.ruleId}`)).toEqual(['1:no-restricted-imports', '3:no-restricted-syntax']);
  });

  it('src/app/ 의 .ts 파일도 같다', { timeout: TIMEOUT }, async () => {
    const r = await lint("export const load = () => import('../samples/x');\n", 'src/app/__boundary_probe.ts');
    expect(r.boundary).toHaveLength(1);
  });

  it('샘플이 아닌 비슷한 경로는 통과', { timeout: TIMEOUT }, async () => {
    const r = await lint(`${NEAR_MISS}\n`, 'src/components/__boundary_probe.tsx');
    expect(r.fatal).toEqual([]);
    expect(r.boundary).toEqual([]);
  });
});

describe('src/services/demo/**·src/samples/** 는 예외', () => {
  for (const folder of ['src/services/demo', 'src/samples']) {
    for (const [name, code] of ALL_CASES) {
      it(`${folder} — ${name}`, { timeout: TIMEOUT }, async () => {
        const r = await lint(code, `${folder}/__boundary_probe.ts`);
        expect(r.fatal).toEqual([]);
        expect(r.boundary).toEqual([]);
      });
    }
  }
});
