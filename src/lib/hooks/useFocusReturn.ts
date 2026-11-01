import { useEffect, useInsertionEffect, useRef, type RefObject } from 'react';

/**
 * 포커스 복귀 — 켜질 때 포커스가 있던 요소를 기억했다가, 꺼지거나(컨테이너가 사라지면) 그 자리로 돌려준다(모달).
 *
 * - 기억은 useInsertionEffect 에서 한다: 자식의 autoFocus(React 가 레이아웃 단계에서 부름)보다 먼저 돌아서
 *   모달 안 입력칸으로 포커스가 옮겨지기 전의 요소(여는 버튼)를 잡는다.
 * - 돌려주기는 다음 프레임에 한다. 그때도 `containerRef` 가 화면에 붙어 있으면(개발 모드의 효과 재실행 등)
 *   아직 열려 있는 것이므로 돌려주지 않는다.
 */
/** 다음 프레임에 확인하는 '아직 열려 있는지' — 정리 함수가 부를 때의 최신 값을 읽는다 */
function stillMounted(ref: RefObject<HTMLElement | null>): boolean {
  return !!ref.current?.isConnected;
}

export function useFocusReturn(containerRef: RefObject<HTMLElement | null>, active: boolean): void {
  const saved = useRef<HTMLElement | null>(null);

  useInsertionEffect(() => {
    if (!active || saved.current) return;
    const el = document.activeElement;
    if (el instanceof HTMLElement && el !== document.body) saved.current = el;
  }, [active]);

  useEffect(() => {
    if (!active) return;
    return () => {
      window.requestAnimationFrame(() => {
        if (stillMounted(containerRef)) return;
        const prev = saved.current;
        saved.current = null;
        if (prev && prev.isConnected) prev.focus({ preventScroll: true });
      });
    };
  }, [active, containerRef]);
}
