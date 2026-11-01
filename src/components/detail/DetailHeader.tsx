'use client';

import type { CSSProperties } from 'react';
import { listReturnHref, useRememberedListQuery } from '@/components/list/listReturn';
import { AnalysisStatusLabel, Button, IconButton, ReviewStatusPill, RiskBadge, cx } from '@/components/ui';
import type { DetailActions } from './detailActions';
import type { HeaderModel } from './detailModel';
import styles from './DetailHeader.module.css';

export interface DetailHeaderProps {
  model: HeaderModel;
  analysisId: string;
  mobile: boolean;
  actions: Pick<DetailActions, 'completeReview' | 'reopenReview'>;
}

/**
 * 상세 머리글(Main 331–357) — 목록으로, 제목 · 문서 수 · 쪽 수 · 접수 · 분석 ID(고정폭),
 * '결과 보고서'(→ /analyses/[id]/report), '검토 완료' · '검토 다시 열기'(T7 모달), 상태 3종, 탐지 확인 진행.
 * 휴대폰에서는 보고서 버튼이 아이콘 버튼이 되고 라벨이 짧아진다.
 */
export function DetailHeader({ model: m, analysisId, mobile, actions }: DetailHeaderProps) {
  const reportHref = `/analyses/${encodeURIComponent(analysisId)}/report`;
  // 목록으로 = 프로토타입 goList: 마지막 목록의 검색·필터·정렬을 그대로 둔다
  const listHref = listReturnHref(useRememberedListQuery());
  const pct = { '--pct': m.progress.pct + '%' } as CSSProperties;
  return (
    <div className={styles.head}>
      <div className={styles.top}>
        <IconButton href={listHref} label="문서 분석 목록으로 돌아가기" icon="dg-i-arrow-left" size={40} iconSize={20} strokeWidth={2.2} className={styles.back} />
        <div className={styles.titles}>
          <h1 className={styles.title}>{m.name}</h1>
          <div className={styles.meta}>
            문서 {m.docCount}개 · {m.pageTotalText} · 접수 {m.date}
            {mobile ? null : (
              <>
                {' · 분석 ID '}
                <span className={styles.code}>{m.code}</span>
              </>
            )}
          </div>
        </div>
        <div className={styles.actions}>
          {mobile ? (
            m.noReport ? (
              <IconButton label="결과 보고서" icon="dg-i-report" size={40} variant="secondary" iconSize={18} strokeWidth={2} disabled title={m.reportTitle} />
            ) : (
              <IconButton href={reportHref} label="결과 보고서" icon="dg-i-report" size={40} variant="secondary" iconSize={18} strokeWidth={2} />
            )
          ) : m.noReport ? (
            <Button variant="secondary" icon="dg-i-report" iconStrokeWidth={2} disabled title={m.reportTitle} className={cx(styles.btn, styles.report)}>
              결과 보고서
            </Button>
          ) : (
            <Button href={reportHref} variant="secondary" icon="dg-i-report" iconStrokeWidth={2} title={m.reportTitle} className={cx(styles.btn, styles.report)}>
              결과 보고서
            </Button>
          )}
          {m.showComplete ? (
            <Button
              variant="primary"
              raised
              icon="dg-i-check-badge"
              iconStrokeWidth={2.1}
              disabled={m.noComplete}
              title={m.completeTitle}
              onClick={actions.completeReview}
              className={cx(styles.btn, styles.state, styles.complete)}
              data-slot="review-state"
            >
              검토 완료
            </Button>
          ) : null}
          {m.showReopen ? (
            <Button variant="secondary" icon="dg-i-history" iconStrokeWidth={2} onClick={actions.reopenReview} className={cx(styles.btn, styles.state)} data-slot="review-state">
              {mobile ? '다시 열기' : '검토 다시 열기'}
            </Button>
          ) : null}
        </div>
      </div>
      <div className={styles.stats}>
        <dl className={styles.dl}>
          <div className={styles.stat}>
            <dt className={styles.dt}>{mobile ? '위험' : '위험등급'}</dt>
            <dd className={styles.dd}>
              <RiskBadge level={m.risk} size="sm" strong />
            </dd>
          </div>
          <div className={styles.stat}>
            <dt className={styles.dt}>{mobile ? '분석' : '분석 상태'}</dt>
            <dd className={styles.dd}>
              <AnalysisStatusLabel status={m.status} size="md" strong />
            </dd>
          </div>
          <div className={styles.stat}>
            <dt className={styles.dt}>{mobile ? '검토' : '검토 상태'}</dt>
            <dd className={styles.dd}>
              <ReviewStatusPill status={m.review} size="sm" strong />
            </dd>
          </div>
        </dl>
        {m.hasProgress ? (
          <div className={styles.progress}>
            <div
              role="progressbar"
              aria-label="탐지 항목 확인 진행"
              aria-valuemin={0}
              aria-valuemax={m.progress.total}
              aria-valuenow={m.progress.reviewed}
              className={styles.bar}
            >
              <div className={styles.fill} style={pct} />
            </div>
            <span className={styles.pgText}>
              {mobile ? (
                <>
                  확인 <strong>{m.progress.reviewed}</strong>/{m.progress.total} · 미해결{' '}
                  <strong className={m.progress.open ? styles.warn : undefined}>{m.progress.open}</strong>
                </>
              ) : (
                <>
                  탐지 확인 <strong>{m.progress.reviewed}</strong>/{m.progress.total} · 오탐 {m.progress.fp} · 미해결 검토사항{' '}
                  <strong className={m.progress.open ? styles.warn : undefined}>{m.progress.open}</strong>
                </>
              )}
            </span>
          </div>
        ) : null}
      </div>
    </div>
  );
}
