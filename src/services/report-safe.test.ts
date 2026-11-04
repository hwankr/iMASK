/* 보고서용 안전한 사본 — 원문 값 지우기 · 워크플로우 글의 원문 값 → masked(한 번의 훑기, 긴 값부터) · 원래 객체 불변 · 데모 그대로.
   원문 값은 테스트 출력에 옮기지 않는다(합성 값만 직접 만든다). */
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { createService } from '@/services';
import { toAnalysis } from './api/mapping';
import { analysisOut, contractResult } from './api/testing';
import { isLiveAnalysis, isReportTarget, rawValueMasker, reportClock, reportSafeAnalysis } from './report-safe';
import type { Analysis, Finding } from './types';

const NEW_REVIEW = { status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, history: [], version: 1 };

function liveAnalysis(edit?: (r: Record<string, unknown>) => void, review: unknown = NEW_REVIEW): Analysis {
  const result = contractResult();
  edit?.(result);
  return toAnalysis(analysisOut({ status: 'done', result, review: structuredClone(review) }));
}

/** 합성 값을 심은 실제 분석 — findings[i] 의 value · masked 를 바꾸고 워크플로우 글을 넣는다 */
function planted(values: { value: string; masked: string }[], texts: { reason?: string; overall?: string; next?: string }): Analysis {
  return liveAnalysis((r) => {
    const findings = r.findings as Record<string, unknown>[];
    values.forEach((v, i) => {
      findings[i].value = v.value;
      findings[i].masked = v.masked;
    });
    if (texts.reason !== undefined) findings[0].risk_reason = texts.reason;
    const overall = r.overall as Record<string, unknown>;
    if (texts.overall !== undefined) overall.text = texts.overall;
    if (texts.next !== undefined) overall.next_text = texts.next;
  });
}

const finding = (f: Partial<Finding> & { value: string; masked: string }): Finding =>
  ({ id: 'D1-01', masked: f.masked, live: { id: '0:x', field: 'x', value: f.value, mappingStatus: 'ok', confidence: null, riskSource: null } }) as Finding;

describe('rawValueMasker — 한 번의 훑기 · 긴 값부터', () => {
  it('긴 값부터 맞춘다(값이 다른 값의 일부)', () => {
    const mask = rawValueMasker([finding({ value: '1234', masked: 'S***' }), finding({ value: '010-1234-5678', masked: '010-****-5678' })]);
    expect(mask('번호 010-1234-5678 와 1234')).toBe('번호 010-****-5678 와 S***');
  });

  it('정규식 특수 문자가 든 값', () => {
    const special = 'a.b*c+d?e(f)g[h]i{j}k|l^m$n\\o/p';
    const mask = rawValueMasker([finding({ value: special, masked: '#MASK#' }), finding({ value: '$&', masked: 'X$1' })]);
    expect(mask('앞 ' + special + ' 뒤')).toBe('앞 #MASK# 뒤');
    expect(mask('aXb*c+d?e(f)g[h]i{j}k|l^m$n\\o/p')).toBe('aXb*c+d?e(f)g[h]i{j}k|l^m$n\\o/p');
    // 바꿀 글의 $ 패턴은 해석하지 않는다
    expect(mask('값 $& 끝')).toBe('값 X$1 끝');
  });

  it('바꾼 글을 다시 훑지 않는다 — masked 가 원문 값을 품어도 · 다른 값을 만들어도 한 번만', () => {
    const mask = rawValueMasker([finding({ value: 'AB', masked: 'AB**' }), finding({ value: 'CD', masked: 'EF' }), finding({ value: 'EFG', masked: '***' })]);
    expect(mask('AB')).toBe('AB**');
    expect(mask('ABAB')).toBe('AB**AB**');
    // CD → EF 로 바꾼 뒤 'EFG' 가 생겨도 다시 바꾸지 않는다
    expect(mask('CDG')).toBe('EFG');
  });

  it('빈 masked → 같은 코드 포인트 수의 *, 1 코드 포인트 값 · masked 와 같은 값 · 빈 값은 그대로', () => {
    const mask = rawValueMasker([
      finding({ value: '홍길동', masked: '' }),
      finding({ value: '😀😀', masked: '' }),
      finding({ value: '김', masked: '*' }),
      finding({ value: '010-****-5678', masked: '010-****-5678' }),
      finding({ value: '', masked: 'x' }),
    ]);
    expect(mask('홍길동 😀😀 김 010-****-5678')).toBe('*** ** 김 010-****-5678');
  });

  it('같은 값이 여러 항목이면 처음 항목의 masked', () => {
    const mask = rawValueMasker([finding({ value: '홍길동', masked: '홍*동' }), finding({ value: '홍길동', masked: '***' })]);
    expect(mask('홍길동')).toBe('홍*동');
  });

  it('대상 값이 없으면 받은 글 그대로', () => {
    const mask = rawValueMasker([finding({ value: '김', masked: '*' })]);
    expect(mask('김 그대로')).toBe('김 그대로');
  });
});

/** 실행 중에 만드는 긴 합성 값 — 한글 음절(BMP) 또는 이모지(비 BMP) 코드 포인트 len 개 */
function big(seed: number, len: number, astral = false): string {
  const out: string[] = [];
  for (let i = 0; i < len; i++) out.push(String.fromCodePoint(astral ? 0x1f600 + ((i + seed) % 64) : 0xac00 + ((i * 7 + seed) % 11172)));
  return out.join('');
}

describe('rawValueMasker — 리터럴 매칭(정규식 한도 없음)', () => {
  it('65,536 · 262,144 코드 포인트 값도 예외 없이 바꾼다', () => {
    for (const len of [4096, 65536, 262144]) {
      const value = big(len, len);
      const mask = rawValueMasker([finding({ value, masked: 'LONG' })]);
      expect(mask('앞 ' + value + ' 뒤')).toBe('앞 LONG 뒤');
      // 빈 masked → 같은 코드 포인트 수의 *
      const star = rawValueMasker([finding({ value, masked: '' })])('[' + value + ']');
      expect(star.length).toBe(len + 2);
      expect(star).toBe('[' + '*'.repeat(len) + ']');
    }
  });

  it('여러 큰 값(합계 백만 코드 포인트 넘음) · 비 BMP 값 — 모두 바뀌고 원문 조각이 남지 않는다', () => {
    const values = [...Array.from({ length: 12 }, (_, i) => big(100 + i, 65536)), big(7, 262144), big(3, 40000, true)];
    const mask = rawValueMasker(values.map((value, i) => finding({ value, masked: `M${i}` })));
    const text = values.map((v, i) => `줄${i}:${v}`).join('\n');
    const out = mask(text);
    expect(out).toBe(values.map((_, i) => `줄${i}:M${i}`).join('\n'));
    for (const v of values) expect(out.includes(v.slice(1000, 1064))).toBe(false);
  });

  it('겹치는 접두 값 — 가장 이른 일치, 같은 위치면 코드 포인트가 긴 값', () => {
    const mask = rawValueMasker([finding({ value: 'AB', masked: '1' }), finding({ value: 'ABC', masked: '2' }), finding({ value: 'BCD', masked: '3' })]);
    expect(mask('ABCD')).toBe('2D');
    expect(mask('xBCDx AB')).toBe('x3x 1');
    // 더 긴 값이 뒤에서 시작하면 이른 일치가 먼저
    const early = rawValueMasker([finding({ value: 'BCDE', masked: 'L' }), finding({ value: 'AB', masked: 'S' })]);
    expect(early('ABCDE')).toBe('SCDE');
    // 같은 위치 · 비 BMP — 코드 포인트 길이로 견준다
    const astral = rawValueMasker([finding({ value: '😀😀', masked: 'two' }), finding({ value: '😀😀😀', masked: 'three' })]);
    expect(astral('😀😀😀😀')).toBe('three😀');
  });

  it('서로게이트 쌍을 가르는 자리에서는 맞추지 않는다(u 플래그와 같은 뜻)', () => {
    const mask = rawValueMasker([finding({ value: '\uDE00x', masked: 'L' }), finding({ value: 'a\uD83D', masked: 'H' })]);
    expect(mask('😀x')).toBe('😀x');
    expect(mask('a😀')).toBe('a😀');
    expect(mask('\uDE00x a\uD83D')).toBe('L H');
  });

  it('바꾼 결과가 다른 원문 값을 만들어도 다시 바꾸지 않는다(긴 값에서도)', () => {
    const v1 = big(1, 70000);
    const v2 = 'Z' + v1.slice(0, 5);
    const mask = rawValueMasker([finding({ value: v1, masked: 'Z' }), finding({ value: 'Z' + 'Q', masked: '#' }), finding({ value: v2, masked: '$' })]);
    // v1 → 'Z' 다음에 'Q' 가 와서 'ZQ' 가 생겨도 다시 바꾸지 않는다
    expect(mask(v1 + 'Q')).toBe('ZQ');
  });

  it('값이 수백 개 · 글이 길어도 빨리 끝난다', () => {
    const values = Array.from({ length: 400 }, (_, i) => `값${i}-${big(i, 24)}`);
    const mask = rawValueMasker(values.map((value, i) => finding({ value, masked: `*${i}*` })));
    const text = Array.from({ length: 200 }, (_, i) => `줄 ${i} ${values[(i * 13) % 400]} 끝 ${values[(i * 7) % 400]}`).join('\n');
    const t0 = performance.now();
    const out = mask(text);
    const ms = performance.now() - t0;
    expect(values.filter((v) => out.includes(v))).toHaveLength(0);
    expect(ms).toBeLessThan(2000);
  });
});

describe('rawValueMasker — 선형 시간(V-T2-2 V3 회귀: 반복이 많은 긴 값)', () => {
  /** 걸린 시간(ms)과 결과 */
  const timed = (fn: () => string): [string, number] => {
    const t0 = performance.now();
    const out = fn();
    return [out, performance.now() - t0];
  };
  /* 한도는 느린 CI 를 생각해 넉넉히 — 고치기 전(indexOf)은 8 × 65,536 비 BMP 2.9초 · 16개 9.8초였다 */

  it('같은 high surrogate 를 쓰는 비 BMP 값 8 × 65,536 + 이어 붙인 글 — 1초 안', () => {
    const values = Array.from({ length: 8 }, (_, i) => String.fromCodePoint(0xf1000 + i).repeat(65536));
    const mask = rawValueMasker(values.map((value, i) => finding({ value, masked: '#' + i })));
    const [out, ms] = timed(() => mask(values.join('|')));
    expect(out).toBe(values.map((_, i) => '#' + i).join('|'));
    expect(ms).toBeLessThan(1000);
  });

  it('16개(합계 1,245,184 코드 포인트) — 2.5초 안', () => {
    const values = Array.from({ length: 16 }, (_, i) => String.fromCodePoint(0xf0000 + i).repeat(i === 15 ? 262144 : 65536));
    expect(values.reduce((n, v) => n + Array.from(v).length, 0)).toBe(1245184);
    const mask = rawValueMasker(values.map((value, i) => finding({ value, masked: '#' + i })));
    const [out, ms] = timed(() => mask(values.join('|')));
    expect(out).toBe(values.map((_, i) => '#' + i).join('|'));
    expect(ms).toBeLessThan(2500);
  });

  it("BMP 반복 패턴('ab'.repeat(32768) 꼴) 8개 — 1초 안", () => {
    const values = Array.from({ length: 8 }, (_, i) => ('a' + String.fromCharCode(0x62 + i)).repeat(32768));
    const mask = rawValueMasker(values.map((value, i) => finding({ value, masked: '#' + i })));
    const [out, ms] = timed(() => mask(values.join('') + values[0]));
    expect(out).toBe(values.map((_, i) => '#' + i).join('') + '#0');
    expect(ms).toBeLessThan(1000);
  });

  it('접두가 겹치는 긴 값 8개(끝만 다름) — 이른 일치 · 긴 값, 1초 안', () => {
    const base = 'ab'.repeat(32768);
    const values = Array.from({ length: 8 }, (_, i) => base.slice(0, 65536 - 1000 * i) + 'Z' + i);
    const mask = rawValueMasker(values.map((value, i) => finding({ value, masked: '#' + i })));
    const [out, ms] = timed(() => mask(values.join('|')));
    expect(out).toBe(values.map((_, i) => '#' + i).join('|'));
    expect(ms).toBeLessThan(1000);
    // 겹치는 접두 — 같은 위치에서 긴 값, 짧은 값만 있으면 짧은 값
    const prefixes = rawValueMasker([finding({ value: base.slice(0, 40000), masked: 'S' }), finding({ value: base, masked: 'L' })]);
    expect(prefixes(base + '|' + base.slice(0, 50000))).toBe('L|S' + base.slice(40000, 50000));
  });

  it('짧은 값 600개 × 240줄 — 0.5초 안', () => {
    const values = Array.from({ length: 600 }, (_, i) => String.fromCodePoint(0xe100 + i).repeat(8));
    const mask = rawValueMasker(values.map((value, i) => finding({ value, masked: '#' + i })));
    const lines = Array.from({ length: 240 }, (_, i) => values[i] + ' | ' + values[(i + 200) % 600] + ' | ' + values[(i + 400) % 600]);
    const t0 = performance.now();
    const out = lines.map(mask);
    const ms = performance.now() - t0;
    expect(out.every((s, i) => s === '#' + i + ' | #' + ((i + 200) % 600) + ' | #' + ((i + 400) % 600))).toBe(true);
    expect(ms).toBeLessThan(500);
  });

  it('같은 글은 같은 결과(다시 부르면 저장한 결과)', () => {
    const mask = rawValueMasker([finding({ value: '홍길동', masked: '홍*동' })]);
    const first = mask('이름 홍길동');
    expect(mask('이름 홍길동')).toBe(first);
    expect(first).toBe('이름 홍*동');
    expect(mask('다른 글')).toBe('다른 글');
  });

  it('매칭 경로에 엔진 검색(indexOf · includes · split · 정규식)이 없다', () => {
    const src = readFileSync(new URL('./report-safe.ts', import.meta.url), 'utf8');
    const code = src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
    expect(code).not.toMatch(/\.(indexOf|lastIndexOf|includes|split|search|match|matchAll|replace|replaceAll)\(|new RegExp|RegExp\(/);
  });
});

describe('reportSafeAnalysis — 실제 분석', () => {
  it('원문 값 지우기 — evidence · live.value 빈 값(다른 live 필드 그대로), raw.result null', () => {
    const a = liveAnalysis();
    const s = reportSafeAnalysis(a);
    expect(s).not.toBe(a);
    expect(s.findings).toHaveLength(a.findings.length);
    s.findings.forEach((f, i) => {
      expect(f.evidence).toBe('');
      expect(f.live?.value).toBe('');
      expect({ ...f.live, value: 'X' }).toEqual({ ...a.findings[i].live, value: 'X' });
      expect(f.masked).toBe(a.findings[i].masked);
    });
    expect(s.raw?.result).toBeNull();
    expect(s.raw?.detailReady).toBe(true);
    expect(s.raw?.reviewable).toBe(true);
    // 결과 JSON 이 없어도 원래 값이 하나도 남지 않는다
    const raws = a.findings.map((f) => f.live!.value).filter((v, i) => v && Array.from(v).length >= 2 && v !== a.findings[i].masked);
    expect(raws.length).toBeGreaterThan(0);
    const json = JSON.stringify(s);
    expect(raws.filter((v) => json.includes(v)).length).toBe(0);
  });

  it('워크플로우 글(위험 사유 · 권장 조치 · 판단 근거 · overall 원문)의 원문 값 → masked, 담당자 글 · 이름 · 이력은 그대로', () => {
    const a = planted(
      [
        { value: '홍길동', masked: '홍*동' },
        { value: '900101-1234567', masked: '900101-1******' },
        { value: '1234567', masked: '' },
      ],
      { reason: '근거 홍길동 · 900101-1234567', overall: '- 사유 900101-1234567 확인\n- 짧은 1234567', next: '- 조치 홍길동 가림' },
    );
    const withUser: Analysis = {
      ...a,
      name: '홍길동 분석',
      memo: '메모 홍길동',
      completionNote: '완료 900101-1234567',
      findings: a.findings.map((f, i) => (i === 0 ? { ...f, memo: '항목 메모 홍길동', fpNote: '사유 홍길동', reclassNote: '수정 홍길동' } : f)),
      history: [{ id: 'H1', at: '2026-11-04 10:00', actor: '이지은', kind: 'memo', target: '분석 건', change: '홍길동', reason: '홍길동' }],
    };
    const before = structuredClone(withUser);
    const s = reportSafeAnalysis(withUser);
    expect(s.findings[0].reason).toBe('근거 홍*동 · 900101-1******');
    expect(s.riskReasons).toEqual(['사유 900101-1****** 확인', '짧은 *******']);
    expect(s.recs).toEqual(['조치 홍*동 가림']);
    expect(s.raw?.overall?.text).toBe('- 사유 900101-1****** 확인\n- 짧은 *******');
    expect(s.raw?.overall?.nextText).toBe('- 조치 홍*동 가림');
    // 담당자 글 · 이름 · 이력 그대로
    expect(s.name).toBe('홍길동 분석');
    expect(s.memo).toBe('메모 홍길동');
    expect(s.completionNote).toBe('완료 900101-1234567');
    expect(s.findings[0]).toMatchObject({ memo: '항목 메모 홍길동', fpNote: '사유 홍길동', reclassNote: '수정 홍길동' });
    expect(s.history).toEqual(withUser.history);
    // 원래 객체는 그대로
    expect(withUser).toEqual(before);
    expect(withUser.findings[0].reason).toBe('근거 홍길동 · 900101-1234567');
    expect(withUser.findings[0].live?.value).toBe('홍길동');
    expect(withUser.raw?.result).not.toBeNull();
  });

  it('isLiveAnalysis · isReportTarget — 대기 · 실패 · 옛 형식 · 검토 기록 없음은 대상이 아님', () => {
    expect(isReportTarget(liveAnalysis())).toBe(true);
    expect(isReportTarget(liveAnalysis(undefined, null))).toBe(false);
    expect(isReportTarget(toAnalysis(analysisOut()))).toBe(false);
    expect(isReportTarget(toAnalysis(analysisOut({ status: 'failed', error: 'x' })))).toBe(false);
    expect(isReportTarget(toAnalysis(analysisOut({ status: 'done', result: { format: 'imask-upstage-v1' }, review: NEW_REVIEW })))).toBe(false);
    expect(isLiveAnalysis(toAnalysis(analysisOut()))).toBe(true);
  });
});

describe('reportSafeAnalysis — 데모 분석은 같은 객체', () => {
  it('raw 가 없으면 받은 값을 그대로 돌려준다', async () => {
    const a = await createService().get('A1');
    if (!a) throw new Error('A1');
    expect(isLiveAnalysis(a)).toBe(false);
    expect(isReportTarget(a)).toBe(false);
    expect(reportSafeAnalysis(a)).toBe(a);
  });
});

describe('reportClock — 실제 분석은 서울 시각, 데모는 브라우저 시각', () => {
  it('UTC 15:00 은 서울 다음 날 00:00', async () => {
    const at = new Date('2026-11-04T15:00:30Z');
    expect(reportClock(liveAnalysis(), at)).toBe('2026-11-05 00:00');
    const demo = await createService().get('A1');
    if (!demo) throw new Error('A1');
    const local = `${at.getFullYear()}-${String(at.getMonth() + 1).padStart(2, '0')}-${String(at.getDate()).padStart(2, '0')} ${String(at.getHours()).padStart(2, '0')}:${String(at.getMinutes()).padStart(2, '0')}`;
    expect(reportClock(demo, at)).toBe(local);
  });
});
