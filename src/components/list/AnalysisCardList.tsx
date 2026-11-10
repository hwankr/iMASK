'use client';

import Link from 'next/link';
import type { CSSProperties } from 'react';
import { AnalysisStatusLabel, Icon, ReviewStatusPill, RiskBadge, cx } from '@/components/ui';
import { analysisRiskView } from '@/display/rules';
import { staggerStyle } from '@/lib/hooks/useStagger';
import { detailHref } from '@/lib/routes';
import { useRouteBase } from '@/services/react';
import { LayersIcon } from './ListIcons';
import type { ListModel } from './listModel';
import styles from './AnalysisCardList.module.css';

/**
 * 휴대폰 카드 목록(768px 미만) — Main 180–200. `<ul>` 카드마다 위험 타일, 이름, '문서 n개 · 접수 일시',
 * 상태 3종(위험등급 · 분석 상태 · 검토 상태)을 라벨과 함께 아래로, 버튼(실패 건 '오류 확인', '상세 보기' — 지금 기준 경로의 상세).
 */
export function AnalysisCardList({
  model,
  replay,
  onShowError,
  onReset,
}: {
  model: ListModel;
  replay: boolean;
  onShowError: (id: string) => void;
  onReset: () => void;
}) {
  const base = useRouteBase();
  return (
    <ul className={styles.list}>
      {model.rows.map((r, i) => {
        const risk = analysisRiskView(r.risk);
        return (
          <li
            key={r.id}
            className={cx(styles.card, replay && styles.cardAlt)}
            style={{ ...staggerStyle(i), '--tile-bg': risk.bg, '--tile-fg': risk.fg } as CSSProperties}
            data-analysis-id={r.id}
          >
            <span aria-hidden="true" className={styles.tile}>
              <LayersIcon className={styles.tileIcon} />
            </span>
            <div className={styles.body}>
              <div className={styles.head}>
                <span className={styles.name}>{r.name}</span>
                <span className={styles.meta}>
                  {r.docs === null ? '' : '문서 ' + r.docs + '개 · '}접수 {r.date}
                </span>
              </div>
              <dl className={styles.facts}>
                <div className={styles.fact}>
                  <dt className={styles.dt}>위험등급</dt>
                  <dd className={styles.dd}>
                    <RiskBadge level={r.risk} size="sm" />
                  </dd>
                </div>
                <div className={styles.fact}>
                  <dt className={styles.dt}>분석 상태</dt>
                  <dd className={cx(styles.dd, styles.statusDd)}>
                    <AnalysisStatusLabel status={r.status} size="sm" />
                    {r.sub ? <span className={styles.sub}>{r.sub}</span> : null}
                  </dd>
                </div>
                <div className={styles.fact}>
                  <dt className={styles.dt}>검토 상태</dt>
                  <dd className={styles.dd}>
                    <ReviewStatusPill status={r.review} size="xs" />
                  </dd>
                </div>
              </dl>
              <div className={styles.actions}>
                {r.failed ? (
                  <button type="button" className={cx(styles.btn, styles.btnError)} data-row-action="error" onClick={() => onShowError(r.id)}>
                    오류 확인
                  </button>
                ) : null}
                <Link href={detailHref(base, r.id)} aria-label={r.name + ' 상세 보기'} className={cx(styles.btn, styles.btnOpen)} data-row-action="open">
                  상세 보기
                  <Icon name="dg-i-chev-right" size={16} strokeWidth={2.2} />
                </Link>
              </div>
            </div>
          </li>
        );
      })}
      {model.noResults ? (
        <li className={styles.noResults}>
          <strong className={styles.noResultsTitle}>조건에 맞는 분석 건이 없습니다</strong>
          <span className={styles.noResultsText}>{model.noResultsText}</span>
          <button type="button" className={styles.noResultsReset} onClick={onReset}>
            검색·필터 초기화
          </button>
        </li>
      ) : null}
    </ul>
  );
}
