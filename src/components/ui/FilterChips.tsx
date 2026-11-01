'use client';

import { cx } from './cx';
import styles from './FilterChips.module.css';

export interface FilterChip<V extends string = string> {
  value: V;
  label: string;
  count?: number;
}

export interface FilterChipsProps<V extends string> {
  chips: readonly FilterChip<V>[];
  value: V;
  onChange: (value: V) => void;
  /** 묶음의 aria-label(예: '탐지 항목 필터') */
  ariaLabel: string;
  className?: string;
}

/**
 * 필터 칩 — 고르면 어둡게 채움, 건수 표시, aria-pressed. 하나만 고른다. Main 465 · 보드 03.
 * 높이는 --chip-h(30 · 휴대폰 36).
 */
export function FilterChips<V extends string>({ chips, value, onChange, ariaLabel, className }: FilterChipsProps<V>) {
  return (
    <div role="group" aria-label={ariaLabel} className={cx(styles.group, className)}>
      {chips.map((c) => {
        const on = c.value === value;
        return (
          <button key={c.value} type="button" aria-pressed={on} onClick={() => onChange(c.value)} className={cx(styles.chip, on && styles.on)}>
            {c.label}
            {c.count !== undefined ? <span className={styles.count}>{c.count}</span> : null}
          </button>
        );
      })}
    </div>
  );
}
