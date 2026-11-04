/* ==========================================================================
   목록 화면의 덧씌움 — 서비스가 새 목록을 주기 전까지 이 화면에서 한 일을 바로 보이게 한다(순수 함수).
   - hidden: 이 화면에서 지운 행(또는 지우려다 이미 없던 행) — 뺀다. 지운 뒤 포커스가 사라진 행 대신 이웃 행으로 가게
     창이 닫히는 순간 행이 빠져 있어야 한다.
   - retrying: 다시 분석 요청 중인 행 — '재시도 중'(기존 retrying 표시 그대로, 버튼 막힘).
   - started: 실제 분석에서 다시 분석을 시작한 행 — 새 목록이 올 때까지 '분석 중'(문서도 분석 중)으로 보인다.
   화면은 hidden · started 를 '덧씌울 때의 목록 데이터'와 함께 들고 있다가 데이터가 바뀌면(새 응답) 버린다 — 서버 값이 이긴다.
   retrying 은 요청이 끝날 때까지(데이터와 무관하게) 둔다.
   ========================================================================== */

import type { Analysis } from '@/services/types';

export interface ListOverlay {
  hidden: ReadonlySet<string>;
  retrying: ReadonlySet<string>;
  started: ReadonlySet<string>;
}

export const NO_OVERLAY: ListOverlay = { hidden: new Set(), retrying: new Set(), started: new Set() };

/** 덧씌운 목록 — 빠진 행 없이 순서 그대로, 바뀐 행만 새 객체 */
export function applyListOverlay(list: readonly Analysis[], o: ListOverlay): Analysis[] {
  const out: Analysis[] = [];
  for (const a of list) {
    if (o.hidden.has(a.id)) continue;
    if (o.started.has(a.id)) {
      out.push({
        ...a,
        status: 'running',
        retrying: false,
        analyzedAt: '',
        docs: a.docs.map((d) => ({ ...d, status: 'running', error: '' })),
      });
    } else if (o.retrying.has(a.id) && !a.retrying) {
      out.push({ ...a, retrying: true });
    } else {
      out.push(a);
    }
  }
  return out;
}
