import { describe, expect, it } from 'vitest';
import { FSTATUS, HKIND, RISK } from '@/display/rules';
import { createService, getDemoControls } from '@/services';
import type { Analysis } from '@/services/types';
import { reportView } from './reportModel';

/** 서비스가 주는 분석 건(샘플을 직접 가져오지 않는다) */
async function analysis(id: string, state?: 'report'): Promise<Analysis> {
  const svc = createService();
  if (state) await getDemoControls(svc)?.prepare(state);
  const a = await svc.get(id);
  if (!a) throw new Error('없는 분석: ' + id);
  return a;
}

describe('보고서 화면 모델 — 원본 reportVM', () => {
  it('report 상태(A1, demoProgressA1): 머리 · 요약 숫자 · 분포', async () => {
    const a = await analysis('A1', 'report');
    const v = reportView(a);
    expect(v.code).toBe('DG-20261030-0007');
    expect(v.name).toBe('대출상담 서류 묶음');
    expect(v.risk).toBe('high');
    expect(v.review).toBe('done');
    expect(v.notDone).toBe(false);
    expect(v.completedText).toBe('이지은 · 2026.10.30 16:40');

    const f = a.findings;
    const high = f.filter((x) => x.risk === 'high').length;
    const medium = f.filter((x) => x.risk === 'medium').length;
    const low = f.filter((x) => x.risk === 'low').length;
    const reviewed = f.filter((x) => x.status !== 'open').length;
    expect(v.cards.map((c) => c.label)).toEqual(['탐지 항목', '담당자 확인', '남은 검토사항', '문서 간 연결']);
    expect(v.cards[0]).toMatchObject({ num: f.length, unit: '건', after: '', sub: `높음 ${high} · 보통 ${medium} · 낮음 ${low}` });
    expect(v.cards[1]).toMatchObject({ num: reviewed, unit: '', after: '/ ' + f.length });
    const openI = a.items.filter((i) => !i.resolved).length;
    expect(v.cards[2]).toMatchObject({ num: openI, warn: openI > 0, sub: `전체 ${a.items.length}건 중 해결 ${a.items.length - openI}건` });
    expect(v.cards[3].sub).toBe('모두 확인 · 판단 완료');

    expect(v.dist.map((d) => [d.key, d.n, d.color, d.index])).toEqual(
      [
        ['high', high, RISK.high.solid],
        ['medium', medium, RISK.medium.solid],
        ['low', low, RISK.low.solid],
      ]
        .filter((d) => (d[1] as number) > 0)
        .map((d, i) => [...d, i]),
    );
    expect(v.distAria).toBe('위험등급별 탐지 분포: ' + v.dist.map((d) => `${d.label} ${d.n}건`).join(', '));
  });

  it('표시값은 마스킹된 값만 — 원문 위치 조각의 원래 값(x)은 보고서 어디에도 없다', async () => {
    const a = await analysis('A1', 'report');
    const v = reportView(a);
    expect(v.findings.map((x) => x.masked)).toEqual(
      a.findings
        .slice()
        .sort((x, y) => (x.id < y.id ? -1 : 1))
        .map((x) => x.masked),
    );
    const raws = new Set<string>();
    for (const d of a.docs)
      for (const page of d.pages ?? [])
        for (const block of page) {
          const walk = (val: unknown): void => {
            if (Array.isArray(val)) val.forEach(walk);
            else if (val && typeof val === 'object') {
              const o = val as Record<string, unknown>;
              if (typeof o.a === 'string' && typeof o.x === 'string' && typeof o.m === 'string' && o.x !== o.m && o.x.length >= 6) raws.add(o.x);
              else Object.values(o).forEach(walk);
            }
          };
          walk(block);
        }
    expect(raws.size).toBeGreaterThan(0);
    const json = JSON.stringify(v);
    for (const raw of raws) expect(json.includes(raw), raw).toBe(false);
  });

  it('문서 표 · 정보 종류 표 · 남은 검토사항 · 수정 표', async () => {
    const a = await analysis('A1', 'report');
    const v = reportView(a);
    expect(v.docs).toHaveLength(a.docs.length);
    const d0 = v.docs[0];
    expect(d0.meta).toMatch(/^(PDF|JPG|PNG) · (\d+페이지|페이지 확인 불가)$/);
    expect(typeof d0.nFind).toBe('number');
    // 정보 종류 표는 ② CATS 순서, 0건은 빠진다
    expect(v.cats.every((c) => c.n > 0)).toBe(true);
    expect(v.cats.reduce((s, c) => s + c.n, 0)).toBe(a.findings.length);
    // 남은 검토사항 = 해결하지 않은 것
    expect(v.remaining.map((r) => r.id)).toEqual(a.items.filter((i) => !i.resolved).map((i) => i.id));
    // 수정 표 — 오탐(F-10)과 분류 수정(F-12)
    const f10 = v.changes.find((c) => c.id === 'F-10');
    const f12 = v.changes.find((c) => c.id === 'F-12');
    expect(f10?.now).toMatch(/^오탐 \(/);
    expect(f10?.at).toBe('2026.10.30 16:10');
    expect(f12?.now).toContain('기타 · 은행 직원');
    expect(f12?.reason).toBe('상담 직원 서명란에 적힌 직원 성명');
  });

  it('검토 기록 — ② 이력 구분 라벨과 구분별 색(토큰), 사유가 없으면 -', async () => {
    const a = await analysis('A1', 'report');
    const v = reportView(a);
    expect(v.history).toHaveLength(a.history.length);
    const first = v.history[0];
    expect(first.kind).toBe(HKIND[a.history[0].kind]);
    const complete = v.history.find((h) => h.kind === HKIND.complete);
    expect(complete).toMatchObject({ kindFg: 'var(--accent-ink)', dot: 'var(--accent)' });
    for (const h of v.history) {
      expect(h.dot).toMatch(/^var\(--[a-z0-9-]+\)$/);
      expect(h.kindFg).toMatch(/^var\(--[a-z0-9-]+\)$/);
      expect(h.reason.length).toBeGreaterThan(0);
    }
  });

  it('등급·확인 상태 라벨은 ② 한 곳에서 — ② 라벨을 바꾸면 요약 카드 설명·분포·수정 표가 함께 바뀐다', async () => {
    const a = await analysis('A1', 'report');
    // 실행 중 객체만 잠깐 바꿨다가 되돌린다(② 의 타입은 readonly)
    const risk = RISK as unknown as Record<'high' | 'medium' | 'low', { label: string }>;
    const fstatus = FSTATUS as unknown as Record<'false_positive' | 'reclassified', { label: string }>;
    const saved = [risk.high.label, risk.medium.label, risk.low.label, fstatus.false_positive.label, fstatus.reclassified.label];
    try {
      risk.high.label = '검증 상';
      risk.medium.label = '검증 중';
      risk.low.label = '검증 하';
      fstatus.false_positive.label = '검증 오탐';
      fstatus.reclassified.label = '검증 수정';
      const v = reportView(a);
      const n = (k: 'high' | 'medium' | 'low') => a.findings.filter((x) => x.risk === k).length;
      expect(v.cards[0].sub).toBe(`검증 상 ${n('high')} · 검증 중 ${n('medium')} · 검증 하 ${n('low')}`);
      const fp = a.findings.filter((x) => x.status === 'false_positive').length;
      const recl = a.findings.filter((x) => x.status === 'reclassified').length;
      expect(v.cards[1].sub).toBe(`검증 오탐 ${fp} · 검증 수정 ${recl}`);
      expect(v.dist.map((d) => d.label)).toEqual(['검증 상', '검증 중', '검증 하'].slice(0, v.dist.length));
      expect(v.changes.find((c) => c.id === 'F-10')?.now).toMatch(/^검증 오탐 \(/);
    } finally {
      [risk.high.label, risk.medium.label, risk.low.label, fstatus.false_positive.label, fstatus.reclassified.label] = saved;
    }
    expect(reportView(a).cards[0].sub).toMatch(/^높음 \d+ · 보통 \d+ · 낮음 \d+$/);
  });

  it('검토가 끝나지 않은 분석(A4) — 미완료 안내 · 완료 전 문구 · 분석 한계', async () => {
    const a = await analysis('A4');
    const v = reportView(a);
    expect(v.notDone).toBe(true);
    expect(v.completedText).toBe('검토 진행 중 (완료 전)');
    expect(v.status).toBe('partial');
    expect(v.limits).toBe(a.limits);
  });

  it('분석 중(A3)·실패(A6) — 사유 없음 문구, 끝나지 않은 문서의 숫자는 -', async () => {
    const a3 = reportView(await analysis('A3'));
    expect(a3.noReasonsText).toBe('분석이 끝나면 위험 사유가 표시됩니다.');
    const a6 = reportView(await analysis('A6'));
    expect(a6.reasons).toEqual([]);
    expect(a6.noReasonsText).toBe('분석에 실패해 위험 사유를 판단하지 못했습니다.');
    expect(a6.docs.every((d) => d.nFind === '-' && d.nHigh === '-' && d.reviewed === '-')).toBe(true);
    expect(a6.dist).toEqual([]);
    expect(a6.distAria).toBe('위험등급별 탐지 분포: 탐지 없음');
    expect(a6.cards[3].sub).toBe('찾은 연결 없음');
    expect(a6.memo).toBe('작성한 검토 메모가 없습니다.');
    expect(a6.hasMemo).toBe(false);
  });
});
