import { useEffect, useRef, type RefObject } from 'react';

/**
 * 바깥 누름 — 켜져 있는 동안 `refs` 밖을 누르면(pointerdown) `onOutside` 를 부른다.
 * 프로토타입의 onRootDown(드롭다운 닫기)과 같다.
 */
export function useOutsidePointerDown(
  refs: ReadonlyArray<RefObject<HTMLElement | null>>,
  onOutside: (event: PointerEvent) => void,
  active: boolean,
): void {
  const handler = useRef(onOutside);
  useEffect(() => {
    handler.current = onOutside;
  });
  useEffect(() => {
    if (!active) return;
    const onDown = (e: PointerEvent) => {
      const t = e.target;
      if (!(t instanceof Node)) return;
      if (refs.some((r) => r.current?.contains(t))) return;
      handler.current(e);
    };
    document.addEventListener('pointerdown', onDown, true);
    return () => document.removeEventListener('pointerdown', onDown, true);
  }, [refs, active]);
}
