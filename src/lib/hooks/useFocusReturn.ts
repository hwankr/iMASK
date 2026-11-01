import { useEffect, useInsertionEffect, useRef, type RefObject } from 'react';

/**
 * 포커스 복귀 — 켜질 때 포커스가 있던 요소를 기억했다가, 꺼지거나(컨테이너가 사라지면) 그 자리로 돌려준다(모달).
 *
 * - 기억은 useInsertionEffect 에서 한다: 자식의 autoFocus(React 가 레이아웃 단계에서 부름)보다 먼저 돌아서
 *   모달 안 입력칸으로 포커스가 옮겨지기 전의 요소(여는 버튼)를 잡는다.
 * - 돌려주기는 다음 프레임에 한다. 그때도 `containerRef` 가 화면에 붙어 있으면(개발 모드의 효과 재실행 등)
 *   아직 열려 있는 것이므로 돌려주지 않는다.
 * - `fallback`(선택): 기억한 요소가 그사이 화면에서 사라졌을 때(예: 목록 오류 모달에서 '다시 시도'하는 동안
 *   행의 '오류 확인' 버튼이 없어졌다가 다시 생김) 대신 포커스할 요소를 찾는다. 열려 있던 마지막 렌더의
 *   함수를 쓴다(닫는 렌더에서는 대상 정보가 이미 지워졌을 수 있어서).
 */
/** 다음 프레임에 확인하는 '아직 열려 있는지' — 정리 함수가 부를 때의 최신 값을 읽는다 */
function stillMounted(ref: RefObject<HTMLElement | null>): boolean {
  return !!ref.current?.isConnected;
}

export function useFocusReturn(
  containerRef: RefObject<HTMLElement | null>,
  active: boolean,
  fallback?: () => HTMLElement | null,
): void {
  const saved = useRef<HTMLElement | null>(null);
  const fallbackRef = useRef<(() => HTMLElement | null) | undefined>(undefined);

  // 열려 있는 동안의 최신 fallback 만 기억한다(닫는 렌더의 값으로 덮지 않음)
  useEffect(() => {
    if (active) fallbackRef.current = fallback;
  });

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
        const find = fallbackRef.current;
        fallbackRef.current = undefined;
        if (prev && prev.isConnected) {
          prev.focus({ preventScroll: true });
          return;
        }
        // 기억한 자리가 없어졌다 — 다른 곳에 이미 포커스가 갔으면(사용자가 옮김) 그대로 둔다
        const now = document.activeElement;
        if (now && now !== document.body) return;
        const alt = find?.();
        if (alt && alt.isConnected) alt.focus({ preventScroll: true });
      });
    };
  }, [active, containerRef]);
}
