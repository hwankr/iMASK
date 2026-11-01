'use client';

import type { ButtonHTMLAttributes, MouseEvent } from 'react';

export interface GuardedButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** true 면 누름을 막는다 — 로딩·비활성 표시(aria-disabled) 상태 */
  blocked: boolean;
}

/**
 * `<button>` + 누름 막기 — Button 의 실제 요소(브라우저에서만 도는 처리기가 있어 클라이언트 컴포넌트).
 *
 * 막힌 상태(로딩·aria-disabled)는 `disabled` 를 쓰지 않으므로(포커스를 잃지 않게) 브라우저가 누름을
 * 그대로 처리한다. 그래서 처리기를 항상 달아 두고, 막힌 동안에는
 * - `preventDefault()` — 기본 동작(type="submit" 이면 폼 제출, type="reset" 이면 초기화)을 막는다.
 *   마우스 클릭·Enter·Space 와 폼 안 입력칸에서 Enter(암묵적 제출 — 기본 버튼에 click 을 보낸다) 모두 click 으로 온다.
 * - `stopPropagation()` — 진짜 `disabled` 버튼처럼 부모의 click 처리기(예: 행 누르기)에도 전하지 않는다.
 * - 전달받은 `onClick` 을 부르지 않는다.
 * 일반 상태에서만 `onClick` 을 부른다.
 */
export function GuardedButton({ blocked, onClick, ...rest }: GuardedButtonProps) {
  const handleClick = (event: MouseEvent<HTMLButtonElement>) => {
    if (blocked) {
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    onClick?.(event);
  };
  return <button {...rest} onClick={handleClick} />;
}
