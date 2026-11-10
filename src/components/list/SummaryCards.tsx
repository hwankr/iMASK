'use client';

import type { CSSProperties } from 'react';
import { CountUp, Icon, cx } from '@/components/ui';
import type { SummaryCard, SummaryCardId } from './listModel';
import styles from './SummaryCards.module.css';

/**
 * 요약 카드 3개(전체 분석 · 상 등급 · 검토 대기) — Main 127–139.
 * 누르면 목록을 걸러 보고(aria-pressed — 눌린 상태는 선택 표시와 낭독기 글 aria-label), 숫자는 세어 올라간다(값이 바뀌면 이어서 변함).
 */
export function SummaryCards({ cards, onPick }: { cards: readonly SummaryCard[]; onPick: (id: SummaryCardId) => void }) {
  return (
    <section aria-labelledby="dg-sum-title" className={styles.summary}>
      <div className={styles.head}>
        <h2 id="dg-sum-title" className={styles.title}>
          요약
        </h2>
      </div>
      <div className={styles.band}>
        {cards.map((c) => (
          <button
            key={c.id}
            type="button"
            aria-pressed={c.on}
            aria-label={c.aria}
            onClick={() => onPick(c.id)}
            className={cx(styles.card, c.on && styles.on)}
            style={{ '--card-icon': c.iconColor, '--card-fg': c.color } as CSSProperties}
          >
            <span className={styles.label}>
              <span className={styles.icon}>
                <Icon name={c.icon} size={17} strokeWidth={2} />
              </span>
              {c.label}
            </span>
            <span className={styles.value}>
              <CountUp value={c.n} speed="fast" className={styles.num} />
              <span className={styles.unit}>건</span>
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
