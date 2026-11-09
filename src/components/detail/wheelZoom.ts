/* ==========================================================================
   원문 뷰어 Ctrl + 휠 — 브라우저 화면 확대 대신 원문 배율(0.4~2배, 0.1 단위)을 바꾼다.
   - 마우스 휠: 눈금 한 번(이벤트 하나)에 한 단계(0.1 — 확대 · 축소 버튼과 같다). 줄 · 쪽 단위 휠(Firefox)도 이벤트마다 한 단계.
     화소 단위의 작은 값(고해상도 휠 · 트랙패드 두 손가락 스크롤)은 모아서 눈금 하나(100px)마다 한 단계.
   - 트랙패드 오므리기: 브라우저가 ctrlKey 휠(작은 화소 값)로 보낸다. 실제 Ctrl 키가 떼어져 있으면 오므리기로 보고
     배율 × e^(−deltaY / 100)(브라우저가 오므리기를 휠 값으로 바꾸는 공식의 역)으로 이어서 바꾼다 — 반올림 전 배율을 들고 있다.
   - 잠깐(WHEEL_IDLE_MS) 멈추면 모아 둔 값을 버린다.
   순수 함수(React · DOM 없음) — 붙이는 곳은 DocViewer.tsx, 시험은 wheelZoom.test.ts.
   ========================================================================== */

import { normalizeZoom, ZOOM_MAX, ZOOM_MIN } from './detailState';

/** 화소 휠 눈금 하나(Chrome · Edge 기본 100 — 화면 배율에 따라 더 크다) */
export const WHEEL_NOTCH_PX = 100;
/** 배율 한 단계 — 확대 · 축소 버튼과 같다 */
export const WHEEL_ZOOM_STEP = 0.1;
/** 이만큼(ms) 멈추면 모아 둔 휠 값을 버린다 */
export const WHEEL_IDLE_MS = 300;

/** WheelEvent 에서 쓰는 값 */
export interface WheelInput {
  deltaX: number;
  deltaY: number;
  /** 0 화소 · 1 줄 · 2 쪽 */
  deltaMode: number;
  ctrlKey: boolean;
  /** 이벤트 시각(ms) */
  timeStamp: number;
}

/** 이벤트 사이에 들고 있는 값 */
export interface WheelZoomMemo {
  /** 모자란 눈금(작은 화소 값을 모은 것, + 확대) */
  ticks: number;
  /** 오므리는 중인 반올림 전 배율 */
  pinch: number | null;
  /** 마지막 이벤트 시각 */
  at: number;
}

export function createWheelZoomMemo(): WheelZoomMemo {
  return { ticks: 0, pinch: null, at: Number.NEGATIVE_INFINITY };
}

/** 트랙패드 오므리기인가 — ctrlKey 인데 실제 Ctrl 키는 떼어져 있는, 작은 화소 단위 세로 휠 */
export function isPinchWheel(e: WheelInput, ctrlHeld: boolean): boolean {
  return e.ctrlKey && !ctrlHeld && e.deltaMode === 0 && e.deltaX === 0 && Math.abs(e.deltaY) < WHEEL_NOTCH_PX / 2;
}

/**
 * 휠 이벤트 하나 → 새 배율(0.1 단위로 맞춘 값), 바뀌지 않으면 null. memo 를 고친다.
 * zoom 은 지금 배율이다(화면 맞춤이면 그 배율 — 0.1 단위가 아닐 수 있다. 버튼처럼 한 단계 옮긴 뒤 0.1 단위로 맞춘다).
 */
export function wheelZoom(zoom: number, e: WheelInput, pinch: boolean, memo: WheelZoomMemo): number | null {
  if (e.timeStamp - memo.at > WHEEL_IDLE_MS) {
    memo.ticks = 0;
    memo.pinch = null;
  }
  memo.at = e.timeStamp;

  let target: number;
  if (pinch) {
    memo.ticks = 0;
    // 들고 있던 배율이 지금 배율과 다르면(버튼 · 화면 맞춤으로 바뀌었다) 지금 배율에서 다시 시작한다
    const base = memo.pinch !== null && normalizeZoom(memo.pinch) === normalizeZoom(zoom) ? memo.pinch : zoom;
    target = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, base * Math.exp(-e.deltaY / WHEEL_NOTCH_PX)));
    memo.pinch = target;
  } else {
    memo.pinch = null;
    let steps: number;
    if (e.deltaMode !== 0 || Math.abs(e.deltaY) >= WHEEL_NOTCH_PX / 2) {
      // 눈금 한 번 — 값의 크기(화면 배율 · 휠 설정에 따라 다르다)와 상관없이 한 단계
      memo.ticks = 0;
      steps = -Math.sign(e.deltaY);
    } else {
      memo.ticks -= e.deltaY / WHEEL_NOTCH_PX;
      steps = Math.trunc(memo.ticks);
      memo.ticks -= steps;
    }
    if (!steps) return null;
    target = zoom + steps * WHEEL_ZOOM_STEP;
  }

  const next = normalizeZoom(target);
  return Math.abs(next - zoom) < 0.005 ? null : next;
}
