'use client';

import { useEffect, useId, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type MouseEvent } from 'react';
import type { IconName } from '@/display/icon-names';
import { isPressFocusable, keepFocusThroughPress } from '@/lib/hooks/focus';
import { useOutsidePointerDown } from '@/lib/hooks/useOutsidePointerDown';
import { cx } from './cx';
import { Icon } from './Icon';
import styles from './Dropdown.module.css';

export interface DropdownOption<V extends string = string> {
  value: V;
  label: string;
  /** 타일 아이콘 — 선 아이콘(dg-i-*) 또는 위험 막대(dg-r*). filter·sort 모양에서만 그린다. */
  icon?: IconName;
  /** 타일 아이콘 색(CSS 값, 예: 'var(--hi)' — ② 표시 규칙의 fg). 기본 --ink-2 */
  iconColor?: string;
  /** 타일 바탕(CSS 값, 예: 'var(--hi-bg)'). 기본 --fill */
  tileColor?: string;
  /** 해당 건수 */
  count?: number;
  /** 분류 수정 창 — 최초 AI 값에 '최초 AI' 표시 */
  aiOriginal?: boolean;
}

/**
 * 모양
 * - filter: 목록 필터. 트리거 '제목 값', 필터가 걸리면 초록. 메뉴에 제목·타일 아이콘·건수
 * - sort: 목록 정렬. 바탕 없는 트리거 + 정렬 아이콘, 트리거 글자는 값만
 * - field: 모달 안 선택칸(분류 수정). 꽉 찬 폭 48px, 바깥 라벨(labelledBy), 메뉴에 '최초 AI' 표시
 */
export type DropdownVariant = 'filter' | 'sort' | 'field';

export interface DropdownProps<V extends string> {
  variant?: DropdownVariant;
  /** 메뉴 제목(filter·sort 메뉴 위 작은 글자, 목록의 aria-label) — filter 트리거는 '제목 값' */
  title: string;
  value: V;
  options: readonly DropdownOption<V>[];
  onChange: (value: V) => void;
  /** filter: 필터가 걸린 상태(초록). 기본은 첫 옵션(전체)이 아닐 때 */
  active?: boolean;
  /** field: 값이 원래 값과 달라짐(옅은 초록 + 강조 테두리) */
  changed?: boolean;
  /** 메뉴를 트리거의 어느 쪽에 맞출지 — start(왼쪽) · end(오른쪽) */
  align?: 'start' | 'end';
  /** 트리거 aria-label — 기본 filter '제목 필터: 값', sort '정렬: 값' (field 는 labelledBy 를 쓴다) */
  ariaLabel?: string;
  /** field: 바깥 라벨 요소 id(트리거는 '라벨 + 값' 으로 읽힌다) */
  labelledBy?: string;
  /** 처음부터 펼쳐 둔다(견본·상태 미리보기용) */
  defaultOpen?: boolean;
  disabled?: boolean;
  id?: string;
  className?: string;
}

/** 다음 렌더 뒤 포커스를 옮길 곳 — 목록 / 트리거 / 트리거(스크롤하지 않음 · 바깥 누름) */
type PendingFocus = 'list' | 'trigger' | 'trigger-quiet' | null;

/** 정렬 아이콘 — 프로토타입 150줄의 인라인 경로(스프라이트에 없음) */
function SortIcon() {
  return (
    <svg className={styles.sortIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d="M7 4v16M3.5 16.5 7 20l3.5-3.5M17 20V4M13.5 7.5 17 4l3.5 3.5" />
    </svg>
  );
}

/**
 * 드롭다운 — 브라우저 기본 select 대신 같은 디자인의 메뉴(보드 03 · Main 148–160 · 717–724).
 * 버튼 아래로 살짝 내려오며 열리고(dg-drop) 화살표가 뒤집힌다.
 * 키보드(프로토타입 1810–1859): 트리거에서 ↓/↑ 로 열고 목록으로, 목록에서 ↑↓·Home·End 이동, Enter 로 고름,
 * Esc 로 닫고 트리거로, Tab 은 닫고 다음으로. 바깥을 누르면 닫힌다. 고르면 트리거로 포커스가 돌아온다.
 *
 * 바깥 누름으로 닫을 때의 포커스 정책:
 * - 포커스를 받는 요소(활성 입력칸·버튼·링크·tabindex 요소 …, 또는 연결된 컨트롤이 포커스를 받을 수 있는 라벨)를
 *   눌렀으면 그 요소가 포커스를 가져간다 — 빼앗지 않는다(판정은 `isPressFocusable`).
 * - 포커스를 받지 않는 곳(글자·빈 바탕, 연결 컨트롤이 없거나 비활성·숨김인 라벨, 비활성 컨트롤 등)을 눌렀고
 *   포커스가 드롭다운(트리거·목록) 안에 있었으면
 *   다른 닫기와 같이 트리거로 돌려준다(화면은 스크롤하지 않음). 그 누름의 mousedown 이 포커스를 풀지 않게 막는다.
 * - 포커스가 처음부터 드롭다운 밖에 있었으면(예: 처음부터 펼친 견본) 건드리지 않는다.
 */
export function Dropdown<V extends string>({
  variant = 'filter',
  title,
  value,
  options,
  onChange,
  active,
  changed = false,
  align = 'start',
  ariaLabel,
  labelledBy,
  defaultOpen = false,
  disabled = false,
  id,
  className,
}: DropdownProps<V>) {
  const [open, setOpen] = useState(defaultOpen);
  const [tick, setTick] = useState(0);
  const pending = useRef<PendingFocus>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const autoId = useId();
  const triggerId = id ?? `${autoId}-btn`;
  const listId = `${autoId}-list`;

  const current = options.find((o) => o.value === value) ?? options[0];
  const isField = variant === 'field';
  const isSort = variant === 'sort';
  const on = variant === 'filter' && (active ?? (options.length > 0 && value !== options[0].value));

  // 포커스 옮기기 — 열린 뒤 목록(고른 항목 또는 첫 항목)으로, 닫힌 뒤 트리거로
  useEffect(() => {
    const f = pending.current;
    if (!f) return;
    pending.current = null;
    if (f === 'list' && open) {
      const list = listRef.current;
      const el = list?.querySelector<HTMLElement>('[role="option"][aria-selected="true"]') ?? list?.querySelector<HTMLElement>('[role="option"]');
      el?.focus();
    } else if (f === 'trigger') {
      triggerRef.current?.focus();
    } else if (f === 'trigger-quiet') {
      triggerRef.current?.focus({ preventScroll: true });
    }
  }, [open, tick]);

  const outsideRefs = useMemo(() => [wrapRef], []);
  /** 닫기 — 모든 닫는 경로가 여기로 온다. focusTo: 닫힌 뒤 포커스를 옮길 곳(null 이면 그대로) */
  const close = (focusTo: PendingFocus) => {
    pending.current = focusTo;
    setOpen(false);
  };

  useOutsidePointerDown(
    outsideRefs,
    (event) => {
      // 정책은 컴포넌트 설명 참고 — 포커스를 받는 요소를 눌렀으면 그 요소에 맡긴다
      const focusWasInside = wrapRef.current?.contains(document.activeElement) ?? false;
      const toTrigger = focusWasInside && !isPressFocusable(event.target);
      if (toTrigger) keepFocusThroughPress(event);
      close(toTrigger ? 'trigger-quiet' : null);
    },
    open,
  );

  const onTriggerClick = (e: MouseEvent<HTMLButtonElement>) => {
    const next = !open;
    // 키보드(Enter·Space)로 연 경우(detail 0)에는 목록으로 포커스
    pending.current = next && e.detail === 0 ? 'list' : null;
    setOpen(next);
  };

  const onTriggerKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      pending.current = 'list';
      setOpen(true);
      setTick((t) => t + 1);
    } else if (e.key === 'Escape' && open) {
      e.preventDefault();
      e.stopPropagation();
      close('trigger');
    }
  };

  const onListKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const opts = Array.from(e.currentTarget.querySelectorAll<HTMLElement>('[role="option"]'));
    const i = opts.indexOf(document.activeElement as HTMLElement);
    const go = (j: number) => opts[Math.max(0, Math.min(opts.length - 1, j))]?.focus();
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        go(i < 0 ? 0 : i + 1);
        break;
      case 'ArrowUp':
        e.preventDefault();
        go(i < 0 ? opts.length - 1 : i - 1);
        break;
      case 'Home':
        e.preventDefault();
        go(0);
        break;
      case 'End':
        e.preventDefault();
        go(opts.length - 1);
        break;
      case 'Escape':
        e.preventDefault();
        e.stopPropagation();
        close('trigger');
        break;
      case 'Tab':
        close(null);
        break;
      default:
        break;
    }
  };

  const pick = (v: V) => {
    onChange(v);
    close('trigger');
  };

  const label = isField || isSort ? current?.label ?? '' : `${title} ${current?.label ?? ''}`;
  const triggerAria = isField ? undefined : (ariaLabel ?? (isSort ? `정렬: ${current?.label ?? ''}` : `${title} 필터: ${current?.label ?? ''}`));

  return (
    <div ref={wrapRef} className={cx(styles.wrap, isField && styles.wrapField, className)}>
      <button
        ref={triggerRef}
        id={triggerId}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-label={triggerAria}
        aria-labelledby={isField && labelledBy ? `${labelledBy} ${triggerId}` : undefined}
        disabled={disabled}
        onClick={onTriggerClick}
        onKeyDown={onTriggerKeyDown}
        className={cx(
          styles.trigger,
          styles[`trigger-${variant}`],
          on && styles.on,
          isField && changed && styles.changed,
          open && styles.open,
        )}
      >
        {isSort ? <SortIcon /> : null}
        <span className={styles.value}>{label}</span>
        <span aria-hidden="true" className={cx(styles.chev, open && styles.chevOpen)}>
          <Icon name="dg-i-chev-down" size={15} strokeWidth={2.2} />
        </span>
      </button>
      {open ? (
        <div
          ref={listRef}
          id={listId}
          role="listbox"
          aria-label={isField && labelledBy ? undefined : title}
          aria-labelledby={isField && labelledBy ? labelledBy : undefined}
          onKeyDown={onListKeyDown}
          className={cx(styles.menu, isField ? styles.menuField : styles.menuList, align === 'end' ? styles.alignEnd : styles.alignStart)}
        >
          {isField ? null : (
            <div aria-hidden="true" className={styles.menuTitle}>
              {title}
            </div>
          )}
          {options.map((o) => {
            const sel = o.value === value;
            const glyph = o.icon?.startsWith('dg-r') ?? false;
            const tileStyle = { '--dd-tile-bg': o.tileColor ?? 'var(--fill)', '--dd-tile-fg': o.iconColor ?? 'var(--ink-2)' } as CSSProperties;
            return (
              <button
                key={o.value}
                type="button"
                role="option"
                aria-selected={sel}
                tabIndex={-1}
                onClick={() => pick(o.value)}
                className={cx(styles.option, isField ? styles.optionField : styles.optionList, sel && styles.selected)}
              >
                {!isField && o.icon ? (
                  <span aria-hidden="true" className={styles.tile} style={tileStyle}>
                    {glyph ? <Icon name={o.icon} size={12} /> : <Icon name={o.icon} size={15} strokeWidth={2.1} />}
                  </span>
                ) : null}
                <span className={styles.optionLabel}>{o.label}</span>
                {isField && o.aiOriginal ? <span className={styles.ai}>최초 AI</span> : null}
                {!isField && o.count !== undefined ? <span className={styles.count}>{o.count}</span> : null}
                <span aria-hidden="true" className={styles.check}>
                  <Icon name="dg-i-check" size={16} strokeWidth={2.6} />
                </span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
