'use client';

import { useId, type ChangeEvent, type FocusEvent, type KeyboardEvent, type ReactNode, type Ref } from 'react';
import { cx } from './cx';
import { VisuallyHidden } from './VisuallyHidden';
import styles from './TextField.module.css';

type FieldElement = HTMLInputElement | HTMLTextAreaElement;

export interface TextFieldProps {
  /** 보이는 라벨 */
  label: ReactNode;
  value: string;
  onChange: (event: ChangeEvent<FieldElement>) => void;
  /** 여러 줄(모달의 사유·메모) */
  multiline?: boolean;
  /** 여러 줄일 때 줄 수 — 기본 3(프로토타입 noteRows) */
  rows?: number;
  /** 필수 — 붉은 * 를 붙이고 화면 낭독기에는 '(필수)' 로 읽힌다 */
  required?: boolean;
  /** 라벨 옆 작은 설명(예: '(필수 · 검토 이력에 남습니다)') */
  labelNote?: ReactNode;
  /** 입력 아래 도움말 */
  help?: ReactNode;
  /** 오류 문구 — 있으면 붉은 바탕·테두리, aria-invalid, 도움말 자리에 붉은 글자 */
  error?: ReactNode;
  /** 문구 없이 오류 모양만(모달처럼 오류 문구를 다른 자리에 둘 때). 기본은 error 가 있을 때 */
  invalid?: boolean;
  /**
   * lg: 업로드 화면의 분석명(높이 54 · 16px · 라벨 15) — 한 줄 기본
   * md: 모달 안 사유·메모(14.5px · 라벨 14.5) — 여러 줄 기본
   */
  size?: 'lg' | 'md';
  /** 글자 수 표시(n/최대) — maxLength 와 함께 */
  showCount?: boolean;
  maxLength?: number;
  placeholder?: string;
  disabled?: boolean;
  readOnly?: boolean;
  autoFocus?: boolean;
  autoComplete?: string;
  name?: string;
  /** 한 줄일 때 type(기본 text). password 는 값을 가린다 */
  type?: 'text' | 'email' | 'tel' | 'url' | 'number' | 'password';
  inputMode?: 'text' | 'numeric' | 'decimal' | 'tel' | 'email' | 'url' | 'search' | 'none';
  onBlur?: (event: FocusEvent<FieldElement>) => void;
  onFocus?: (event: FocusEvent<FieldElement>) => void;
  onKeyDown?: (event: KeyboardEvent<FieldElement>) => void;
  /** 입력 요소 ref(모달 initialFocus 등) */
  inputRef?: Ref<FieldElement>;
  /** 더 붙일 설명 요소 id */
  describedBy?: string;
  id?: string;
  className?: string;
}

/**
 * 입력칸 — 테두리 없이 회색 채움, 누르면 흰색으로 떠오름(0 0 0 2px 강조색), 오류는 붉은 바탕과 문구.
 * 보드 03 · Main 262(분석명) · 744(모달 사유·메모 textarea).
 */
export function TextField({
  label,
  value,
  onChange,
  multiline = false,
  rows = 3,
  required = false,
  labelNote,
  help,
  error,
  invalid: invalidProp,
  size = multiline ? 'md' : 'lg',
  showCount = false,
  maxLength,
  placeholder,
  disabled,
  readOnly,
  autoFocus,
  autoComplete,
  name,
  type = 'text',
  inputMode,
  onBlur,
  onFocus,
  onKeyDown,
  inputRef,
  describedBy,
  id,
  className,
}: TextFieldProps) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  const helpId = `${fieldId}-help`;
  const invalid = invalidProp ?? !!error;
  const hasError = !!error;
  const hasHelp = hasError || !!help;
  const counted = showCount && maxLength != null;

  const shared = {
    id: fieldId,
    name,
    value,
    onChange,
    onBlur,
    onFocus,
    onKeyDown,
    placeholder,
    maxLength,
    disabled,
    readOnly,
    autoFocus,
    autoComplete,
    required,
    'aria-invalid': invalid || undefined,
    'aria-describedby': cx(hasHelp && helpId, describedBy) || undefined,
  };

  return (
    <div className={cx(styles.wrap, styles[`wrap-${size}`], className)}>
      <label htmlFor={fieldId} className={cx(styles.label, styles[`label-${size}`])}>
        {label}
        {required ? (
          <>
            {' '}
            <span aria-hidden="true" className={styles.req}>
              *
            </span>
            <VisuallyHidden>(필수)</VisuallyHidden>
          </>
        ) : null}
        {labelNote ? (
          <>
            {' '}
            <span className={styles.note}>{labelNote}</span>
          </>
        ) : null}
      </label>
      {multiline ? (
        <textarea {...shared} ref={inputRef as Ref<HTMLTextAreaElement> | undefined} rows={rows} className={cx(styles.field, styles.textarea, invalid && styles.invalid)} />
      ) : (
        <input
          {...shared}
          ref={inputRef as Ref<HTMLInputElement> | undefined}
          type={type}
          inputMode={inputMode}
          className={cx(styles.field, styles[`input-${size}`], invalid && styles.invalid)}
        />
      )}
      {hasHelp || counted ? (
        <div className={styles.below}>
          {hasHelp ? (
            <span id={helpId} className={cx(styles.help, hasError && styles.helpError)}>
              {hasError ? error : help}
            </span>
          ) : null}
          {counted ? (
            <span className={styles.count} aria-hidden="true">
              {value.length}/{maxLength}
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
