'use client';

import type { ChangeEvent, ReactNode } from 'react';
import { cx } from './cx';
import styles from './Switch.module.css';

export interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean, event: ChangeEvent<HTMLInputElement>) => void;
  /** 옆 글자(라벨) */
  label: ReactNode;
  disabled?: boolean;
  id?: string;
  name?: string;
  className?: string;
}

/**
 * 스위치 — `<input type="checkbox" role="switch" aria-checked>` + 라벨. 손잡이가 미끄러진다.
 * Main 467(현재 문서만 보기) · 보드 03. Space 로 켜고 끈다.
 */
export function Switch({ checked, onChange, label, disabled, id, name, className }: SwitchProps) {
  return (
    <label className={cx(styles.wrap, disabled && styles.disabled, className)}>
      <input
        id={id}
        name={name}
        type="checkbox"
        role="switch"
        aria-checked={checked}
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked, e)}
        className={styles.switch}
      />
      {label}
    </label>
  );
}
