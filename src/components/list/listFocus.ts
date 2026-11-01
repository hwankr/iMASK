import type { ListFilters } from './listModel';

/* ==========================================================================
   목록 조작 기준점 — 목록 오류 모달을 닫을 때 포커스가 돌아갈 자리.
   여는 버튼('오류 확인')은 '다시 시도'하는 동안 사라진다. 일반 목록에서는 같은 행이 '분석 중'으로 남지만,
   실패 필터(`?status=failed`)에서는 행 자체가 잠시 목록에서 빠진다. 그래서 열 때 그 행의 앞뒤 행과
   걸려 있던 필터를 기억해 두고, 닫을 때 지금 화면에 남아 있는 첫 자리로 보낸다:
     1) 같은 행의 '오류 확인' → 같은 행의 '상세 보기'
     2) 그 행 다음 행들의 '상세 보기'(가까운 순) → 이전 행들의 '상세 보기'(가까운 순)
     3) 걸려 있던 필터의 트리거(분석 상태 → 위험등급 → 검토 상태) → 검색칸
   ========================================================================== */

/** 목록 도구 줄의 검색칸 · 필터 트리거 id — 목록은 한 화면에 하나만 그린다 */
export const LIST_CONTROL_IDS = {
  search: 'dg-list-search',
  risk: 'dg-list-filter-risk',
  status: 'dg-list-filter-status',
  review: 'dg-list-filter-review',
} as const;

/** 행 버튼 표시(`data-row-action`) — 표 · 휴대폰 카드 공통 */
export type RowAction = 'error' | 'open';

/** 오류 모달을 열 때 기억하는 목록 조작 기준점 */
export interface ListAnchor {
  /** 오류를 연 행(분석 ID) */
  id: string;
  /** 같은 목록에서 그 행 뒤의 행들 — 가까운 순 */
  after: string[];
  /** 그 행 앞의 행들 — 가까운 순 */
  before: string[];
  /** 마지막으로 돌아갈 도구 줄 조작 id — 걸려 있던 필터 트리거, 맨 끝은 검색칸 */
  controls: string[];
}

/** 지금 화면에서 행 버튼 · 도구 줄 조작을 찾는 방법(시험에서는 가짜로 바꾼다) */
export interface ListLookup<T> {
  rowAction(rowId: string, action: RowAction): T | null;
  control(id: string): T | null;
}

/** 열 때의 행 순서(화면 위→아래)와 필터로 기준점을 만든다 */
export function makeListAnchor(id: string, order: readonly string[], filters: Pick<ListFilters, 'risk' | 'status' | 'review'>): ListAnchor {
  const i = order.indexOf(id);
  const controls: string[] = [];
  if (filters.status !== 'all') controls.push(LIST_CONTROL_IDS.status);
  if (filters.risk !== 'all') controls.push(LIST_CONTROL_IDS.risk);
  if (filters.review !== 'all') controls.push(LIST_CONTROL_IDS.review);
  controls.push(LIST_CONTROL_IDS.search);
  return {
    id,
    after: i < 0 ? [] : order.slice(i + 1),
    before: i < 0 ? [] : order.slice(0, i).reverse(),
    controls,
  };
}

/** 기준점에서 지금 남아 있는 첫 자리 — 없으면 null */
export function pickListReturn<T>(anchor: ListAnchor, lookup: ListLookup<T>): T | null {
  const same = lookup.rowAction(anchor.id, 'error') ?? lookup.rowAction(anchor.id, 'open');
  if (same) return same;
  for (const rowId of [...anchor.after, ...anchor.before]) {
    const open = lookup.rowAction(rowId, 'open');
    if (open) return open;
  }
  for (const id of anchor.controls) {
    const el = lookup.control(id);
    if (el) return el;
  }
  return null;
}

/** 문서에서 찾기 — 표 행 · 휴대폰 카드 모두 `data-analysis-id` 를 가진다 */
function domLookup(root: Document): ListLookup<HTMLElement> {
  return {
    rowAction: (rowId, action) =>
      root.querySelector<HTMLElement>(`[data-analysis-id="${CSS.escape(rowId)}"] [data-row-action="${action}"]`),
    control: (id) => root.getElementById(id),
  };
}

/** 오류 모달을 여는 순간 — 그 행과 같은 목록의 행 순서를 화면에서 읽어 기준점을 만든다 */
export function captureListAnchor(id: string, filters: Pick<ListFilters, 'risk' | 'status' | 'review'>, root: Document = document): ListAnchor {
  const row = root.querySelector(`[data-analysis-id="${CSS.escape(id)}"]`);
  const order = row?.parentElement
    ? [...row.parentElement.children].map((el) => el.getAttribute('data-analysis-id')).filter((v): v is string => !!v)
    : [id];
  return makeListAnchor(id, order, filters);
}

/** 오류 모달이 닫힐 때 — 기준점에서 지금 화면에 남아 있는 첫 자리 */
export function findListReturn(anchor: ListAnchor, root: Document = document): HTMLElement | null {
  return pickListReturn(anchor, domLookup(root));
}
