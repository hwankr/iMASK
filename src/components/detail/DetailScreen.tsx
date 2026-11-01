'use client';

/* ==========================================================================
   상세 검토 화면(/analyses/[id]) — 원본 Main.dc.html 328–602 · detailVM.
   - 데이터는 useAnalysis(id) 로만 받는다. 불러오는 중에는 뼈대, 없는 ID 면 목록(/)으로 돌려보낸다(replace).
   - 서비스 변경 알림이 오면 훅이 다시 불러와 진행(대기 → 분석 중 → 문서별 완료 → 완료)이 그대로 반영된다.
   - 화면 상태는 useDetailUi(리듀서 하나), 검토 동작은 useDetailActions(T7 이 붙임).
   ========================================================================== */

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { Banner, Button, SegmentedTabs, cx, type BannerAction } from '@/components/ui';
import { useAnalysis } from '@/services/react';
import type { Analysis } from '@/services/types';
import { useDetailActions } from './detailActions';
import {
  bannerModel,
  detailFacts,
  docModels,
  failModel,
  headerModel,
  mobileTabs,
  resultsModel,
  showMobileTabs,
  viewerModel,
  VIEWER_COMPACT_MAX,
  type ViewerMetrics,
} from './detailModel';
import type { DetailUiState, MobileTab } from './detailState';
import { DetailHeader } from './DetailHeader';
import { DetailSkeleton } from './DetailSkeleton';
import { DocList, DocRail, type PanelProps } from './DocList';
import { DocViewer, TRY_SAMPLE_HREF } from './DocViewer';
import { FailedBody } from './FailedBody';
import { ResultsPanel } from './ResultsPanel';
import { useDetailUi } from './useDetailUi';
import styles from './DetailScreen.module.css';

/** 휴대폰 화면 전환 탭 · 패널 id 앞부분 */
const MOBILE_TABS_ID = 'dg-mtab';

/** 뷰어를 재기 전(처음 그리는 순간) — 화면 맞춤 배율 1 */
const UNMEASURED: ViewerMetrics = { width: 0, padX: 0, paperW: 0 };

export interface DetailScreenProps {
  /** 분석 건 ID */
  id: string;
  /**
   * /dev/states 용 시작 조건(탭 · 고른 항목 · 검토사항 · 연결 · 문서 · 휴대폰 탭 · 모달).
   * 주면 원본 initScenario 처럼 저절로 고르지 않는다(createDetailState 참고). 연결은 T7.
   */
  initial?: Partial<DetailUiState>;
}

/** 상세 검토 화면 — 데이터를 불러와 화면을 그린다 */
export function DetailScreen({ id, initial }: DetailScreenProps) {
  const router = useRouter();
  const { data, error, refresh } = useAnalysis(id);

  /* 없는 ID — 프로토타입처럼 목록으로(기록을 남기지 않음) */
  useEffect(() => {
    if (data === null) router.replace('/');
  }, [data, router]);

  if (data === undefined) {
    if (error)
      return (
        <div className={styles.screen}>
          <p role="alert" className={styles.error}>
            분석 건을 불러오지 못했습니다.
            <Button size="sm" variant="secondary" onClick={() => void refresh()} className={styles.errorBtn}>
              다시 불러오기
            </Button>
          </p>
        </div>
      );
    return <DetailSkeleton />;
  }
  if (data === null) return <DetailSkeleton label="분석 건을 찾을 수 없어 목록으로 돌아갑니다." />;
  return <DetailView analysis={data} initial={initial} />;
}

function DetailView({ analysis: a, initial }: { analysis: Analysis; initial?: Partial<DetailUiState> }) {
  const router = useRouter();
  const ui = useDetailUi(a, initial);
  const actions = useDetailActions(a, ui);
  const s = ui.state;
  const mobile = ui.mobile;

  const x = detailFacts(a, s);
  const head = headerModel(a, x);
  const banner = bannerModel(a, x);
  const fail = failModel(a, x);
  const v = viewerModel(a, s, x, ui.metrics ?? UNMEASURED);
  const rs = resultsModel(a, s, x);
  const docs = docModels(a, x);
  const compact = ui.metrics ? ui.metrics.width < VIEWER_COMPACT_MAX : mobile;

  const showTabs = mobile && showMobileTabs(a);
  const leftFull = (!mobile && ui.leftOpen) || (mobile && s.mTab === 'docs');
  const leftRail = !mobile && !ui.leftOpen;
  const showViewer = !mobile || s.mTab === 'doc';
  const showResults = !mobile || s.mTab === 'results';
  const panel = (tab: MobileTab): PanelProps | undefined =>
    showTabs ? { id: `${MOBILE_TABS_ID}-panel-${tab}`, role: 'tabpanel', 'aria-labelledby': `${MOBILE_TABS_ID}-tab-${tab}` } : undefined;

  const bannerActions: BannerAction[] = (banner?.actions ?? []).map((b) => ({
    label: b.label,
    disabled: b.disabled,
    onClick: () => {
      if (b.key === 'trySample') router.push(TRY_SAMPLE_HREF);
      else if (b.key === 'showFailedDoc') {
        const d = a.docs.find((doc) => doc.status === 'failed');
        if (d) ui.pickDoc(d.id);
      } else if (b.key === 'retryFailed') actions.retry();
      else router.push(`/analyses/${encodeURIComponent(a.id)}/report`);
    },
  }));

  return (
    <div className={styles.screen}>
      <DetailHeader model={head} analysisId={a.id} mobile={mobile} actions={actions} />
      {banner ? <Banner variant={banner.variant} icon={banner.icon} title={banner.title} description={banner.text} actions={bannerActions} /> : null}
      {showTabs ? (
        <div className={styles.mTabs}>
          <SegmentedTabs tabs={mobileTabs(a, x)} value={s.mTab} onChange={ui.setMobileTab} ariaLabel="상세 화면 전환" size="lg" idPrefix={MOBILE_TABS_ID} />
        </div>
      ) : null}
      {fail ? (
        <FailedBody fail={fail} locked={x.locked} memo={rs.memo} memoPreview={rs.memoPreview} memoBtn={rs.memoBtn} actions={actions} />
      ) : (
        <div className={cx(styles.panes, mobile ? styles.single : leftRail && styles.railCols)}>
          {leftFull ? <DocList docs={docs} onPick={ui.pickDoc} onCollapse={mobile ? undefined : ui.toggleLeft} mobile={mobile} panel={panel('docs')} /> : null}
          {leftRail ? <DocRail docs={docs} onPick={ui.pickDoc} onExpand={ui.toggleLeft} /> : null}
          {showViewer ? (
            <DocViewer
              v={v}
              mobile={mobile}
              compact={compact}
              scrollRef={ui.viewerRef}
              onPrev={() => ui.setPage(v.page - 1)}
              onNext={() => ui.setPage(v.page + 1)}
              onZoomOut={() => ui.setZoom(v.zoom - 0.1)}
              onZoomIn={() => ui.setZoom(v.zoom + 0.1)}
              onFit={ui.fit}
              onToggleMask={ui.toggleMask}
              onPickFinding={(fid) => ui.pickFinding(fid, { fromDoc: true })}
              onRetryDoc={(docId) => actions.retry(docId)}
              panel={panel('doc')}
            />
          ) : null}
          {showResults ? (
            <ResultsPanel
              rs={rs}
              mobile={mobile}
              onlyDoc={s.onlyDoc}
              fFilter={s.fFilter}
              scrollRef={ui.resultsRef}
              onTab={ui.setTab}
              onFilter={ui.setFilter}
              onOnlyDoc={ui.setOnlyDoc}
              onClearFilter={ui.clearFilter}
              onToggleFinding={(fid) => ui.pickFinding(fid, { toggle: true })}
              onRevealFinding={(fid) => ui.pickFinding(fid, { reveal: true })}
              onItemEvidence={ui.pickItemEvidence}
              onOpenLink={ui.openLink}
              onLinkDoc={ui.pickLinkDoc}
              actions={actions}
              panel={panel('results')}
            />
          ) : null}
        </div>
      )}
      {/* TODO(T7): 모달 자리 — ui.state.modal 을 그리는 <DetailModals ui={ui} analysis={a} /> 를 여기에 둔다 */}
    </div>
  );
}
