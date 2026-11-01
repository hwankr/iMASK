'use client';

import { useRef, type CSSProperties, type KeyboardEvent } from 'react';
import { cx } from './cx';
import styles from './SegmentedTabs.module.css';

export interface SegmentedTab<V extends string = string> {
  value: V;
  label: string;
  /** 탭 옆 건수 */
  count?: number;
  /** warn: 건수가 0보다 크면 주의 색(검토 필요 탭) */
  tone?: 'default' | 'warn';
}

export interface SegmentedTabsProps<V extends string> {
  tabs: readonly SegmentedTab<V>[];
  value: V;
  onChange: (value: V) => void;
  /** tablist 의 aria-label(예: '결과 구분') */
  ariaLabel: string;
  /**
   * md: 결과 패널 탭(높이 38 · 13.5px · 건수 · Main 459)
   * lg: 휴대폰 상세 전환 탭(높이 40 · 14px · Main 367)
   */
  size?: 'md' | 'lg';
  /** 탭·패널 id 앞부분 — 주면 탭에 id·aria-controls 가 붙는다(패널은 tabPanelProps 로) */
  idPrefix?: string;
  className?: string;
}

/** 탭 패널에 붙일 속성 — `<div {...tabPanelProps('dg-res', 'findings')}>` */
export function tabPanelProps(idPrefix: string, value: string) {
  return { id: `${idPrefix}-panel-${value}`, role: 'tabpanel' as const, 'aria-labelledby': `${idPrefix}-tab-${value}`, tabIndex: 0 };
}

/**
 * 세그먼트 탭 — 흰 판이 고른 탭으로 미끄러진다(transform .34s). 보드 03 · Main 367·459.
 * 키보드: ←/→(↑/↓) 이웃 탭으로 옮기며 고름(반복), Home·End 처음·끝. 고른 탭만 Tab 순서에 든다(roving tabindex).
 */
export function SegmentedTabs<V extends string>({ tabs, value, onChange, ariaLabel, size = 'md', idPrefix, className }: SegmentedTabsProps<V>) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const idx = Math.max(0, tabs.findIndex((t) => t.value === value));
  const style = { '--tab-n': tabs.length, '--tab-i': idx } as CSSProperties;

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const n = tabs.length;
    if (n === 0) return;
    let next = -1;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (idx + 1) % n;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = (idx - 1 + n) % n;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = n - 1;
    if (next < 0) return;
    e.preventDefault();
    onChange(tabs[next].value);
    refs.current[next]?.focus();
  };

  return (
    <div role="tablist" aria-label={ariaLabel} onKeyDown={onKeyDown} className={cx(styles.list, styles[size], className)} style={style}>
      <span aria-hidden="true" className={styles.knob} />
      {tabs.map((t, i) => {
        const on = i === idx;
        const warn = t.tone === 'warn' && (t.count ?? 0) > 0;
        return (
          <button
            key={t.value}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="tab"
            id={idPrefix ? `${idPrefix}-tab-${t.value}` : undefined}
            aria-controls={idPrefix ? `${idPrefix}-panel-${t.value}` : undefined}
            aria-selected={on}
            tabIndex={on ? 0 : -1}
            onClick={() => onChange(t.value)}
            className={cx(styles.tab, on && styles.on)}
          >
            {t.label}
            {t.count !== undefined ? <span className={cx(styles.count, warn ? styles.countWarn : on && styles.countOn)}>{t.count}</span> : null}
          </button>
        );
      })}
    </div>
  );
}
