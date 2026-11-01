'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { cx } from './cx';
import { Icon } from './Icon';
import { useAnnounce } from './LiveRegion';
import styles from './Toast.module.css';

export type ToastKind = 'ok' | 'error';

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface ToastOptions {
  kind?: ToastKind;
  action?: ToastAction;
}

/** 사라지는 시간(밀리초) — 프로토타입 1599줄: 행동 버튼이 있으면 6.5초, 없으면 3.8초 */
export const TOAST_DURATION_MS = { withAction: 6500, plain: 3800 } as const;

export interface ToastProps {
  text: string;
  kind?: ToastKind;
  action?: ToastAction | null;
  /**
   * true(기본): 화면 아래 가운데에 떠서 올라온다(dg-toast).
   * false: 놓인 자리에 그대로 그린다(/dev/components 견본용).
   */
  floating?: boolean;
  className?: string;
}

/** 토스트 한 개(모양). 보통은 useToast() 로 띄운다. */
export function Toast({ text, kind = 'ok', action, floating = true, className }: ToastProps) {
  return (
    <div className={cx(styles.toast, floating && styles.floating, className)} data-kind={kind}>
      <span className={cx(styles.icon, kind === 'error' ? styles.iconError : styles.iconOk)}>
        <Icon name={kind === 'error' ? 'dg-i-alert' : 'dg-i-check-circle'} size={19} strokeWidth={2.2} />
      </span>
      <span>{text}</span>
      {action ? (
        <button type="button" className={styles.action} onClick={action.onClick}>
          {action.label}
        </button>
      ) : null}
    </div>
  );
}

/** useToast() 가 돌려주는 함수 — `toast(text, { kind, action })`, `toast.dismiss()` */
export type ToastFn = ((text: string, options?: ToastOptions) => void) & { dismiss: () => void };

const ToastContext = createContext<ToastFn | null>(null);

interface ToastState {
  id: number;
  text: string;
  kind: ToastKind;
  action: ToastAction | null;
}

/**
 * 토스트 제공자 — 한 번에 하나만 보인다. 새 토스트가 오면 앞의 것을 바꾼다.
 * 글자는 LiveRegion(useAnnounce)으로도 알린다. LiveRegionProvider 안에 둔다.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const announce = useAnnounce();
  const [toast, setToast] = useState<ToastState | null>(null);

  const dismiss = useCallback(() => setToast(null), []);

  const show = useCallback(
    (text: string, options: ToastOptions = {}) => {
      setToast((prev) => ({ id: (prev?.id ?? 0) + 1, text, kind: options.kind ?? 'ok', action: options.action ?? null }));
      announce(text);
    },
    [announce],
  );

  // 보인 뒤 정해진 시간이 지나면 사라진다. 새 토스트가 오면(id 가 바뀌면) 시간을 다시 잰다.
  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), toast.action ? TOAST_DURATION_MS.withAction : TOAST_DURATION_MS.plain);
    return () => window.clearTimeout(t);
  }, [toast]);

  const api = useMemo<ToastFn>(() => Object.assign((text: string, options?: ToastOptions) => show(text, options), { dismiss }), [show, dismiss]);

  const act = toast?.action;
  return (
    <ToastContext.Provider value={api}>
      {children}
      {toast ? (
        <Toast
          key={toast.id}
          text={toast.text}
          kind={toast.kind}
          action={
            act
              ? {
                  label: act.label,
                  onClick: () => {
                    dismiss();
                    act.onClick();
                  },
                }
              : null
          }
        />
      ) : null}
    </ToastContext.Provider>
  );
}

/** 토스트 띄우기 — ToastProvider(AppShell) 안에서 쓴다 */
export function useToast(): ToastFn {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast() 는 ToastProvider 안에서만 쓸 수 있습니다(AppShell).');
  return ctx;
}
