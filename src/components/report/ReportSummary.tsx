import type { CSSProperties } from 'react';
import { CountUp, cx } from '@/components/ui';
import type { ReportView } from './reportModel';
import { ReportSection } from './ReportSection';
import styles from './ReportSummary.module.css';

/**
 * 01 결과 요약 — Main 627–638. 요약 숫자 4개(세어 올라감 — 실제 분석은 3개), 위험등급별 탐지 분포 막대(차례로 자람 dg-grow), 등급 유지 안내.
 * 분포 막대 · 범례는 모델의 dist 조각을 차례대로 그린다 — 데모는 높음 · 보통 · 낮음, 실제 분석은 그 뒤 미평가 조각(1건 이상일 때)도.
 * 조각이 하나도 없으면(탐지 0건) 막대를 그리지 않는다.
 */
export function ReportSummary({ v }: { v: ReportView }) {
  return (
    <ReportSection n={v.sections.summary} title="결과 요약" look="summary">
      <div className={cx(styles.cards, v.cards.length === 3 && styles.cardsThree)}>
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
    </ReportSection>
  );
}
