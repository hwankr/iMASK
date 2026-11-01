import { useEffect, type RefObject } from 'react';
import { getFocusable } from './focus';

/**
 * 포커스 가둠 — 켜져 있는 동안 Tab/Shift+Tab 이 컨테이너 안에서만 돈다.
 * 컨테이너 밖으로 포커스가 나가면(마우스·스크립트) 첫 요소로 되돌린다.
 */
export function useFocusTrap(ref: RefObject<HTMLElement | null>, active: boolean): void {
  useEffect(() => {
    const box = ref.current;
    if (!active || !box) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab' || e.defaultPrevented) return;
      const items = getFocusable(box);
      if (items.length === 0) {
        e.preventDefault();
        box.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const cur = document.activeElement;
      if (e.shiftKey && (cur === first || cur === box || !box.contains(cur))) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && (cur === last || !box.contains(cur))) {
        e.preventDefault();
        first.focus();
      }
    };
    const onFocusIn = (e: FocusEvent) => {
      const t = e.target;
      if (t instanceof Node && !box.contains(t)) {
        const items = getFocusable(box);
        (items[0] ?? box).focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('focusin', onFocusIn);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('focusin', onFocusIn);
    };
  }, [ref, active]);
}
