'use client';

import type { ChangeEvent, KeyboardEvent, Ref } from 'react';
import { cx } from './cx';
import { Icon } from './Icon';
import { VisuallyHidden } from './VisuallyHidden';
import styles from './SearchField.module.css';

export interface SearchFieldProps {
  value: string;
  onChange: (event: ChangeEvent<HTMLInputElement>) => void;
  /** 화면 낭독기용 라벨(보이지 않음). 기본은 placeholder 와 같다. */
  label?: string;
  placeholder?: string;
  onKeyDown?: (event: KeyboardEvent<HTMLInputElement>) => void;
  inputRef?: Ref<HTMLInputElement>;
  id?: string;
  name?: string;
  disabled?: boolean;
  /** 감싸는 label 의 클래스 — 폭(flex·max-width)은 쓰는 쪽이 정한다 */
  className?: string;
}

/**
 * 검색칸 — 왼쪽 검색 아이콘, `type="search"`. Main 143–147 · 보드 03.
 * 검색어가 있으면 흰 바탕 + 옅은 초록 테두리, 누르면 흰 바탕 + 강조색 2px.
 */
export function SearchField({
  value,
  onChange,
  label,
  placeholder = '분석명 또는 파일명 검색',
  onKeyDown,
  inputRef,
  id,
  name,
  disabled,
  className,
}: SearchFieldProps) {
  const filled = value.trim().length > 0;
  return (
    <label className={cx(styles.wrap, className)}>
      <VisuallyHidden>{label ?? placeholder}</VisuallyHidden>
      <span className={styles.icon}>
        <Icon name="dg-i-search" size={18} strokeWidth={2} />
      </span>
      <input
        ref={inputRef}
        id={id}
        name={name}
        type="search"
        value={value}
        onChange={onChange}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        autoComplete="off"
        className={cx(styles.input, filled && styles.filled)}
      />
    </label>
  );
}
