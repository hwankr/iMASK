'use client';

import { useEffect, useId, useRef, type KeyboardEvent, type MouseEvent, type PointerEvent, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { useFocusReturn } from '@/lib/hooks/useFocusReturn';
import { useFocusTrap } from '@/lib/hooks/useFocusTrap';
import { useInertBackground } from '@/lib/hooks/useInertBackground';
import { useIsClient } from '@/lib/hooks/useIsClient';
import { useScrollLock } from '@/lib/hooks/useScrollLock';
import { cx } from './cx';
import { IconButton } from './IconButton';
import { Spinner } from './Spinner';
import styles from './Modal.module.css';

/** 바닥 버튼 — 프로토타입 modalVM 의 btn(label, act, kind, { disabled, spin, focus }) */
export interface ModalButton {
  label: string;
  onClick: () => void;
  /** primary: 채운 초록 · secondary: 회색 채움 · ghost: 글자 버튼 · danger: 옅은 빨강(지우기 — Button danger 와 같은 토큰). 기본 secondary */
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  disabled?: boolean;
  /** 돌림 표시 + 글자, 누를 수 없음(포커스는 남는다) */
  loading?: boolean;
  /** 열릴 때 이 버튼에 포커스 */
  autoFocus?: boolean;
}

/** 창 최대 폭 — sm 540(기본) · md 600 · lg 640 (프로토타입 md.w) */
export type ModalWidth = 'sm' | 'md' | 'lg';

export interface ModalProps {
  open: boolean;
  /** 닫기 버튼·Esc·배경 누름 */
  onClose: () => void;
  title: string;
  subtitle?: ReactNode;
  width?: ModalWidth;
  children?: ReactNode;
  buttons?: readonly ModalButton[];
  /** false 면 Esc·배경 누름·닫기 버튼으로 닫히지 않는다(작업 중 등). 기본 true */
  dismissible?: boolean;
  /** 열릴 때 포커스할 요소. 없으면 autoFocus 가 걸린 요소, 그것도 없으면 창 자체 */
  initialFocus?: RefObject<HTMLElement | null>;
  /**
   * 닫힐 때 열기 전 자리(여는 버튼)가 화면에서 사라졌으면 대신 포커스할 요소를 찾는다(선택).
   * 예: 목록 오류 모달 — '다시 시도'하는 동안 행의 '오류 확인' 버튼이 없어졌다가 새로 생긴다.
   */
  returnFocus?: () => HTMLElement | null;
  /**
   * 견본용 — 포털·포커스 가둠·inert·스크롤 잠금 없이 놓인 자리에 흐린 판과 함께 그린다(보드 06, 상태 미리보기).
   * 이때는 대화상자가 아니라 이름 붙은 묶음(role="group")이다.
   */
  inline?: boolean;
  className?: string;
}

/**
 * 모달 — Main 703–755. 배경이 흐려지고(dg-fade) 창이 살짝 커지며 떠오른다(dg-pop).
 * 휴대폰(< 768px)에서는 아래에서 올라오는 시트(dg-sheet, 손잡이, 위쪽만 둥글게).
 * 포털(document.body)로 그리고, 열린 동안 포커스 가둠·뒤 화면 inert·스크롤 잠금,
 * 닫히면 열기 전 자리로 포커스를 돌려준다.
 */
export function Modal({
  open,
  onClose,
  title,
  subtitle,
  width = 'sm',
  children,
  buttons,
  dismissible = true,
  initialFocus,
  returnFocus,
  inline = false,
  className,
}: ModalProps) {
  const isClient = useIsClient();
  const dialogRef = useRef<HTMLDivElement>(null);
  const downOnBackdrop = useRef(false);
  const titleId = useId();
  const subId = useId();
  const active = open && isClient && !inline;

  useFocusReturn(dialogRef, active, returnFocus);
  useFocusTrap(dialogRef, active);
  useInertBackground(active);
  useScrollLock(active);

  // 처음 포커스 — 자식의 autoFocus 가 이미 옮겼으면 그대로 둔다
  useEffect(() => {
    if (!active) return;
    const box = dialogRef.current;
    if (!box || box.contains(document.activeElement)) return;
    const target = initialFocus?.current;
    (target ?? box).focus({ preventScroll: true });
  }, [active, initialFocus]);

  if (!open || (!inline && !isClient)) return null;

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'Escape' || e.defaultPrevented || inline) return;
    e.stopPropagation();
    if (dismissible) onClose();
  };
  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    downOnBackdrop.current = e.target === e.currentTarget;
  };
  const onBackdropClick = (e: MouseEvent<HTMLDivElement>) => {
    const fromBackdrop = downOnBackdrop.current && e.target === e.currentTarget;
    downOnBackdrop.current = false;
    if (fromBackdrop && dismissible && !inline) onClose();
  };

  const dialog = (
    <div className={cx(styles.backdrop, inline && styles.inlineBackdrop)} onKeyDown={onKeyDown} onPointerDown={onPointerDown} onClick={onBackdropClick}>
      <div
        ref={dialogRef}
        role={inline ? 'group' : 'dialog'}
        aria-modal={inline ? undefined : true}
        aria-labelledby={titleId}
        aria-describedby={subtitle ? subId : undefined}
        tabIndex={inline ? undefined : -1}
        className={cx(styles.dialog, styles[width], inline && styles.inlineDialog, className)}
      >
        <div className={styles.handle} aria-hidden="true">
          <span />
        </div>
        <div className={styles.head}>
          <div className={styles.headText}>
            <h2 id={titleId} className={styles.title}>
              {title}
            </h2>
            {subtitle ? (
              <p id={subId} className={styles.sub}>
                {subtitle}
              </p>
            ) : null}
          </div>
          <IconButton
            label="닫기"
            icon="dg-i-x"
            size={40}
            iconSize={20}
            strokeWidth={2.2}
            className={styles.close}
            onClick={onClose}
            disabled={!dismissible}
          />
        </div>
        <div className={styles.body}>{children}</div>
        {buttons && buttons.length > 0 ? (
          <div className={styles.foot}>
            {buttons.map((b, i) => (
              <button
                key={`${i}-${b.label}`}
                type="button"
                className={cx(styles.btn, styles[b.variant ?? 'secondary'], b.loading && styles.loading)}
                onClick={b.loading ? undefined : b.onClick}
                disabled={b.disabled}
                aria-disabled={b.loading || undefined}
                aria-busy={b.loading || undefined}
                autoFocus={inline ? undefined : b.autoFocus}
              >
                {b.loading ? <Spinner size={16} /> : null}
                {b.label}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );

  return inline ? dialog : createPortal(dialog, document.body);
}
