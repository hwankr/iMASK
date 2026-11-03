import { describe, expect, it } from 'vitest';
import { MAX_CANVAS_AREA, MAX_CANVAS_SIDE, MIN_BOX_PX, TOUCH_MIN_PX, boxRect, canvasScale, hitAreas, unitBoxOnPage, type HitBox, type PxRect, type UnitPoint } from './pageBox';

/** 0~1 사각형 꼭짓점 4개(시계 방향) */
const quad = (x0: number, y0: number, x1: number, y1: number): UnitPoint[] => [
  { x: x0, y: y0 },
  { x: x1, y: y0 },
  { x: x1, y: y1 },
  { x: x0, y: y1 },
];

/** 소수 오차를 줄여 비교 */
const round = (r: { x: number; y: number; w: number; h: number } | null) =>
  r && { x: +r.x.toFixed(4), y: +r.y.toFixed(4), w: +r.w.toFixed(4), h: +r.h.toFixed(4) };

const A4 = { width: 760, height: 760 * Math.SQRT2 };

describe('boxRect — 0~1 비율 꼭짓점 → 쪽 위 사각형(px)', () => {
  it('꼭짓점들을 감싼 사각형 — 쪽 폭 · 높이를 곱한다', () => {
    expect(round(boxRect(quad(0.1, 0.3, 0.2, 0.32), { width: 1000, height: 2000 }))).toEqual({ x: 100, y: 600, w: 100, h: 40 });
  });

  it('기울어진 사각형(회전한 꼭짓점)도 최소 · 최대로 감싼다 — 꼭짓점 순서와 무관', () => {
    const rotated: UnitPoint[] = [
      { x: 0.5, y: 0.1 },
      { x: 0.6, y: 0.15 },
      { x: 0.55, y: 0.25 },
      { x: 0.45, y: 0.2 },
    ];
    expect(round(boxRect(rotated, { width: 1000, height: 1000 }))).toEqual({ x: 450, y: 100, w: 150, h: 150 });
    expect(round(boxRect([...rotated].reverse(), { width: 1000, height: 1000 }))).toEqual({ x: 450, y: 100, w: 150, h: 150 });
  });

  it('꼭짓점 2개(대각선)만 있어도 된다', () => {
    expect(round(boxRect([{ x: 0.2, y: 0.4 }, { x: 0.1, y: 0.3 }], { width: 100, height: 100 }))).toEqual({ x: 10, y: 30, w: 10, h: 10 });
  });

  it('2× 배율 — 쪽 크기를 두 배로 넘기면 모든 값이 두 배', () => {
    const pts = quad(0.237, 0.225, 0.286, 0.238); // 고정 자료 D1-01(성명)
    const one = boxRect(pts, A4)!;
    const two = boxRect(pts, { width: A4.width * 2, height: A4.height * 2 })!;
    expect(two.x).toBeCloseTo(one.x * 2, 6);
    expect(two.y).toBeCloseTo(one.y * 2, 6);
    expect(two.w).toBeCloseTo(one.w * 2, 6);
    expect(two.h).toBeCloseTo(one.h * 2, 6);
    expect(one.x).toBeCloseTo(0.237 * 760, 6);
    expect(one.w).toBeCloseTo((0.286 - 0.237) * 760, 6);
  });

  it('세로로 긴 쪽 · 가로로 긴 쪽 — 가로는 폭, 세로는 높이 비율', () => {
    const pts = quad(0.25, 0.5, 0.75, 0.6);
    expect(round(boxRect(pts, { width: 400, height: 1600 }))).toEqual({ x: 100, y: 800, w: 200, h: 160 });
    expect(round(boxRect(pts, { width: 1600, height: 400 }))).toEqual({ x: 400, y: 200, w: 800, h: 40 });
  });

  it('0~1 밖은 자른다', () => {
    expect(round(boxRect(quad(-0.1, 0.9, 0.2, 1.2), { width: 1000, height: 1000 }))).toEqual({ x: 0, y: 900, w: 200, h: 100 });
    expect(round(boxRect(quad(0.8, -0.5, 1.5, 0.1), { width: 1000, height: 1000 }))).toEqual({ x: 800, y: 0, w: 200, h: 100 });
  });

  it('쪽과 전혀 겹치지 않으면 null', () => {
    expect(boxRect(quad(1.1, 0.1, 1.3, 0.2), A4)).toBeNull();
    expect(boxRect(quad(0.1, -0.4, 0.2, -0.1), A4)).toBeNull();
  });

  it('너무 작으면 가운데를 지키며 최소 크기로 늘린다', () => {
    // 납작한 상자(높이 0) — 가운데 y=500 을 지키며 높이 4
    expect(round(boxRect(quad(0.1, 0.5, 0.2, 0.5), { width: 1000, height: 1000 }))).toEqual({ x: 100, y: 498, w: 100, h: MIN_BOX_PX });
    // 점(폭 · 높이 0) — 최소 크기를 직접 정할 수 있다
    expect(round(boxRect([{ x: 0.5, y: 0.5 }, { x: 0.5, y: 0.5 }], { width: 1000, height: 1000 }, 10))).toEqual({ x: 495, y: 495, w: 10, h: 10 });
  });

  it('최소 크기로 늘리다 쪽 밖으로 나가면 안쪽으로 민다 · 쪽이 더 작으면 쪽 크기', () => {
    expect(round(boxRect([{ x: 0, y: 0 }, { x: 0, y: 0 }], { width: 1000, height: 1000 }, 10))).toEqual({ x: 0, y: 0, w: 10, h: 10 });
    expect(round(boxRect([{ x: 1, y: 1 }, { x: 1, y: 1 }], { width: 1000, height: 1000 }, 10))).toEqual({ x: 990, y: 990, w: 10, h: 10 });
    expect(round(boxRect([{ x: 0.5, y: 0.5 }, { x: 0.5, y: 0.5 }], { width: 6, height: 3 }, 10))).toEqual({ x: 0, y: 0, w: 6, h: 3 });
  });

  it('최소 크기 0 · 음수 · NaN 이면 늘리지 않는다', () => {
    for (const min of [0, -5, NaN])
      expect(round(boxRect(quad(0.1, 0.5, 0.2, 0.5), { width: 1000, height: 1000 }, min))).toEqual({ x: 100, y: 500, w: 100, h: 0 });
  });

  it('잘못된 값은 버린다(null) — 꼭짓점 2개 미만 · 숫자 아님 · 유한하지 않음 · 배열 아님 · 쪽 크기 0 이하', () => {
    const size = { width: 100, height: 100 };
    expect(boxRect([], size)).toBeNull();
    expect(boxRect([{ x: 0.1, y: 0.1 }], size)).toBeNull();
    expect(boxRect(null, size)).toBeNull();
    expect(boxRect(undefined, size)).toBeNull();
    expect(boxRect('0,0' as unknown as UnitPoint[], size)).toBeNull();
    expect(boxRect([{ x: 0.1, y: 0.1 }, { x: NaN, y: 0.2 }], size)).toBeNull();
    expect(boxRect([{ x: 0.1, y: 0.1 }, { x: 0.2, y: Infinity }], size)).toBeNull();
    expect(boxRect([{ x: 0.1, y: 0.1 }, { x: '0.2', y: 0.2 } as unknown as UnitPoint], size)).toBeNull();
    expect(boxRect([{ x: 0.1, y: 0.1 }, null as unknown as UnitPoint], size)).toBeNull();
    expect(boxRect(quad(0.1, 0.1, 0.2, 0.2), { width: 0, height: 100 })).toBeNull();
    expect(boxRect(quad(0.1, 0.1, 0.2, 0.2), { width: 100, height: -1 })).toBeNull();
    expect(boxRect(quad(0.1, 0.1, 0.2, 0.2), { width: NaN, height: 100 })).toBeNull();
  });
});

describe('canvasScale — 선명하게 그리되 캔버스 크기 상한', () => {
  const A4PT = { w: 595, h: 842 };

  it('상한 안이면 원하는 배율 그대로(화면 폭/쪽 폭 × 확대 × 기기 픽셀 배율)', () => {
    const want = (760 / A4PT.w) * 1 * 2;
    expect(canvasScale(A4PT.w, A4PT.h, want)).toBeCloseTo(want, 10);
  });

  it('넓이 상한 — 캔버스 픽셀 수가 MAX_CANVAS_AREA 를 넘지 않는다', () => {
    const s = canvasScale(A4PT.w, A4PT.h, 10);
    expect(s).toBeLessThan(10);
    expect(A4PT.w * s * (A4PT.h * s)).toBeLessThanOrEqual(MAX_CANVAS_AREA + 1);
  });

  it('한 변 상한 — 아주 긴 쪽은 긴 변이 MAX_CANVAS_SIDE 를 넘지 않는다', () => {
    const s = canvasScale(100, 20000, 2);
    expect(20000 * s).toBeLessThanOrEqual(MAX_CANVAS_SIDE + 1e-6);
  });

  it('잘못된 쪽 크기면 1, 잘못된 원하는 배율이면 1 로 본다', () => {
    expect(canvasScale(0, 842, 2)).toBe(1);
    expect(canvasScale(NaN, 842, 2)).toBe(1);
    expect(canvasScale(595, 842, NaN)).toBe(1);
    expect(canvasScale(595, 842, -3)).toBe(1);
  });
});

describe('unitBoxOnPage — 쪽에 그릴 수 있는 상자(매핑 · 화면 변환이 같이 쓰는 기준)', () => {
  it('쪽 안 · 일부만 걸친 상자 · 선(넓이 0)은 그릴 수 있다', () => {
    expect(unitBoxOnPage(quad(0.1, 0.1, 0.2, 0.2))).toBe(true);
    expect(unitBoxOnPage(quad(-0.05, 0.9, 1.2, 1.01))).toBe(true);
    expect(unitBoxOnPage(quad(0.1, 0.5, 0.2, 0.5))).toBe(true);
    expect(unitBoxOnPage(quad(0.9, 0.9, 1, 1))).toBe(true); // 모서리에 닿음
  });

  it('쪽과 전혀 겹치지 않거나 잘못된 꼭짓점이면 그릴 수 없다 — boxRect 도 null', () => {
    const off = [quad(2, 2, 3, 3), quad(-0.4, 0.1, -0.1, 0.2), quad(0.1, 1.01, 0.2, 1.5)];
    for (const pts of off) {
      expect(unitBoxOnPage(pts)).toBe(false);
      expect(boxRect(pts, A4)).toBeNull();
    }
    expect(unitBoxOnPage([{ x: 0.1, y: 0.1 }])).toBe(false);
    expect(unitBoxOnPage([{ x: 0.1, y: 0.1 }, { x: NaN, y: 0.2 }])).toBe(false);
    expect(unitBoxOnPage(null)).toBe(false);
  });
});

describe('hitAreas — 휴대폰 누름 영역(보이는 상자는 그대로, 누르는 영역만 넓힘)', () => {
  const PAGE = { width: 760, height: 1075 };
  const box = (key: string, group: string, x: number, y: number, w: number, h: number): HitBox => ({ key, group, rect: { x, y, w, h } });
  const contains = (o: PxRect, i: PxRect) => o.x <= i.x + 1e-9 && o.y <= i.y + 1e-9 && o.x + o.w >= i.x + i.w - 1e-9 && o.y + o.h >= i.y + i.h - 1e-9;
  const overlapArea = (a: PxRect, b: PxRect) =>
    Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) * Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));

  it('혼자 있는 상자 — 화면 44px 이상(배율 1), 가운데 유지, 보이는 상자를 품는다', () => {
    const r = box('a', 'F1', 300, 400, 20, 8);
    const e = hitAreas([r], { zoom: 1, page: PAGE }).get('a')!;
    expect(e.w).toBeCloseTo(TOUCH_MIN_PX, 9);
    expect(e.h).toBeCloseTo(TOUCH_MIN_PX, 9);
    expect(e.x + e.w / 2).toBeCloseTo(310, 9);
    expect(e.y + e.h / 2).toBeCloseTo(404, 9);
    expect(contains(e, r.rect)).toBe(true);
  });

  it('배율 보정 — 쪽 px 로 44 ÷ 배율(0.47 → 약 93.6, 2 → 22), 이미 큰 상자는 그대로', () => {
    const r = box('a', 'F1', 300, 400, 20, 8);
    const small = hitAreas([r], { zoom: 0.47, page: PAGE }).get('a')!;
    expect(small.w * 0.47).toBeCloseTo(44, 6);
    expect(small.h * 0.47).toBeCloseTo(44, 6);
    const big = hitAreas([r], { zoom: 2, page: PAGE }).get('a')!;
    expect(big.w).toBeCloseTo(22, 9);
    expect(big.h).toBeCloseTo(22, 9);
    const wide = box('w', 'F1', 100, 100, 200, 60);
    expect(hitAreas([wide], { zoom: 1, page: PAGE }).get('w')).toEqual(wide.rect);
  });

  it('쪽 가장자리 — 쪽 안으로 밀되 보이는 상자는 품는다', () => {
    const r = box('a', 'F1', 0, 0, 10, 4);
    const e = hitAreas([r], { zoom: 1, page: PAGE }).get('a')!;
    expect(e.x).toBe(0);
    expect(e.y).toBe(0);
    expect(e.w).toBeCloseTo(44, 9);
    expect(contains(e, r.rect)).toBe(true);
  });

  it('서로 다른 항목이 가로로 가까우면 두 상자 사이 가운데에서 나눈다 — 겹침 0, 다른 항목 상자를 덮지 않음', () => {
    const a = box('a', 'F1', 100, 400, 30, 10);
    const b = box('b', 'F2', 140, 400, 30, 10); // 틈 10px → 가운데 135
    const m = hitAreas([a, b], { zoom: 0.5, page: PAGE });
    const ea = m.get('a')!;
    const eb = m.get('b')!;
    expect(ea.x + ea.w).toBeCloseTo(135, 9);
    expect(eb.x).toBeCloseTo(135, 9);
    expect(overlapArea(ea, eb)).toBe(0);
    expect(overlapArea(ea, b.rect)).toBe(0);
    expect(overlapArea(eb, a.rect)).toBe(0);
    // 나누지 않는 방향(세로 · 바깥쪽)은 44 ÷ 0.5 = 88 까지 넓힌다
    expect(ea.h).toBeCloseTo(88, 9);
    expect(ea.x).toBeCloseTo(115 - 44, 9);
  });

  it('서로 다른 항목이 세로로 가까우면 위아래 가운데에서 나눈다', () => {
    const a = box('a', 'F1', 100, 400, 60, 12);
    const b = box('b', 'F2', 110, 420, 60, 12); // 세로 틈 8 → 가운데 416
    const m = hitAreas([a, b], { zoom: 0.47, page: PAGE });
    expect(m.get('a')!.y + m.get('a')!.h).toBeCloseTo(416, 9);
    expect(m.get('b')!.y).toBeCloseTo(416, 9);
    expect(overlapArea(m.get('a')!, m.get('b')!)).toBe(0);
  });

  it('같은 항목의 상자끼리는 나누지 않는다(겹쳐도 됨) — 둘 다 44px', () => {
    const a = box('a1', 'F1', 100, 400, 30, 10);
    const b = box('a2', 'F1', 135, 400, 30, 10);
    const m = hitAreas([a, b], { zoom: 1, page: PAGE });
    expect(m.get('a1')!.w).toBeCloseTo(44, 9);
    expect(m.get('a2')!.w).toBeCloseTo(44, 9);
    expect(overlapArea(m.get('a1')!, m.get('a2')!)).toBeGreaterThan(0);
  });

  it('원래 사각형끼리 겹치는 서로 다른 항목은 둘 다 넓히지 않는다', () => {
    const a = box('a', 'F1', 100, 400, 30, 10);
    const b = box('b', 'F2', 120, 405, 30, 10);
    const m = hitAreas([a, b], { zoom: 0.5, page: PAGE });
    expect(m.get('a')).toEqual(a.rect);
    expect(m.get('b')).toEqual(b.rect);
  });

  it('고정 자료 대출신청서 1쪽(배율 0.47) — 서로 다른 항목의 누름 영역 겹침 0 · 늘 보이는 상자를 품음 · 순서와 무관', () => {
    const W = 760;
    const H = 760 * (841.92 / 594.96);
    const unit: [string, string, number, number, number, number][] = [
      ['D1-01#1', 'D1-01', 0.237, 0.225, 0.286, 0.238],
      ['D1-02#1', 'D1-02', 0.596, 0.226, 0.73, 0.238],
      ['D1-03#1', 'D1-03', 0.236, 0.254, 0.357, 0.266],
      ['D1-04#1', 'D1-04', 0.596, 0.254, 0.808, 0.269],
      ['D1-05#1', 'D1-05', 0.237, 0.282, 0.317, 0.295],
      ['D1-05#2', 'D1-05', 0.323, 0.282, 0.371, 0.295],
      ['D1-05#3', 'D1-05', 0.376, 0.282, 0.457, 0.295],
      ['D1-06#1', 'D1-06', 0.236, 0.31, 0.329, 0.324],
      ['D1-08#1', 'D1-08', 0.596, 0.339, 0.7, 0.353],
    ];
    const boxes = unit.map(([k, g, x0, y0, x1, y1]) => box(k, g, x0 * W, y0 * H, (x1 - x0) * W, (y1 - y0) * H));
    const m = hitAreas(boxes, { zoom: 0.47, page: { width: W, height: H } });
    for (const b of boxes) expect(contains(m.get(b.key)!, b.rect)).toBe(true);
    for (const a of boxes)
      for (const b of boxes) {
        if (a.group === b.group) continue;
        expect(overlapArea(m.get(a.key)!, m.get(b.key)!)).toBe(0);
        expect(overlapArea(m.get(a.key)!, b.rect)).toBe(0);
      }
    const reversed = hitAreas([...boxes].reverse(), { zoom: 0.47, page: { width: W, height: H } });
    for (const b of boxes) expect(reversed.get(b.key)).toEqual(m.get(b.key));
  });
});
