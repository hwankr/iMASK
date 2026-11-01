import { describe, expect, it } from 'vitest';
import { LIST_CONTROL_IDS, makeListAnchor, pickListReturn, type ListLookup, type RowAction } from './listFocus';

const NONE = { risk: 'all', status: 'all', review: 'all' } as const;
const ORDER = ['A1', 'A2', 'A6', 'A4', 'A5'];

/** 가짜 화면 — 남아 있는 행 버튼('A4:open' 꼴)과 조작 id 만 찾는다 */
function screen(rows: string[], controls: string[] = []): ListLookup<string> {
  return {
    rowAction: (id: string, action: RowAction) => (rows.includes(`${id}:${action}`) ? `${id}:${action}` : null),
    control: (id: string) => (controls.includes(id) ? id : null),
  };
}
const ALL_CONTROLS = Object.values(LIST_CONTROL_IDS);

describe('목록 조작 기준점 — 오류 모달을 닫을 때 돌아갈 자리', () => {
  it('열 때의 행 순서에서 뒤 행 · 앞 행을 가까운 순으로 기억한다', () => {
    const a = makeListAnchor('A6', ORDER, NONE);
    expect(a.after).toEqual(['A4', 'A5']);
    expect(a.before).toEqual(['A2', 'A1']);
  });

  it('행이 목록에 없었으면 앞뒤 행은 비운다', () => {
    expect(makeListAnchor('A9', ORDER, NONE)).toMatchObject({ after: [], before: [] });
  });

  it('걸려 있던 필터 트리거(분석 상태 → 위험등급 → 검토 상태) 다음 맨 끝에 검색칸', () => {
    expect(makeListAnchor('A6', ['A6'], { ...NONE, status: 'failed' }).controls).toEqual([LIST_CONTROL_IDS.status, LIST_CONTROL_IDS.search]);
    expect(makeListAnchor('A6', ['A6'], { risk: 'unrated', status: 'failed', review: 'needed' }).controls).toEqual([
      LIST_CONTROL_IDS.status,
      LIST_CONTROL_IDS.risk,
      LIST_CONTROL_IDS.review,
      LIST_CONTROL_IDS.search,
    ]);
    expect(makeListAnchor('A6', ['A6'], NONE).controls).toEqual([LIST_CONTROL_IDS.search]);
  });

  const filtered = makeListAnchor('A6', ORDER, { ...NONE, status: 'failed' });

  it("같은 행이 남아 있으면 '오류 확인', 없으면 같은 행 '상세 보기'(일반 목록의 기존 동작)", () => {
    expect(pickListReturn(filtered, screen(['A6:error', 'A6:open', 'A4:open'], ALL_CONTROLS))).toBe('A6:error');
    expect(pickListReturn(filtered, screen(['A6:open', 'A4:open'], ALL_CONTROLS))).toBe('A6:open');
  });

  it("행이 빠졌으면 남은 다음 행 '상세 보기' → 이전 행 '상세 보기'(가까운 순)", () => {
    expect(pickListReturn(filtered, screen(['A1:open', 'A2:open', 'A4:open', 'A5:open'], ALL_CONTROLS))).toBe('A4:open');
    expect(pickListReturn(filtered, screen(['A1:open', 'A2:open', 'A5:open'], ALL_CONTROLS))).toBe('A5:open');
    expect(pickListReturn(filtered, screen(['A1:open', 'A2:open'], ALL_CONTROLS))).toBe('A2:open');
    // 이웃 행의 '오류 확인'은 고르지 않는다(상세 보기만)
    expect(pickListReturn(filtered, screen(['A4:error', 'A1:open'], ALL_CONTROLS))).toBe('A1:open');
  });

  it('남은 행이 없으면 걸린 필터 트리거, 그것도 없으면 검색칸, 아무것도 없으면 null', () => {
    expect(pickListReturn(filtered, screen([], ALL_CONTROLS))).toBe(LIST_CONTROL_IDS.status);
    expect(pickListReturn(filtered, screen([], [LIST_CONTROL_IDS.search]))).toBe(LIST_CONTROL_IDS.search);
    expect(pickListReturn(filtered, screen([], []))).toBeNull();
  });

  it('필터 없는 기준점은 같은 행 다음 곧바로 앞뒤 행, 마지막은 검색칸', () => {
    const plain = makeListAnchor('A6', ORDER, NONE);
    expect(pickListReturn(plain, screen(['A5:open'], ALL_CONTROLS))).toBe('A5:open');
    expect(pickListReturn(plain, screen([], ALL_CONTROLS))).toBe(LIST_CONTROL_IDS.search);
  });
});
