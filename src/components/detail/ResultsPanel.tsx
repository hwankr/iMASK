'use client';

import Link from 'next/link';
import type { CSSProperties } from 'react';
import { Button, FilterChips, Icon, SegmentedTabs, Spinner, Switch, IndeterminateBar, cx, tabPanelProps } from '@/components/ui';
import type { DetailActions } from './detailActions';
import type { ResultsModel, WaitingModel } from './detailModel';
import type { DetailTab, FindingFilter } from './detailState';
import type { PanelProps } from './DocList';
import { TRY_SAMPLE_HREF } from './DocViewer';
import { FindingRow } from './FindingRow';
import { LinkCards } from './LinkCards';
import { ReviewItems } from './ReviewItems';
import styles from './ResultsPanel.module.css';
import viewerStyles from './DocViewer.module.css';

/** 결과 탭 · 패널 id 앞부분 */
export const RESULT_TABS_ID = 'dg-res';

export interface ResultsPanelProps {
  rs: ResultsModel;
  mobile: boolean;
  onlyDoc: boolean;
  fFilter: FindingFilter;
  scrollRef: (el: HTMLElement | null) => void;
  onTab: (tab: DetailTab) => void;
  onFilter: (f: FindingFilter) => void;
  onOnlyDoc: (on: boolean) => void;
  onClearFilter: () => void;
  onToggleFinding: (fid: string) => void;
  onRevealFinding: (fid: string) => void;
  onItemEvidence: (rid: string, idx: number) => void;
  onOpenLink: (lid: string) => void;
  onLinkDoc: (lid: string, idx: number) => void;
  actions: DetailActions;
  panel?: PanelProps;
}

function Waiting({ w }: { w: WaitingModel }) {
  return (
    <div className={styles.wait}>
      <div className={styles.waitHead}>
        <span className={cx(styles.waitIcon, w.queued && styles.waitQueued)}>{w.queued ? <Icon name="dg-i-clock" size={24} /> : <Spinner size={22} />}</span>
        <div className={styles.waitTitles}>
          <span className={styles.waitTitle}>{w.title}</span>
          <span className={styles.waitSub}>{w.sub}</span>
        </div>
      </div>
      {w.queued ? null : <IndeterminateBar variant="track" size="md" tone="run" />}
      <p className={styles.waitText}>{w.text}</p>
      <ol className={styles.waitDocs}>
        {w.docs.map((d, i) => (
          <li key={i} className={styles.waitDoc} style={{ '--st-fg': d.status.fg } as CSSProperties}>
            <span className={styles.waitDocIcon}>{d.status.spin ? <Spinner size={15} /> : <Icon name={d.status.icon} size={17} strokeWidth={2.1} />}</span>
            <span className={styles.waitDocTitle}>{d.title}</span>
            <span className={styles.waitDocState}>{d.status.label}</span>
          </li>
        ))}
      </ol>
      <p className={styles.waitHint}>{w.hint}</p>
      {w.demo ? (
        <Link href={TRY_SAMPLE_HREF} className={cx(viewerStyles.bigBtn, styles.tryBtn)}>
          <Icon name="dg-i-play" size={17} strokeWidth={2.2} />
          샘플 문서로 체험하기
        </Link>
      ) : null}
    </div>
  );
}

/**
 * 결과 패널(Main 457–600) — 탭 3개(탐지 항목 · 검토 필요 · 문서 간 연결 + 건수), 탐지 항목(필터 칩 · 현재 문서만 보기 ·
 * 펼치는 행), 검토 필요, 문서 간 연결, 결과를 기다리는 동안의 안내, 검토 메모(편집은 T7).
 */
export function ResultsPanel({
  rs,
  mobile,
  onlyDoc,
  fFilter,
  scrollRef,
  onTab,
  onFilter,
  onOnlyDoc,
  onClearFilter,
  onToggleFinding,
  onRevealFinding,
  onItemEvidence,
  onOpenLink,
  onLinkDoc,
  actions,
  panel,
}: ResultsPanelProps) {
  const tabPanel = rs.hasTabs ? tabPanelProps(RESULT_TABS_ID, rs.tab) : null;
  return (
    /* data-focus-region · data-focus-home: 동작 뒤 행이 목록에서 빠지면 포커스를 이어 줄 구역과 기준 자리(focusRescue) */
    <section aria-label="탐지 결과와 검토 항목" className={cx(styles.panel, mobile && styles.mobile)} data-focus-region="results" {...panel}>
      {rs.hasTabs ? (
        <div className={styles.tabs} data-focus-home="2">
          <SegmentedTabs tabs={rs.tabs} value={rs.tab} onChange={onTab} ariaLabel="결과 구분" idPrefix={RESULT_TABS_ID} />
        </div>
      ) : null}
      <div ref={scrollRef} className={styles.scroll} {...(tabPanel ?? {})}>
        {rs.hasTabs && rs.tab === 'findings' ? (
          <div key="findings" className={styles.fade}>
            <div data-sticky="1" data-focus-home="1" className={styles.sticky}>
              <FilterChips chips={rs.chips} value={fFilter} onChange={onFilter} ariaLabel="탐지 항목 필터" />
              <div className={styles.stickyRow}>
                <Switch checked={onlyDoc} onChange={(on) => onOnlyDoc(on)} label="현재 문서만 보기" />
                <span className={styles.shown}>{rs.shownText}</span>
              </div>
            </div>
            {rs.findings.map((f) => (
              <FindingRow key={f.id} f={f} locked={rs.locked} onToggle={onToggleFinding} onReveal={onRevealFinding} actions={actions} />
            ))}
            {rs.findings.length === 0 ? (
              <div className={styles.noItems}>
                <span>조건에 맞는 탐지 항목이 없습니다.</span>
                <button type="button" className={styles.clearBtn} onClick={onClearFilter}>
                  필터 해제
                </button>
              </div>
            ) : null}
          </div>
        ) : null}
        {rs.hasTabs && rs.tab === 'review' ? (
          <div key="review" className={styles.fade}>
            <ReviewItems keep={rs.keep} nOpen={rs.nOpen} nDone={rs.nDone} items={rs.items} locked={rs.locked} onEvidence={onItemEvidence} onOpenLink={onOpenLink} actions={actions} />
          </div>
        ) : null}
        {rs.hasTabs && rs.tab === 'links' ? (
          <div key="links" className={styles.fade}>
            <LinkCards links={rs.links} locked={rs.locked} onPickDoc={onLinkDoc} actions={actions} />
          </div>
        ) : null}
        {rs.waiting ? <Waiting w={rs.waiting} /> : null}
      </div>
      {rs.hasTabs ? (
        <div className={styles.memo}>
          <span aria-hidden="true" className={styles.memoIcon}>
            <Icon name="dg-i-memo" size={18} />
          </span>
          <div className={styles.memoTexts}>
            <div className={styles.memoTitle}>검토 메모</div>
            <div className={cx(styles.memoPreview, rs.memo && styles.memoHas)}>{rs.memoPreview}</div>
          </div>
          <Button size="item" variant="secondary" disabled={rs.locked} onClick={actions.editMemo} className={styles.memoBtn}>
            {rs.memoBtn}
          </Button>
        </div>
      ) : null}
    </section>
  );
}
