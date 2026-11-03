'use client';

import Link from 'next/link';
import type { CSSProperties, MouseEvent } from 'react';
import { AnalysisStatusLabel, Button, Icon, ReviewStatusPill, RiskBadge, VisuallyHidden, cx } from '@/components/ui';
import { riskView } from '@/display/rules';
import { staggerStyle } from '@/lib/hooks/useStagger';
import { detailHref } from '@/lib/routes';
import { useRouteBase } from '@/services/react';
import { LayersIcon, SearchIcon } from './ListIcons';
import type { ListModel, ListRow } from './listModel';
import styles from './AnalysisTable.module.css';

export interface AnalysisTableProps {
  model: ListModel;
  /** 행 등장 움직임 번갈아(dg-in / dg-in-b) — 필터·정렬이 바뀌면 다시 돈다 */
  replay: boolean;
  onOpen: (id: string) => void;
  onShowError: (id: string) => void;
  onRetry: (id: string) => void;
  onReset: () => void;
}

/**
 * 분석 목록 표(768px 이상) — Main 173–176.
 * 열 7개, 행 높이 72px(14 + 위험 타일 44 + 14), 숫자는 고정폭 숫자.
 * 행을 누르면 상세 검토로 가고, 키보드는 행 끝의 '상세 보기'(링크 — 지금 기준 경로의 상세)를 쓴다. 실패 건은 '오류 확인'·'재시도'.
 */
export function AnalysisTable({ model, replay, onOpen, onShowError, onRetry, onReset }: AnalysisTableProps) {
  return (
    <div className={styles.scroll}>
      <table className={styles.table}>
        <caption className={styles.caption}>분석 목록. 행을 누르면 상세 검토 화면으로 이동합니다.</caption>
        <thead>
          <tr>
            <th scope="col" className={cx(styles.th, styles.thFirst)}>
              분석명
            </th>
            <th scope="col" className={cx(styles.th, styles.thNum)}>
              문서 수
            </th>
            <th scope="col" className={styles.th}>
              위험등급
            </th>
            <th scope="col" className={styles.th}>
              분석 상태
            </th>
            <th scope="col" className={styles.th}>
              검토 상태
            </th>
            <th scope="col" className={styles.th}>
              접수일시
            </th>
            <th scope="col" className={cx(styles.th, styles.thLast)}>
              <VisuallyHidden>상세 보기와 작업</VisuallyHidden>
            </th>
          </tr>
        </thead>
        <tbody>
          {model.rows.map((r, i) => (
            <TableRow key={r.id} row={r} index={i} replay={replay} onOpen={onOpen} onShowError={onShowError} onRetry={onRetry} />
          ))}
          {model.noResults ? (
            <tr>
              <td colSpan={7} className={styles.noResultsCell}>
                <div className={styles.noResults}>
                  <span className={styles.noResultsIcon}>
                    <SearchIcon className={styles.noResultsGlyph} />
                  </span>
                  <strong className={styles.noResultsTitle}>조건에 맞는 분석 건이 없습니다</strong>
                  <span className={styles.noResultsText}>{model.noResultsText}</span>
                  <Button variant="secondary" className={styles.noResultsReset} onClick={onReset}>
                    검색·필터 초기화
                  </Button>
                </div>
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

function TableRow({
  row: r,
  index,
  replay,
  onOpen,
  onShowError,
  onRetry,
}: {
  row: ListRow;
  index: number;
  replay: boolean;
  onOpen: (id: string) => void;
  onShowError: (id: string) => void;
  onRetry: (id: string) => void;
}) {
  const risk = riskView(r.risk);
  const base = useRouteBase();
  const stop = (fn: () => void) => (e: MouseEvent) => {
    e.stopPropagation();
    fn();
  };
  return (
    <tr
      className={cx(styles.row, replay && styles.rowAlt)}
      style={{ ...staggerStyle(index), '--tile-bg': risk.bg, '--tile-fg': risk.fg } as CSSProperties}
      onClick={() => onOpen(r.id)}
      data-analysis-id={r.id}
    >
      <td className={cx(styles.td, styles.tdFirst)}>
        <div className={styles.nameCell}>
          <span aria-hidden="true" className={styles.tile}>
            <LayersIcon className={styles.tileIcon} />
          </span>
          <div className={styles.nameText}>
            <span className={styles.name}>{r.name}</span>
            <span className={styles.files}>{r.files}</span>
          </div>
        </div>
      </td>
      <td className={cx(styles.td, styles.docs)}>{r.docs}개</td>
      <td className={styles.td}>
        <RiskBadge level={r.risk} size="sm" />
      </td>
      <td className={styles.td}>
        <div className={styles.status}>
          <AnalysisStatusLabel status={r.status} size="md" />
          {r.sub ? <span className={styles.sub}>{r.sub}</span> : null}
        </div>
      </td>
      <td className={styles.td}>
        <ReviewStatusPill status={r.review} size="sm" />
      </td>
      <td className={cx(styles.td, styles.date)}>{r.date}</td>
      <td className={cx(styles.td, styles.tdLast)}>
        <div className={styles.actions}>
          {r.failed ? (
            <>
              <button type="button" className={cx(styles.act, styles.actError)} data-row-action="error" onClick={stop(() => onShowError(r.id))}>
                오류 확인
              </button>
              <button type="button" className={cx(styles.act, styles.actRetry)} onClick={stop(() => onRetry(r.id))} disabled={r.retrying}>
                <Icon name="dg-i-refresh" size={14} strokeWidth={2.2} />
                {r.retrying ? '재시도 중…' : '재시도'}
              </button>
            </>
          ) : null}
          <Link
            href={detailHref(base, r.id)}
            aria-label={r.name + ' 상세 보기'}
            className={cx(styles.act, styles.actOpen)}
            data-row-action="open"
            onClick={(e) => e.stopPropagation()}
          >
            상세 보기
            <Icon name="dg-i-chev-right" size={16} strokeWidth={2.2} />
          </Link>
        </div>
      </td>
    </tr>
  );
}
