'use client';

import { useId, type ReactNode } from 'react';
import { cx } from './cx';
import styles from './RadioList.module.css';
import hidden from './VisuallyHidden.module.css';

export interface RadioOption<V extends string = string> {
  value: V;
  label: string;
  /** 설명 — 있으면 제목 + 설명 두 줄 카드(내보내기 형식 선택, Main 734) */
  description?: ReactNode;
}

export interface RadioListProps<V extends string> {
  /** fieldset 의 legend(예: '오탐으로 판단한 이유') */
  legend: ReactNode;
  options: readonly RadioOption<V>[];
  /** 아직 고르지 않았으면 null */
  value: V | null;
  onChange: (value: V) => void;
  /** 라디오 묶음 이름 — 없으면 자동 */
  name?: string;
  disabled?: boolean;
  /** legend 를 화면에서 숨긴다(위에 보이는 제목이 따로 있을 때). 화면 낭독기에는 읽힌다. */
  legendHidden?: boolean;
  className?: string;
}

/**
 * 선택 목록 — 모달 안 사유·형식 선택. 진짜 `<input type="radio">` + `<label>`, `fieldset`/`legend`.
 * 보드 03 '선택 목록' · Main 715(오탐 사유) · 734(내보내기 형식). 화살표 키 이동은 브라우저 기본 동작.
 */
export function RadioList<V extends string>({ legend, options, value, onChange, name, disabled = false, legendHidden = false, className }: RadioListProps<V>) {
  const autoName = useId();
  const group = name ?? autoName;
  const rich = options.some((o) => o.description != null);
  return (
    <fieldset className={cx(styles.fieldset, rich && styles.fieldsetRich, className)} disabled={disabled}>
      <legend className={legendHidden ? hidden.hidden : styles.legend}>{legend}</legend>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <label key={o.value} className={cx(styles.option, rich && styles.rich, on && styles.on)}>
            <input type="radio" name={group} value={o.value} checked={on} onChange={() => onChange(o.value)} className={styles.radio} />
            {rich ? (
              <span className={styles.text}>
                <strong className={styles.title}>{o.label}</strong>
                {o.description ? <span className={styles.desc}>{o.description}</span> : null}
              </span>
            ) : (
              o.label
            )}
          </label>
        );
      })}
    </fieldset>
  );
}
