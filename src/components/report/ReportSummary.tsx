import type { CSSProperties } from 'react';
import { CountUp, cx } from '@/components/ui';
import type { ReportView } from './reportModel';
import { ReportSection } from './ReportSection';
import styles from './ReportSummary.module.css';

/**
 * 01 결과 요약 — Main 627–638. 요약 숫자 4개(세어 올라감 — 실제 분석은 2개), 위험등급별 탐지 분포 막대(차례로 자람 dg-grow), 등급 유지 안내.
 */
export function ReportSummary({ v }: { v: ReportView }) {
  return (
    <ReportSection n={v.sections.summary} title="결과 요약" look="summary">
      <div className={cx(styles.cards, v.cards.length === 2 && styles.cardsTwo)}>
        {v.cards.map((c) => (
          <div key={c.key} className={styles.card}>
            <span className={styles.label}>{c.label}</span>
            <span className={cx(styles.value, c.warn && styles.warn)}>
              <CountUp value={c.num} className={styles.num} />
              <span className={styles.unit}>{c.unit}</span>
              <span className={styles.after}>{c.after}</span>
            </span>
            <span className={styles.sub}>{c.sub}</span>
          </div>
        ))}
      </div>
      {v.dist.length > 0 ? (
        <div className={styles.dist}>
          <div className={styles.distHead}>
            <strong className={styles.distTitle}>위험등급별 탐지 분포</strong>
            <span className={styles.distBasis}>탐지 {v.nFind}건 기준</span>
          </div>
          <div role="img" aria-label={v.distAria} className={styles.bar}>
            {v.dist.map((d) => (
              <span
                key={d.key}
                className={styles.seg}
                style={{ '--seg-n': d.n, '--seg-color': d.color, '--seg-i': d.index } as CSSProperties}
              />
            ))}
          </div>
          <div aria-hidden="true" className={styles.legend}>
            {v.dist.map((d) => (
              <span key={d.key} className={styles.legendItem}>
                <span className={styles.swatch} style={{ '--seg-color': d.color } as CSSProperties} />
                {d.label} <strong className={styles.legendNum}>{d.n}건</strong>
              </span>
            ))}
          </div>
        </div>
      ) : null}
      <p className={styles.keep}>최종 위험등급은 분석 결과를 그대로 유지합니다. 담당자의 검토 완료나 오탐 표시로 위험등급이 자동으로 바뀌지 않습니다.</p>
    </ReportSection>
  );
}
