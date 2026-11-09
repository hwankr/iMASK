/* ==========================================================================
   원문 쪽 끝에서 더 굴리면 다음 · 이전 쪽 — 쪽 끝(아래 · 위)에 닿은 뒤 같은 방향으로 PAGE_FLIP_PX 넘게 더 굴리면 넘긴다.
   - 마우스 휠 눈금 하나가 100px 안팎이라 끝에 닿은 뒤 두 눈금쯤이다(끝까지 내린 마지막 눈금은 세지 않는다 —
     이벤트가 올 때 아직 끝이 아니었으므로).
   - 끝이 아니거나 넘길 쪽이 없거나, 방향이 바뀌거나, 잠깐(PAGE_FLIP_IDLE_MS) 멈추면 모은 값을 버린다.
   - 넘긴 직후(PAGE_FLIP_LOCK_MS) 같은 방향으로 이어 오는 휠(관성)은 삼켜서 새 쪽이 곧바로 밀려 내려가지 않게 한다.
   - 가로 휠(Shift · 가로가 더 큰 값)은 보지 않는다. Ctrl 휠은 확대 · 축소라 부르는 쪽(DocViewer.tsx)이 따로 처리한다.
   순수 함수(React · DOM 없음) — 시험은 pageFlip.test.ts.
   ========================================================================== */

/** 끝에 닿은 뒤 이만큼(px) 더 굴리면 넘긴다 */
export const PAGE_FLIP_PX = 200;
/** 이만큼(ms) 멈추면 모은 값을 버린다 */
export const PAGE_FLIP_IDLE_MS = 400;
/** 넘긴 뒤 이만큼(ms) 같은 방향 휠을 삼킨다 */
export const PAGE_FLIP_LOCK_MS = 500;
/** 줄 단위 휠(Firefox) 한 줄(px) */
const LINE_PX = 40;
/** 끝으로 보는 여유(px) — 배율 때문에 스크롤 위치가 소수일 수 있다 */
const END_SLACK = 2;

export interface PageFlipInput {
  deltaX: number;
  deltaY: number;
  /** 0 화소 · 1 줄 · 2 쪽 */
  deltaMode: number;
  shiftKey: boolean;
  /** 이벤트 시각(ms) */
  timeStamp: number;
  /** 스크롤 영역 — scrollTop · scrollHeight · clientHeight */
  top: number;
  height: number;
  client: number;
  canPrev: boolean;
  canNext: boolean;
}

export interface PageFlipMemo {
  /** 끝에서 모은 휠 양(px) */
  acc: number;
  /** 모으는 방향(1 아래 · -1 위 · 0 없음) */
  dir: number;
  at: number;
  /** 넘긴 방향과 삼키기가 끝나는 시각 */
  lockDir: number;
  lockUntil: number;
}

export function createPageFlipMemo(): PageFlipMemo {
  return { acc: 0, dir: 0, at: Number.NEGATIVE_INFINITY, lockDir: 0, lockUntil: Number.NEGATIVE_INFINITY };
}

/**
 * 휠 이벤트 하나 → 'next' · 'prev'(넘긴다), 'swallow'(넘긴 직후 같은 방향 — 스크롤하지 않게 막는다), null(그대로).
 * memo 를 고친다.
 */
export function wheelPageFlip(e: PageFlipInput, memo: PageFlipMemo): 'next' | 'prev' | 'swallow' | null {
  if (e.shiftKey || e.deltaY === 0 || Math.abs(e.deltaX) > Math.abs(e.deltaY)) return null;
  const dir = e.deltaY > 0 ? 1 : -1;
  if (dir === memo.lockDir && e.timeStamp < memo.lockUntil) return 'swallow';

  const atEnd = dir > 0 ? e.top + e.client >= e.height - END_SLACK : e.top <= END_SLACK;
  const can = dir > 0 ? e.canNext : e.canPrev;
  if (!atEnd || !can) {
    memo.acc = 0;
    memo.dir = 0;
    return null;
  }
  if (memo.dir !== dir || e.timeStamp - memo.at > PAGE_FLIP_IDLE_MS) memo.acc = 0;
  memo.dir = dir;
  memo.at = e.timeStamp;
  const px = e.deltaMode === 1 ? LINE_PX : e.deltaMode === 2 ? Math.max(e.client, PAGE_FLIP_PX) : 1;
  memo.acc += Math.abs(e.deltaY) * px;
  if (memo.acc < PAGE_FLIP_PX) return null;

  memo.acc = 0;
  memo.dir = 0;
  memo.lockDir = dir;
  memo.lockUntil = e.timeStamp + PAGE_FLIP_LOCK_MS;
  return dir > 0 ? 'next' : 'prev';
}
