import { describe, expect, it } from 'vitest';
import { createService, getDemoControls } from '@/services';
import type { Analysis } from '@/services/types';
import {
  DEFAULT_FILTERS,
  dropdownModels,
  filtersToQuery,
  isFiltered,
  listModel,
  parseFilters,
  replaySignature,
  type ListFilters,
} from './listModel';

/** 서비스가 주는 목록(샘플을 직접 가져오지 않는다) */
async function sampleList(): Promise<Analysis[]> {
  const svc = createService();
  return svc.list();
}

const F = (patch: Partial<ListFilters> = {}): ListFilters => ({ ...DEFAULT_FILTERS, ...patch });

describe('목록 필터 ↔ URL 검색 파라미터', () => {
  it('기본값은 빼고 q · risk · status · review · sort 순서로 쓴다', () => {
    expect(filtersToQuery(F())).toBe('');
    expect(filtersToQuery(F({ sort: 'risk', review: 'needed', q: '김 서연' }))).toBe('q=%EA%B9%80+%EC%84%9C%EC%97%B0&review=needed&sort=risk');
  });

  it('모르는 값은 기본값으로 읽고, 쓴 값은 그대로 다시 읽힌다', () => {
    expect(parseFilters(new URLSearchParams('risk=bogus&status=toString&review=needed&sort=x'))).toEqual(F({ review: 'needed' }));
    const f = F({ q: '전세 계약서', risk: 'high', status: 'failed', review: 'done', sort: 'risk' });
    expect(parseFilters(new URLSearchParams(filtersToQuery(f)))).toEqual(f);
  });

  it('정렬은 걸러 보기가 아니다 · 검색어 공백만은 걸러 보기가 아니다', () => {
    expect(isFiltered(F({ sort: 'risk' }))).toBe(false);
    expect(isFiltered(F({ q: '   ' }))).toBe(false);
    expect(isFiltered(F({ q: 'a' }))).toBe(true);
  });

  it('행 다시 등장 서명은 필터·정렬만 본다(검색어 제외)', () => {
    expect(replaySignature(F({ q: 'a' }))).toBe(replaySignature(F()));
    expect(replaySignature(F({ risk: 'high' }))).not.toBe(replaySignature(F()));
  });
});

describe('listModel — 프로토타입 listVM 규칙', () => {
  it('요약 숫자와 머리말은 서비스 데이터에서 센다', async () => {
    const all = await sampleList();
    const m = listModel(all, F());
    const high = all.filter((a) => a.risk === 'high').length;
    const needed = all.filter((a) => a.review === 'needed').length;
    expect(m.total).toBe(all.length);
    expect(m.cards.map((c) => c.n)).toEqual([all.length, high, needed]);
    expect(m.cards.map((c) => c.on)).toEqual([true, false, false]);
    expect(m.heroLead + m.heroStrong + m.heroTail).toBe(needed ? `검토를 기다리는 분석이 ${needed}건 있습니다.` : '검토를 기다리는 분석이 없습니다.');
    expect(m.basis).toBe(''); // 걸러 보지 않을 때는 '전체 n건'과 같은 말이라 기준 칩을 그리지 않는다
    expect(m.resultText).toBe(`전체 ${all.length}건`);
    expect(m.rows).toHaveLength(all.length);
  });

  it('최근 접수순 · 위험도순(같으면 최근 접수순)', async () => {
    const all = await sampleList();
    const recent = listModel(all, F()).rows;
    for (let i = 1; i < recent.length; i++) expect(recent[i - 1].date >= recent[i].date).toBe(true);
    const rank: Record<string, number> = { high: 3, medium: 2, low: 1, unrated: 0 };
    const byRisk = listModel(all, F({ sort: 'risk' })).rows;
    for (let i = 1; i < byRisk.length; i++) {
      const a = rank[byRisk[i - 1].risk];
      const b = rank[byRisk[i].risk];
      expect(a >= b).toBe(true);
      if (a === b) expect(byRisk[i - 1].date >= byRisk[i].date).toBe(true);
    }
  });

  it('검색(분석명 · 파일명, 대소문자 무시) · 필터 · 결과 문구', async () => {
    const all = await sampleList();
    const target = all[0];
    const byFile = listModel(all, F({ q: '  ' + target.docs[0].name.toUpperCase() + ' ' }));
    expect(byFile.rows.some((r) => r.id === target.id)).toBe(true);
    expect(byFile.filtered).toBe(true);
    expect(byFile.basis).toBe('검색 결과 기준');
    expect(byFile.resultText).toBe(`${byFile.rows.length}건 표시 · 전체 ${all.length}건 중`);

    const m = listModel(all, F({ review: 'needed' }));
    expect(m.rows.every((r) => r.review === 'needed')).toBe(true);
    expect(m.cards[2].on).toBe(true);
    expect(m.cards[0].on).toBe(false);
    const fHigh = m.rows.filter((r) => r.risk === 'high').length;
    expect(m.resultSub).toBe(`이 중 상 등급 ${fHigh}건 · 검토 대기 ${m.rows.length}건`);
  });

  it('검색 결과 없음 문구 — 검색어가 있으면 따옴표로, 없으면 필터 문구', async () => {
    const all = await sampleList();
    const q = listModel(all, F({ q: ' 전세 계약서 ' }));
    expect(q.noResults).toBe(true);
    expect(q.noResultsText).toBe('‘전세 계약서’에 맞는 분석명이나 파일명이 없습니다. 검색어를 바꾸거나 필터를 초기화해 보세요.');
    const none = listModel(all, F({ q: '', risk: 'high', status: 'queued', review: 'done' }));
    expect(none.noResults).toBe(true);
    expect(none.noResultsText).toBe('선택한 필터에 맞는 분석 건이 없습니다. 필터를 바꾸거나 초기화해 보세요.');
  });

  it('행 — 파일 요약 · 분석 상태 아래 글자 · 실패 건', async () => {
    const all = await sampleList();
    const rows = listModel(all, F()).rows;
    for (const a of all) {
      const r = rows.find((x) => x.id === a.id)!;
      expect(r.files).toBe(a.docs.length > 1 ? `${a.docs[0].name} 외 ${a.docs.length - 1}개` : a.docs[0]?.name ?? '-');
      expect(r.failed).toBe(a.status === 'failed');
      if (a.status === 'partial') expect(r.sub).toBe(`문서 ${a.docs.filter((d) => d.status === 'failed').length}개 처리 실패`);
    }
  });

  it('비어 있으면 empty', async () => {
    const svc = createService();
    await getDemoControls(svc)!.clearAll();
    const m = listModel(await svc.list(), F());
    expect(m.empty).toBe(true);
    expect(m.hasData).toBe(false);
  });
});

describe('드롭다운 — 건수는 전체 목록 기준', () => {
  it('위험등급 · 분석 상태 · 검토 상태 건수, 정렬 선택지 2개', async () => {
    const all = await sampleList();
    const [risk, status, review, sort] = dropdownModels(all);
    expect(risk.options.map((o) => o.label)).toEqual(['전체', '상', '중', '하', '미평가']);
    expect(status.options.map((o) => o.label)).toEqual(['전체', '대기', '분석 중', '완료', '일부 실패', '실패']);
    expect(review.options.map((o) => o.label)).toEqual(['전체', '미검토', '검토 대기', '검토 완료']);
    expect(sort.options.map((o) => o.label)).toEqual(['최근 접수순', '위험도순']);
    expect(risk.options[0].count).toBe(all.length);
    expect(risk.options.slice(1).reduce((n, o) => n + (o.count ?? 0), 0)).toBe(all.length);
    expect(status.options.find((o) => o.value === 'failed')?.count).toBe(all.filter((a) => a.status === 'failed').length);
    expect(review.options.find((o) => o.value === 'needed')?.count).toBe(all.filter((a) => a.review === 'needed').length);
    expect(sort.options.every((o) => o.count === undefined)).toBe(true);
  });
});
