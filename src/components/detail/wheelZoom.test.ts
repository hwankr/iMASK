import { describe, expect, it } from 'vitest';
import { createWheelZoomMemo, isPinchWheel, wheelZoom, WHEEL_IDLE_MS, type WheelInput } from './wheelZoom';

/** Ctrl 휠 이벤트 — 기본은 화소 단위 세로 휠 */
const ev = (deltaY: number, at: number, more: Partial<WheelInput> = {}): WheelInput => ({ deltaX: 0, deltaY, deltaMode: 0, ctrlKey: true, timeStamp: at, ...more });

/** 같은 memo 로 이벤트를 차례로 보내고, 배율이 바뀔 때마다 그 배율로 이어 간다 */
function run(start: number, events: readonly WheelInput[], pinch = false): { zoom: number; changes: (number | null)[] } {
  const memo = createWheelZoomMemo();
  let zoom = start;
  const changes = events.map((e) => {
    const next = wheelZoom(zoom, e, pinch, memo);
    if (next !== null) zoom = next;
    return next;
  });
  return { zoom, changes };
}

describe('wheelZoom — 마우스 휠', () => {
  it('눈금 한 번에 한 단계: 위로 굴리면 확대, 아래로 굴리면 축소', () => {
    expect(run(1, [ev(-100, 0)]).changes).toEqual([1.1]);
    expect(run(1, [ev(100, 0)]).changes).toEqual([0.9]);
  });

  it('화면 배율로 눈금 값이 커져도(125 · 150 · 300) 한 단계', () => {
    expect(run(1, [ev(-125, 0), ev(-150, 16), ev(-300, 32)]).changes).toEqual([1.1, 1.2, 1.3]);
  });

  it('줄 · 쪽 단위 휠(Firefox)은 이벤트마다 한 단계', () => {
    expect(run(1, [ev(-3, 0, { deltaMode: 1 }), ev(1, 16, { deltaMode: 2 })]).changes).toEqual([1.1, 1]);
  });

  it('작은 화소 값은 모아서 눈금 하나(100)마다 한 단계', () => {
    expect(run(1, [ev(-25, 0), ev(-25, 16), ev(-25, 32), ev(-25, 48), ev(-40, 64)]).changes).toEqual([null, null, null, 1.1, null]);
  });

  it('잠깐 멈추면 모아 둔 값을 버린다', () => {
    // 0.3 + 0.3 을 모은 뒤 멈춤 → 버리고 다시 모은다(이어서 모았다면 세 번째 0.49 에서 1 을 넘었다)
    expect(run(1, [ev(-30, 0), ev(-30, 16), ev(-50 + 1, 16 + WHEEL_IDLE_MS + 1), ev(-30, 16 + WHEEL_IDLE_MS + 17)]).changes).toEqual([null, null, null, null]);
  });

  it('화면 맞춤 배율(0.1 단위 아님)에서는 버튼처럼 한 단계 옮긴 뒤 0.1 단위로 맞춘다', () => {
    expect(run(0.87, [ev(-100, 0)]).changes).toEqual([1]);
    expect(run(0.87, [ev(100, 0)]).changes).toEqual([0.8]);
  });

  it('끝(0.4 · 2배)에서는 더 바뀌지 않는다', () => {
    expect(run(2, [ev(-100, 0)]).changes).toEqual([null]);
    expect(run(0.4, [ev(100, 0)]).changes).toEqual([null]);
    expect(run(1.9, [ev(-100, 0), ev(-100, 16), ev(100, 32)]).changes).toEqual([2, null, 1.9]);
  });

  it('가로로만 굴린 휠은 그대로', () => {
    expect(run(1, [ev(0, 0, { deltaX: -100 })]).changes).toEqual([null]);
  });
});

describe('wheelZoom — 트랙패드 오므리기', () => {
  it('배율 × e^(−deltaY/100) 으로 이어서 바뀐다 — 두 배로 벌리면 1 → 2배', () => {
    const steps = Array.from({ length: 10 }, (_, i) => ev((-100 * Math.LN2) / 10, i * 16));
    const r = run(1, steps, true);
    expect(r.zoom).toBe(2);
    // 작은 값도 버리지 않고 모은다(0.1 단위를 넘을 때마다 바뀐다)
    expect(r.changes.filter((c) => c !== null).length).toBeGreaterThanOrEqual(5);
  });

  it('오므리면 축소, 끝을 넘겨 오므렸다가 되돌리면 곧바로 커진다', () => {
    const memo = createWheelZoomMemo();
    let zoom = 0.5;
    for (let i = 0; i < 10; i++) zoom = wheelZoom(zoom, ev(20, i * 16), true, memo) ?? zoom;
    expect(zoom).toBe(0.4);
    // 0.4 에 붙어 있다 — 반대로 조금만 벌려도(0.4 × e^0.15 ≈ 0.46) 0.5
    expect(wheelZoom(zoom, ev(-15, 200), true, memo)).toBe(0.5);
  });

  it('들고 있던 배율이 지금 배율과 다르면(버튼으로 바뀜) 지금 배율에서 다시 시작한다', () => {
    const memo = createWheelZoomMemo();
    expect(wheelZoom(1, ev(-4, 0), true, memo)).toBe(null); // 1.04 — 아직 1
    // 버튼으로 0.6 이 됐다 — 들고 있던 1.04 에서 이어 가면 1.1 이 되지만, 0.6 × 1.04 ≈ 0.62 라 아직 0.6
    expect(wheelZoom(0.6, ev(-4, 16), true, memo)).toBe(null);
    expect(memo.pinch).toBeCloseTo(0.6 * Math.exp(0.04), 6);
  });
});

describe('isPinchWheel', () => {
  it('ctrlKey 인데 실제 Ctrl 키가 떼어진 작은 화소 휠만 오므리기', () => {
    expect(isPinchWheel(ev(-3, 0), false)).toBe(true);
    expect(isPinchWheel(ev(-3, 0), true)).toBe(false);
    expect(isPinchWheel(ev(-100, 0), false)).toBe(false);
    expect(isPinchWheel(ev(-3, 0, { deltaMode: 1 }), false)).toBe(false);
    expect(isPinchWheel(ev(-3, 0, { deltaX: 2 }), false)).toBe(false);
    expect(isPinchWheel(ev(-3, 0, { ctrlKey: false }), false)).toBe(false);
  });
});
