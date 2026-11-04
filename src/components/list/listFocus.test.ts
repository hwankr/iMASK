import { describe, expect, it } from 'vitest';
import { LIST_CONTROL_IDS, makeListAnchor, pickDeleteReturn, pickListReturn, type ListLookup, type RowAction, requestListFocusOnArrive, takeListFocusOnArrive } from './listFocus';

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

describe('상세에서 지운 뒤 목록에 왔을 때 — 한 번 검색칸으로', () => {
  const body = { isConnected: true };
  const search = { id: 'dg-list-search', isConnected: true };
  const fakeDoc = (active: unknown) =>
    ({ activeElement: active, body, getElementById: (id: string) => (id === 'dg-list-search' ? search : null) }) as unknown as Document;

  it('요청이 없으면 null', () => {
    expect(takeListFocusOnArrive(fakeDoc(body))).toBeNull();
  });

  it('요청이 있으면 포커스가 빠져 있을 때(body) 검색칸 — 한 번만', () => {
    requestListFocusOnArrive();
    expect(takeListFocusOnArrive(fakeDoc(body))).toBe(search);
    expect(takeListFocusOnArrive(fakeDoc(body))).toBeNull();
  });

  it('그사이 다른 곳에 포커스가 있으면 그대로(null) — 요청은 써 버린다', () => {
    requestListFocusOnArrive();
    expect(takeListFocusOnArrive(fakeDoc({ isConnected: true }))).toBeNull();
    expect(takeListFocusOnArrive(fakeDoc(body))).toBeNull();
  });
});

describe('삭제 확인 창이 닫힐 때 돌아갈 자리 — 기준점, 없으면 본문의 첫 조작(마지막 행 삭제)', () => {
  const NEW = '#main 새 분석';
  const withFirst = (s: ListLookup<string>, first: string | null = NEW) => ({ ...s, firstControl: () => first });

  it('이웃 행이 남아 있으면 그 행의 상세 보기(기준점 그대로)', () => {
    const a = makeListAnchor('A6', ORDER, NONE);
    expect(pickDeleteReturn(a, withFirst(screen(['A4:open', 'A5:open'], ALL_CONTROLS)))).toBe('A4:open');
  });

  it('행은 없고 도구 줄이 남아 있으면 검색칸(필터로 비었을 때)', () => {
    const a = makeListAnchor('A6', ORDER, NONE);
    expect(pickDeleteReturn(a, withFirst(screen([], ALL_CONTROLS)))).toBe(LIST_CONTROL_IDS.search);
  });

  it('마지막 행을 지워 행 · 도구 줄이 모두 사라졌으면 본문의 첫 조작(빈 목록의 새 분석)', () => {
    const only = makeListAnchor('A1', ['A1'], NONE);
    expect(pickDeleteReturn(only, withFirst(screen([], [])))).toBe(NEW);
    const filtered = makeListAnchor('A1', ['A1'], { ...NONE, status: 'failed', risk: 'high' });
    expect(pickDeleteReturn(filtered, withFirst(screen([], [])))).toBe(NEW);
  });

  it('본문에도 조작이 없으면 null(공통 Modal 이 아무것도 하지 않는다)', () => {
    expect(pickDeleteReturn(makeListAnchor('A1', ['A1'], NONE), withFirst(screen([], []), null))).toBeNull();
  });

  it('오류 모달의 돌아갈 자리(pickListReturn)는 그대로 — 본문 첫 조작으로 넓히지 않는다', () => {
    expect(pickListReturn(makeListAnchor('A1', ['A1'], NONE), screen([], []))).toBeNull();
  });
});
