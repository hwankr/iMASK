import { Icon, cx } from '@/components/ui';
import type { ListModel } from './listModel';
import styles from './ResultBar.module.css';

/**
 * 결과 줄 — 기준 표시('전체 기준' · '검색 결과 기준'), 결과 문구, 걸렀을 때 부가 문구와 '검색·필터 초기화'. Main 165–172.
 * 결과 부분은 aria-live(polite)로 바뀔 때 읽힌다.
 */
export function ResultBar({ model, onReset }: { model: ListModel; onReset: () => void }) {
  return (
    <div className={styles.bar}>
      <div aria-live="polite" className={styles.result}>
        <span className={cx(styles.basis, model.filtered && styles.basisOn)}>{model.basis}</span>
        <span className={styles.text}>{model.resultText}</span>
        {model.filtered ? <span className={styles.sub}>{model.resultSub}</span> : null}
      </div>
      {model.filtered ? (
        <button type="button" className={styles.reset} onClick={onReset}>
          <Icon name="dg-i-x" size={14} strokeWidth={2.2} />
          검색·필터 초기화
        </button>
      ) : null}
    </div>
  );
}
