/* ==========================================================================
   검토 동작 뒤 포커스 지키기.
   동작이 끝나면 누른 버튼이 다른 버튼으로 바뀌는 일이 많다(탐지 내용 확인 → 확인 취소, 오탐으로 표시 → 오탐 취소,
   해결로 표시 → 다시 열기, 검토 완료 → 검토 다시 열기). 그러면 모달이 돌려줄 버튼(또는 바로 누른 버튼)이 없어져
   포커스가 문서 맨 앞으로 빠진다. 누를 때 '어느 행(data-card)의 어느 자리(data-slot)'였는지 기억했다가,
   포커스가 빠졌으면 같은 자리의 새 버튼(없으면 그 행의 첫 버튼)으로 옮긴다. 원본에는 없는 보완이다.
   - 행 자체가 목록에서 빠지면(예: '미확인' 필터에서 확인 · 오탐 표시 · 분류 수정) 누를 때 기억한 행 순서로
     다음 남은 행의 펼치기 버튼 → 없으면 이전 행 → 남은 행이 없으면 구역(data-focus-region)의
     기준 자리(data-focus-home: 고른 필터 칩 → 고른 결과 탭)로 옮긴다.
   - 행 밖의 버튼(예: 일부 실패 띠의 '실패 문서 다시 분석')은 data-slot 만으로 다시 찾는다. 띠처럼 진행 중에
     버튼이 사라졌다가 다시 생기면, 다시 그려질 때까지 잠시(WATCH_MS) 기다렸다가 옮긴다.
   ========================================================================== */

import { getFocusable, scrollBehavior } from '@/lib/hooks';

/** 누른 자리 */
export interface FocusSpot {
  el: HTMLElement;
  /** 행(data-card) ID — 없으면 화면 전체에서 찾는다 */
  card: string | null;
  /** 같은 일을 하는 버튼 묶음(data-slot) — 예: 확인 ↔ 확인 취소 */
  slot: string | null;
  /** 누를 때 같은 목록에 있던 행 ID(화면 순서) — 그 행이 빠졌을 때 다음 · 이전 행을 찾는다 */
  order: string[];
  /** 행을 담은 구역(data-focus-region) — 예: 결과 패널 */
  region: string | null;
}

/** 새 데이터로 다시 그려질 때까지 기다리는 최대 시간(실제 API 는 다시 불러오는 데 시간이 걸린다) */
const WATCH_MS = 1500;

function sel(name: string, value: string): string {
  return `[${name}="${typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(value) : value}"]`;
}

/** 지금 포커스가 있는 자리를 기억한다(누른 순간 부른다) */
export function rememberFocus(): FocusSpot | null {
  if (typeof document === 'undefined') return null;
  const el = document.activeElement;
  if (!(el instanceof HTMLElement) || el === document.body) return null;
  const cardEl = el.closest<HTMLElement>('[data-card]');
  const order = cardEl?.parentElement
    ? Array.from(cardEl.parentElement.children).flatMap((c) => {
        const id = c.getAttribute('data-card');
        return id ? [id] : [];
      })
    : [];
  return {
    el,
    card: cardEl?.getAttribute('data-card') ?? null,
    slot: el.closest('[data-slot]')?.getAttribute('data-slot') ?? null,
    order,
    region: el.closest('[data-focus-region]')?.getAttribute('data-focus-region') ?? null,
  };
}

function lost(): boolean {
  const cur = document.activeElement;
  return !cur || cur === document.body || !cur.isConnected;
}

const enabled = (b: HTMLElement) => !b.matches(':disabled');

/** 행의 대표 버튼 — 펼치기 버튼(aria-expanded), 없으면 첫 버튼 */
function cardButton(card: HTMLElement): HTMLElement | undefined {
  const all = getFocusable(card);
  return all.find((b) => b.hasAttribute('aria-expanded')) ?? all[0];
}

/** 목록을 담은 스크롤 영역에서 행이 보이게(고정 머리 data-sticky 아래로) — useDetailUi 의 행 스크롤과 같은 규칙 */
function revealCard(card: HTMLElement): void {
  let box = card.parentElement;
  while (box && box !== document.body) {
    const oy = getComputedStyle(box).overflowY;
    if (oy === 'auto' || oy === 'scroll') break;
    box = box.parentElement;
  }
  if (!box || box === document.body) return;
  const r = card.getBoundingClientRect();
  const c = box.getBoundingClientRect();
  const stk = box.querySelector('[data-sticky]');
  const top = c.top + (stk ? stk.getBoundingClientRect().height : 0) + 4;
  let d = 0;
  if (r.top < top) d = r.top - top;
  else if (r.bottom > c.bottom - 8) d = Math.min(r.top - top, r.bottom - c.bottom + 8);
  if (Math.abs(d) > 1) box.scrollBy({ top: d, behavior: scrollBehavior() });
}

/** 기억한 행이 목록에서 빠졌을 때 — 다음 남은 행 → 이전 행 → 지금 있는 첫 행 → 구역의 기준 자리 */
function fallback(spot: FocusSpot, root: ParentNode): { target: HTMLElement; card?: HTMLElement } | null {
  const i = spot.card ? spot.order.indexOf(spot.card) : -1;
  const ids = i < 0 ? [] : [...spot.order.slice(i + 1), ...spot.order.slice(0, i).reverse()];
  for (const id of ids) {
    const card = root.querySelector<HTMLElement>(sel('data-card', id));
    const target = card ? cardButton(card) : undefined;
    if (card && target) return { target, card };
  }
  const anyCard = root.querySelector<HTMLElement>('[data-card]');
  const anyTarget = anyCard ? cardButton(anyCard) : undefined;
  if (anyCard && anyTarget) return { target: anyTarget, card: anyCard };
  /* 남은 행이 없다 — 기준 자리를 우선순위(data-focus-home 값) 순서로: 고른 필터 칩 → 고른 결과 탭 */
  const homes = Array.from(root.querySelectorAll<HTMLElement>('[data-focus-home]')).sort(
    (a, b) => Number(a.getAttribute('data-focus-home')) - Number(b.getAttribute('data-focus-home')),
  );
  for (const home of homes) {
    const all = getFocusable(home);
    const target = all.find((b) => b.matches('[aria-pressed="true"], [aria-selected="true"]')) ?? all[0];
    if (target) return { target };
  }
  return null;
}

/** 포커스를 옮길 곳 — 아직 다시 그려지지 않아 찾지 못하면 null */
function findTarget(spot: FocusSpot): { target: HTMLElement; card?: HTMLElement } | null {
  if (spot.el.isConnected && enabled(spot.el)) return { target: spot.el };
  const region = spot.region ? document.querySelector<HTMLElement>(sel('data-focus-region', spot.region)) : null;
  const root: ParentNode = region ?? document;
  if (spot.card) {
    const card = root.querySelector<HTMLElement>(sel('data-card', spot.card));
    if (!card) return fallback(spot, root);
    const inSlot = spot.slot ? Array.from(card.querySelectorAll<HTMLElement>(sel('data-slot', spot.slot))).flatMap((s) => (s.matches('button, a[href]') ? [s] : getFocusable(s))) : [];
    const target = inSlot.find(enabled) ?? getFocusable(card)[0];
    return target ? { target } : null;
  }
  if (!spot.slot) return null;
  const inSlot = Array.from(document.querySelectorAll<HTMLElement>(sel('data-slot', spot.slot))).flatMap((s) => (s.matches('button, a[href]') ? [s] : getFocusable(s)));
  const target = inSlot.find(enabled);
  return target ? { target } : null;
}

/**
 * 포커스가 빠졌으면 기억한 자리로 되돌린다. 화면이 새 데이터로 다시 그려지고 모달의 포커스 복귀(다음 프레임)가
 * 끝난 뒤에 확인하려고 두 프레임 기다린다. 그 뒤로도 WATCH_MS 동안은 매 프레임 살핀다 —
 * 포커스가 아직 누른 버튼에 있으면(그 행이 곧 빠질 수 있음) 기다리고, 빠졌는데 옮길 곳이 아직 없으면(띠가 다시 그려지기 전)
 * 기다린다. 다른 곳에 포커스가 가 있거나 사용자가 화면을 누르면 그만둔다.
 */
export function rescueFocus(spot: FocusSpot | null): void {
  if (!spot || typeof window === 'undefined') return;
  const until = performance.now() + WATCH_MS;
  let frame = 0;
  let stopped = false;
  const stop = () => {
    stopped = true;
  };
  const end = () => window.removeEventListener('pointerdown', stop, true);
  window.addEventListener('pointerdown', stop, true);
  const tick = () => {
    if (stopped) return end();
    frame += 1;
    if (frame >= 2) {
      if (!lost()) {
        if (document.activeElement !== spot.el) return end();
      } else {
        const found = findTarget(spot);
        if (found) {
          found.target.focus({ preventScroll: true });
          if (found.card) revealCard(found.card);
          return end();
        }
      }
    }
    if (performance.now() < until) requestAnimationFrame(tick);
    else end();
  };
  requestAnimationFrame(tick);
}
