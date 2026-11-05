'use client';

import Link from 'next/link';
import type { CSSProperties, ReactNode } from 'react';
import { Button, FilterChips, Icon, SegmentedTabs, Spinner, Switch, IndeterminateBar, cx, tabPanelProps } from '@/components/ui';
import { useRouteBase } from '@/services/react';
import type { DetailActions } from './detailActions';
import type { ResultsModel, WaitingModel } from './detailModel';
import type { DetailTab, FindingFilter } from './detailState';
import type { PanelProps } from './DocList';
import { trySampleHref } from './DocViewer';
import { FindingRow } from './FindingRow';
import { LinkCards } from './LinkCards';
import { ReviewItems } from './ReviewItems';
import styles from './ResultsPanel.module.css';
import viewerStyles from './DocViewer.module.css';

/** 결과 탭 · 패널 id 앞부분 */
export const RESULT_TABS_ID = 'dg-res';

/**
 * '모두 가림 · 모두 해제'를 누르면 누른 버튼이 막혀(모두 가림 → 모두 가림 막힘) 포커스가 문서 맨 앞으로 빠진다.
 * 다시 그린 뒤 포커스가 빠졌으면 다른 버튼(slot)으로 옮긴다.
 */
function keepBulkFocus(slot: 'mask-all' | 'mask-none') {
  requestAnimationFrame(() => {
    const cur = document.activeElement;
    if (cur instanceof HTMLButtonElement ? !cur.disabled : cur && cur !== document.body && cur.isConnected) return;
    document.querySelector<HTMLButtonElement>(`[data-slot="${slot}"]:not(:disabled)`)?.focus();
  });
}

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
  /** 마스킹 미리보기 중 — 탐지 항목 하나의 가림을 켜고 끈다 */
  onMaskPick: (fid: string) => void;
  /** 마스킹 미리보기 중 — 보이는 행을 모두 가림(on) · 보임 */
  onMaskPickAll: (fids: readonly string[], on: boolean) => void;
  onItemEvidence: (rid: string, idx: number) => void;
  onOpenLink: (lid: string) => void;
  onLinkDoc: (lid: string, idx: number) => void;
  actions: DetailActions;
  panel?: PanelProps;
  /** 실제 분석 '분석 요약' 탭 내용(데모는 없음) */
  summary?: ReactNode;
}

function Waiting({ w }: { w: WaitingModel }) {
  const base = useRouteBase();
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
        <Link href={trySampleHref(base)} className={cx(viewerStyles.bigBtn, styles.tryBtn)}>
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
 * 실제 분석은 탭이 탐지 항목 · 검토 필요 · (문서 간 연결 — 있을 때만, 읽기 전용) · 분석 요약(summary 를 그린다)이다. 검토 기록을 불러오지 못했으면(rs.readOnly)
 * 검토 동작(해결 · 다시 열기 포함) · 메모 버튼만 막는다.
 * 마스킹 미리보기 중(rs.maskPick)에는 탐지 항목 머리에 '가림 n/m · 모두 가림 · 모두 해제'(보이는 행 기준), 행마다 가림 버튼이 붙는다.
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
  onMaskPick,
  onMaskPickAll,
  onItemEvidence,
  onOpenLink,
  onLinkDoc,
  actions,
  panel,
  summary,
}: ResultsPanelProps) {
  const tabPanel = rs.hasTabs ? tabPanelProps(RESULT_TABS_ID, rs.tab) : null;
  const mp = rs.maskPick;
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
              {mp ? (
                <div role="group" aria-label="가릴 항목" className={cx(styles.stickyRow, styles.maskRow)}>
                  <span aria-live="polite" className={styles.maskText}>
                    <Icon name="dg-i-eye-off" size={15} strokeWidth={2.2} />
                    {mp.text}
                  </span>
                  <span className={styles.maskBtns}>
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={mp.allOn}
                      onClick={() => {
                        onMaskPickAll(mp.ids, true);
                        keepBulkFocus('mask-none');
                      }}
                      data-slot="mask-all"
                    >
                      모두 가림
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={mp.allOff}
                      onClick={() => {
                        onMaskPickAll(mp.ids, false);
                        keepBulkFocus('mask-all');
                      }}
                      data-slot="mask-none"
                    >
                      모두 해제
                    </Button>
                  </span>
                </div>
              ) : null}
            </div>
            {rs.findings.map((f) => (
              <FindingRow
                key={f.id}
                f={f}
                locked={rs.locked}
                readOnly={rs.readOnly}
                onToggle={onToggleFinding}
                onReveal={onRevealFinding}
                actions={actions}
                onMaskPick={mp ? onMaskPick : undefined}
              />
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
            <ReviewItems
              keep={rs.keep}
              nOpen={rs.nOpen}
              nDone={rs.nDone}
              items={rs.items}
              locked={rs.itemsLocked}
              emptyText={rs.itemsEmptyText}
              onEvidence={onItemEvidence}
              onOpenLink={onOpenLink}
              actions={actions}
            />
          </div>
        ) : null}
        {rs.hasTabs && rs.tab === 'links' ? (
          <div key="links" className={styles.fade}>
            <LinkCards links={rs.links} locked={rs.locked} intro={rs.linksIntro} onPickDoc={onLinkDoc} actions={actions} />
          </div>
        ) : null}
        {rs.hasTabs && rs.tab === 'summary' ? (
          <div key="summary" className={styles.fade}>
            {summary}
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
          <Button size="item" variant="secondary" disabled={rs.locked || rs.readOnly} onClick={actions.editMemo} className={styles.memoBtn}>
            {rs.memoBtn}
          </Button>
        </div>
      ) : null}
    </section>
  );
}
