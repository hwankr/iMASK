/* ==========================================================================
   쪽 위 위치 상자 · 캔버스 배율 — 순수 함수(실제 분석 원문 뷰어). 테스트 대상.
   - 계약의 상자는 쪽 크기에 대한 0~1 비율 꼭짓점(보통 4개, 기울어진 사각형일 수 있다)이다.
     화면은 꼭짓점들을 감싼 축 정렬 사각형을 쪽 크기(px)로 바꿔 그린다.
   - 캔버스는 선명하게 그리려고 기기 픽셀 배율을 곱하되, 너무 큰 캔버스(메모리 · 브라우저 한도)를 만들지 않게 상한을 둔다.
   - '쪽에 닿는 상자'(unitBoxOnPage)는 매핑(서비스 contract.ts — 위치 ID)과 화면 변환(boxRect)이 같이 쓰는 한 기준이다.
     쪽과 전혀 겹치지 않는 상자는 위치 ID 에서도 빠지므로 이름표 · 스크롤 · '위치 확인 필요' 판단이 그린 상자와 같다.
   - 휴대폰 누름 영역(hitAreas): 보이는 상자는 그대로 두고, 누르는 영역만 화면에서 44px(배율 보정)까지 넓히되
     서로 다른 항목끼리는 두 원래 사각형 사이 가운데에서 잘라 겹치지 않게 나눈다.
   ========================================================================== */

/** 0~1 비율 꼭짓점 */
export interface UnitPoint {
  x: number;
  y: number;
}

/** 쪽 위 사각형(px) — 왼쪽 위 기준 */
export interface PxRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** 상자의 최소 크기(px, 배율 1 기준 쪽 폭에서) — 점 · 선처럼 납작한 상자도 보이고 누를 수 있게 */
export const MIN_BOX_PX = 4;

const clamp01 = (v: number): number => (v < 0 ? 0 : v > 1 ? 1 : v);

/** 꼭짓점들이 모두 유한한 수이고 2개 이상인지 */
function validPoints(points: readonly UnitPoint[] | null | undefined): points is readonly UnitPoint[] {
  if (!Array.isArray(points) || points.length < 2) return false;
  return points.every((p) => !!p && typeof p.x === 'number' && typeof p.y === 'number' && Number.isFinite(p.x) && Number.isFinite(p.y));
}

/**
 * 0~1 비율 꼭짓점이 쪽(0~1 정사각형)과 겹치는지 — 쪽에 그릴 수 있는 상자인지(꼭짓점 2개 이상 · 유한한 수 포함).
 * 선 · 점처럼 넓이가 0 이어도 쪽 안에 있으면 그린다(최소 크기로 늘림).
 */
export function unitBoxOnPage(points: readonly UnitPoint[] | null | undefined): boolean {
  if (!validPoints(points)) return false;
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (const p of points) {
    if (p.x < x0) x0 = p.x;
    if (p.x > x1) x1 = p.x;
    if (p.y < y0) y0 = p.y;
    if (p.y > y1) y1 = p.y;
  }
  return !(x1 < 0 || y1 < 0 || x0 > 1 || y0 > 1);
}

/** 최소 크기를 맞춘다 — 가운데를 지키며 늘리고, 쪽 밖으로 나가면 안쪽으로 민다(쪽이 더 작으면 쪽 크기) */
function grow(start: number, len: number, min: number, total: number): [number, number] {
  if (len >= min) return [start, len];
  const want = Math.min(min, total);
  let s = start + len / 2 - want / 2;
  if (s < 0) s = 0;
  if (s + want > total) s = total - want;
  return [s, want];
}

/**
 * 0~1 비율 꼭짓점 → 쪽 위 사각형(px).
 * - 꼭짓점들의 최소 · 최대로 감싼 사각형(기울어진 사각형도 감싼다)
 * - 0~1 로 자른다. 쪽과 전혀 겹치지 않으면 null
 * - 폭 · 높이가 minPx 보다 작으면 가운데를 지키며 minPx 로 늘린다(쪽 안으로)
 * - 꼭짓점이 2개 미만이거나, 숫자가 아니거나 유한하지 않은 값이 있거나, 쪽 크기가 0 이하면 null
 * size 는 그리는 쪽의 px 크기다(배율을 곱한 크기를 넘기면 그 배율의 px).
 */
export function boxRect(points: readonly UnitPoint[] | null | undefined, size: { width: number; height: number }, minPx: number = MIN_BOX_PX): PxRect | null {
  const { width: W, height: H } = size;
  if (!(Number.isFinite(W) && Number.isFinite(H) && W > 0 && H > 0)) return null;
  // 잘못된 꼭짓점 · 쪽과 겹치지 않는 상자(모두 쪽 밖)는 버린다 — 매핑과 같은 기준(unitBoxOnPage)
  if (!points || !unitBoxOnPage(points)) return null;
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (const p of points) {
    if (p.x < x0) x0 = p.x;
    if (p.x > x1) x1 = p.x;
    if (p.y < y0) y0 = p.y;
    if (p.y > y1) y1 = p.y;
  }
  const cx0 = clamp01(x0);
  const cy0 = clamp01(y0);
  const cx1 = clamp01(x1);
  const cy1 = clamp01(y1);
  const min = Number.isFinite(minPx) && minPx > 0 ? minPx : 0;
  const [x, w] = grow(cx0 * W, (cx1 - cx0) * W, min, W);
  const [y, h] = grow(cy0 * H, (cy1 - cy0) * H, min, H);
  return { x, y, w, h };
}

/** 캔버스 한 장의 최대 픽셀 수(2^23 ≈ 838만 — RGBA 약 32MB). 휴대폰 브라우저의 캔버스 한도보다 넉넉히 작다 */
export const MAX_CANVAS_AREA = 8_388_608;
/** 캔버스 한 변의 최대 픽셀 */
export const MAX_CANVAS_SIDE = 8192;

/**
 * 쪽(PDF 단위 pageW × pageH)을 그릴 배율. 원하는 배율(want = 화면 폭/쪽 폭 × 확대 배율 × 기기 픽셀 배율)을 쓰되
 * 캔버스가 maxArea 픽셀 · 한 변 maxSide 픽셀을 넘지 않게 줄인다. 잘못된 값이면 1.
 */
export function canvasScale(pageW: number, pageH: number, want: number, maxArea: number = MAX_CANVAS_AREA, maxSide: number = MAX_CANVAS_SIDE): number {
  if (!(pageW > 0 && pageH > 0 && Number.isFinite(pageW) && Number.isFinite(pageH))) return 1;
  const w = Number.isFinite(want) && want > 0 ? want : 1;
  const byArea = Math.sqrt(maxArea / (pageW * pageH));
  const bySide = maxSide / Math.max(pageW, pageH);
  return Math.min(w, byArea, bySide);
}

/* ---------- 휴대폰 누름 영역 ---------- */

/** 누름 영역을 계산할 상자 하나 — rect 는 쪽 위 보이는 사각형(px, 배율 1 기준 쪽 좌표) */
export interface HitBox {
  /** 상자 열쇠(위치 ID) */
  key: string;
  /** 같은 항목이면 같은 값(탐지 항목 번호) — 같은 항목 상자끼리는 겹쳐도 된다 */
  group: string;
  rect: PxRect;
}

/** 휴대폰 누름 영역 최소 크기(화면 px) — tokens.css --touch-min 과 같은 값 */
export const TOUCH_MIN_PX = 44;

const right = (r: PxRect) => r.x + r.w;
const bottom = (r: PxRect) => r.y + r.h;
const intersects = (a: PxRect, b: PxRect) => a.x < right(b) && b.x < right(a) && a.y < bottom(b) && b.y < bottom(a);

/**
 * 보이는 상자는 그대로 두고 누르는 영역만 넓힌다(쪽 좌표 px). 결과는 열쇠 → 누름 사각형(늘 보이는 사각형을 품는다).
 * 1) 각 상자를 가운데를 지키며 화면 minScreenPx(배율 보정 = minScreenPx ÷ zoom 쪽 px)까지 늘리고 쪽 안으로 자른다.
 * 2) 서로 다른 항목의 두 상자가 늘린 영역끼리 겹치면, 두 원래 사각형이 떨어진 축(둘 다면 더 많이 떨어진 축)의
 *    가운데 선에서 자른다 — 각자 자기 쪽만 남으므로 서로 겹치지 않고, 다른 항목의 원래 사각형도 덮지 않는다.
 *    원래 사각형끼리 이미 겹치면(나눌 선이 없음) 둘 다 늘리지 않는다.
 * 자르기는 늘 줄이기만 하고 원래 사각형 사이 가운데 선만 쓰므로 순서와 무관하게 같은 결과다.
 * 빽빽한 곳에서는 minScreenPx 보다 작을 수 있다(겹치지 않게 나눈 결과). 같은 항목 상자끼리는 겹쳐도 된다.
 */
export function hitAreas(
  boxes: readonly HitBox[],
  opts: { zoom: number; page: { width: number; height: number }; minScreenPx?: number },
): Map<string, PxRect> {
  const out = new Map<string, PxRect>();
  const zoom = Number.isFinite(opts.zoom) && opts.zoom > 0 ? opts.zoom : 1;
  const minPage = (opts.minScreenPx ?? TOUCH_MIN_PX) / zoom;
  const W = opts.page.width;
  const H = opts.page.height;
  const pageOk = Number.isFinite(W) && Number.isFinite(H) && W > 0 && H > 0;

  // 1) 원하는 크기로 늘림
  const want = boxes.map((b) => {
    const r = b.rect;
    const [x, w] = pageOk ? grow(r.x, r.w, minPage, W) : [r.x, Math.max(r.w, minPage)];
    const [y, h] = pageOk ? grow(r.y, r.h, minPage, H) : [r.y, Math.max(r.h, minPage)];
    // 쪽 안으로 밀다가 원래 사각형을 놓치지 않게 원래 사각형을 품도록 맞춘다
    const nx = Math.min(x, r.x);
    const ny = Math.min(y, r.y);
    return { x: nx, y: ny, w: Math.max(x + w, right(r)) - nx, h: Math.max(y + h, bottom(r)) - ny };
  });
  // 경계(왼 · 위 · 오른 · 아래) — 자르기는 이 값을 줄이기만 한다
  const lim = want.map((e) => ({ l: e.x, t: e.y, r: right(e), b: bottom(e) }));

  // 2) 서로 다른 항목끼리 나눔
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      if (boxes[i].group === boxes[j].group) continue;
      if (!intersects(want[i], want[j])) continue;
      const a = boxes[i].rect;
      const b = boxes[j].rect;
      const gapX = Math.max(b.x - right(a), a.x - right(b));
      const gapY = Math.max(b.y - bottom(a), a.y - bottom(b));
      if (gapX < 0 && gapY < 0) {
        // 원래 사각형이 겹친다 — 둘 다 늘리지 않는다
        lim[i] = { l: a.x, t: a.y, r: right(a), b: bottom(a) };
        lim[j] = { l: b.x, t: b.y, r: right(b), b: bottom(b) };
        continue;
      }
      if (gapX >= gapY) {
        const [L, R, li, ri] = right(a) <= b.x ? [a, b, i, j] : [b, a, j, i];
        const mid = (right(L) + R.x) / 2;
        lim[li].r = Math.min(lim[li].r, mid);
        lim[ri].l = Math.max(lim[ri].l, mid);
      } else {
        const [T, B, ti, bi] = bottom(a) <= b.y ? [a, b, i, j] : [b, a, j, i];
        const mid = (bottom(T) + B.y) / 2;
        lim[ti].b = Math.min(lim[ti].b, mid);
        lim[bi].t = Math.max(lim[bi].t, mid);
      }
    }
  }

  boxes.forEach((b, k) => {
    const r = b.rect;
    // 원래 사각형은 늘 품는다(누르는 영역이 보이는 상자보다 작아지지 않게)
    const l = Math.min(lim[k].l, r.x);
    const t = Math.min(lim[k].t, r.y);
    const rr = Math.max(lim[k].r, right(r));
    const bb = Math.max(lim[k].b, bottom(r));
    out.set(b.key, { x: l, y: t, w: rr - l, h: bb - t });
  });
  return out;
}
