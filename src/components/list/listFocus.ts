import { getFocusable } from '@/lib/hooks';
import type { ListFilters } from './listModel';

/* ==========================================================================
   목록 조작 기준점 — 목록 오류 모달을 닫을 때 포커스가 돌아갈 자리.
   여는 버튼('오류 확인')은 '다시 시도'하는 동안 사라진다. 일반 목록에서는 같은 행이 '분석 중'으로 남지만,
   실패 필터(`?status=failed`)에서는 행 자체가 잠시 목록에서 빠진다. 그래서 열 때 그 행의 앞뒤 행과
   걸려 있던 필터를 기억해 두고, 닫을 때 지금 화면에 남아 있는 첫 자리로 보낸다:
     1) 같은 행의 '오류 확인' → 같은 행의 '상세 보기'
     2) 그 행 다음 행들의 '상세 보기'(가까운 순) → 이전 행들의 '상세 보기'(가까운 순)
     3) 걸려 있던 필터의 트리거(분석 상태 → 위험등급 → 검토 상태) → 검색칸
   삭제 확인 창도 같은 기준점을 쓰고, 마지막 행을 지워 그 자리가 모두 없어졌으면 본문의 첫 조작으로 보낸다(findDeleteReturn).
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

/** 본문(#main)의 첫 유효 조작 — 빈 목록이면 머리말의 '새 분석'. 없으면 null */
export function firstMainControl(root: Document = document): HTMLElement | null {
  const main = root.getElementById('main');
  return main ? (getFocusable(main)[0] ?? null) : null;
}

/* ---------- 삭제 확인 창이 닫힐 때 ----------
   지운 행(또는 이미 없던 행)은 창이 닫히는 순간 목록에서 빠진다. 기준점(pickListReturn — 이웃 행 → 걸린 필터 → 검색칸)을
   먼저 찾고, 마지막 행을 지워 표 · 도구 줄이 함께 사라졌으면 본문의 첫 조작(빈 목록의 '새 분석' 등)으로 보낸다.
   사용자가 그사이 다른 조작에 포커스를 두었으면 공통 Modal(useFocusReturn)이 그대로 둔다. */

/** 기준점의 자리, 없으면 본문의 첫 조작(firstControl) */
export function pickDeleteReturn<T>(anchor: ListAnchor, lookup: ListLookup<T> & { firstControl(): T | null }): T | null {
  return pickListReturn(anchor, lookup) ?? lookup.firstControl();
}

/** 삭제 확인 창이 닫힐 때 — 화면에서 찾는다 */
export function findDeleteReturn(anchor: ListAnchor, root: Document = document): HTMLElement | null {
  return pickDeleteReturn(anchor, { ...domLookup(root), firstControl: () => firstMainControl(root) });
}

/* ---------- 상세에서 지운 뒤 목록에 왔을 때 ----------
   화면 이동(Next)은 포커스를 옮기지 않는다 — 지운 상세의 버튼이 사라져 포커스가 문서 맨 앞(body)으로 빠진다.
   상세가 지운 뒤 목록으로 가기 직전에 requestListFocusOnArrive() 를 부르면, 목록이 데이터를 그린 뒤 한 번
   검색칸(없으면 본문의 첫 조작)으로 포커스를 옮긴다(그사이 사용자가 다른 곳에 포커스를 두었으면 그대로). */

let focusOnArrive = false;

/** 다음에 그려지는 목록이 한 번 포커스를 받게 한다 */
export function requestListFocusOnArrive(): void {
  focusOnArrive = true;
}

/** 목록이 데이터를 그린 뒤 — 요청이 있었으면(한 번만) 그 자리를 돌려준다 */
export function takeListFocusOnArrive(root: Document = document): HTMLElement | null {
  if (!focusOnArrive) return null;
  focusOnArrive = false;
  const now = root.activeElement;
  if (now && now !== root.body && (now as HTMLElement).isConnected) return null; // 이미 다른 곳에 포커스
  return root.getElementById(LIST_CONTROL_IDS.search) ?? firstMainControl(root);
}
