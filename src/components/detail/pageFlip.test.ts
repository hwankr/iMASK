import { describe, expect, it } from 'vitest';
import { createPageFlipMemo, PAGE_FLIP_IDLE_MS, PAGE_FLIP_LOCK_MS, wheelPageFlip, type PageFlipInput } from './pageFlip';

/** 스크롤 영역: 내용 1000 · 화면 400 → 맨 아래 top = 600 */
const BOTTOM = 600;
const ev = (deltaY: number, at: number, more: Partial<PageFlipInput> = {}): PageFlipInput => ({
  deltaX: 0,
  deltaY,
  deltaMode: 0,
  shiftKey: false,
  timeStamp: at,
  top: BOTTOM,
  height: 1000,
  client: 400,
  canPrev: true,
  canNext: true,
  ...more,
});

function run(events: readonly PageFlipInput[]) {
  const memo = createPageFlipMemo();
  return events.map((e) => wheelPageFlip(e, memo));
}

describe('wheelPageFlip', () => {
  it('맨 아래에서 두 눈금(200px) 더 굴리면 다음 쪽', () => {
    expect(run([ev(100, 0), ev(100, 50)])).toEqual([null, 'next']);
  });

  it('맨 위에서 위로 두 눈금 더 굴리면 이전 쪽', () => {
    expect(run([ev(-100, 0, { top: 0 }), ev(-100, 50, { top: 0 })])).toEqual([null, 'prev']);
  });

  it('끝이 아니면 넘기지 않고, 모은 값도 버린다', () => {
    expect(run([ev(100, 0), ev(100, 50, { top: 500 }), ev(100, 100)])).toEqual([null, null, null]);
  });

  it('넘길 쪽이 없으면(마지막 · 첫 쪽) 넘기지 않는다', () => {
    expect(run([ev(100, 0, { canNext: false }), ev(100, 50, { canNext: false }), ev(100, 100, { canNext: false })])).toEqual([null, null, null]);
    expect(run([ev(-100, 0, { top: 0, canPrev: false }), ev(-100, 50, { top: 0, canPrev: false })])).toEqual([null, null]);
  });

  it('쪽이 화면에 다 들어오면(스크롤 없음) 위아래 모두 끝이다', () => {
    const fit = { top: 0, height: 400, client: 400 };
    expect(run([ev(100, 0, fit), ev(100, 50, fit)])).toEqual([null, 'next']);
    expect(run([ev(-100, 0, fit), ev(-100, 50, fit)])).toEqual([null, 'prev']);
  });

  it('작은 값(트랙패드)은 모아서 200px 이 되면', () => {
    const r = run(Array.from({ length: 10 }, (_, i) => ev(25, i * 16)));
    expect(r.indexOf('next')).toBe(7);
  });

  it('방향이 바뀌거나 잠깐 멈추면 모은 값을 버린다', () => {
    expect(run([ev(150, 0), ev(-10, 20), ev(150, 40)])).toEqual([null, null, null]);
    expect(run([ev(150, 0), ev(150, PAGE_FLIP_IDLE_MS + 1)])).toEqual([null, null]);
  });

  it('넘긴 직후 같은 방향 휠은 삼키고, 반대 방향이나 시간이 지나면 그대로', () => {
    const memo = createPageFlipMemo();
    expect(wheelPageFlip(ev(100, 0), memo)).toBe(null);
    expect(wheelPageFlip(ev(100, 50), memo)).toBe('next');
    // 새 쪽 맨 위 — 관성으로 이어 오는 아래 휠은 삼킨다
    expect(wheelPageFlip(ev(100, 100, { top: 0 }), memo)).toBe('swallow');
    expect(wheelPageFlip(ev(-100, 120, { top: 0 }), memo)).toBe(null);
    expect(wheelPageFlip(ev(100, 50 + PAGE_FLIP_LOCK_MS, { top: 0 }), memo)).toBe(null);
  });

  it('가로 휠 · Shift 휠 · 값 0 은 보지 않는다', () => {
    expect(run([ev(100, 0, { shiftKey: true }), ev(100, 50, { shiftKey: true })])).toEqual([null, null]);
    expect(run([ev(100, 0, { deltaX: 150 }), ev(100, 50, { deltaX: 150 })])).toEqual([null, null]);
    expect(run([ev(0, 0)])).toEqual([null]);
  });

  it('줄 단위(Firefox 3줄 = 120px) · 쪽 단위 휠', () => {
    expect(run([ev(3, 0, { deltaMode: 1 }), ev(3, 50, { deltaMode: 1 })])).toEqual([null, 'next']);
    expect(run([ev(1, 0, { deltaMode: 2 })])).toEqual(['next']);
  });
});
