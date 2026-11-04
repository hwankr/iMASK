'use client';

/* ==========================================================================
   상세 검토 화면(/analyses/[id]) — 원본 Main.dc.html 328–602 · detailVM.
   - 데이터는 useAnalysis(id) 로만 받는다. 불러오는 중에는 뼈대, 없는 ID 면 목록(/ — `/demo` 아래면 /demo)으로 돌려보낸다(replace).
   - 머리글 '삭제' → 확인 창(useDeleteAnalysis). 지우면 토스트와 함께 그 기준 경로의 마지막 목록(listReturnHref)으로 간다 —
     지우는 동안 · 떠나는 동안 데이터가 '없음'이 되어도 '찾을 수 없음' 이동을 하지 않고 뼈대를 그린다.
   - 이동 주소는 지금 기준 경로(useRouteBase)로 만든다(src/lib/routes.ts) — `/demo` 아래에서는 `/demo` 밖으로 나가지 않는다.
   - 서비스 변경 알림이 오면 훅이 다시 불러와 진행(대기 → 분석 중 → 문서별 완료 → 완료)이 그대로 반영된다.
   - 화면 상태는 useDetailUi(리듀서 하나), 검토 동작은 useDetailActions, 모달은 ReviewModal.
   - DetailView 는 실제 분석 상세(LiveDetailScreen — 완료된 공통 계약 결과)도 그린다(live 옵션):
     원문 자리에 원본 파일(useLiveFile — 한 번 받음), 결과 패널에 '분석 요약' 탭(useLiveStages).
     검토 동작은 데모와 같은 useDetailActions(실제 분석 서비스가 서버에 저장한다). 검토 기록을 불러오지 못한
     실제 분석(readOnly)만 READ_ONLY_ACTIONS 로 아무것도 하지 않는다(버튼도 막혀 있다).
   ========================================================================== */

import { useRouter } from 'next/navigation';
import { useEffect, type ReactNode } from 'react';
import { Banner, Button, SegmentedTabs, cx, type BannerAction } from '@/components/ui';
import { requestListFocusOnArrive } from '@/components/list/listFocus';
import { listReturnHref, useRememberedListQuery } from '@/components/list/listReturn';
import { LiveSummaryTab } from '@/components/live/LiveSummaryTab';
import { useDeleteAnalysis } from '@/components/modals/DeleteAnalysis';
import { useLiveStages } from '@/components/live/liveHooks';
import { listHref, reportHref } from '@/lib/routes';
import type { LiveExtras } from '@/services';
import { useAnalysis, useRouteBase } from '@/services/react';
import type { Analysis } from '@/services/types';
import { ReviewModal } from '@/components/modals/ReviewModal';
import { READ_ONLY_ACTIONS, useDetailActions } from './detailActions';
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
import { DocViewer, trySampleHref } from './DocViewer';
import { FailedBody } from './FailedBody';
import { useLiveFile } from './liveFile';
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
   * 주면 원본 initScenario 처럼 저절로 고르지 않는다(createDetailState 참고). /dev/states 의 상세 상태가 넘긴다.
   */
  initial?: Partial<DetailUiState>;
}

/** 상세 검토 화면 — 데이터를 불러와 화면을 그린다 */
export function DetailScreen({ id, initial }: DetailScreenProps) {
  const router = useRouter();
  const base = useRouteBase();
  const { data, error, refresh } = useAnalysis(id);
  // 지운 뒤 — 그 기준 경로의 마지막 목록(검색 · 필터 그대로)으로
  const listQuery = useRememberedListQuery(base);
  const del = useDeleteAnalysis({
    onRemoved: (_id, outcome) => {
      if (outcome !== 'deleted') return;
      requestListFocusOnArrive(); // 화면 이동은 포커스를 옮기지 않는다 — 목록이 그려지면 검색칸으로
      router.push(listReturnHref(base, listQuery));
    },
  });
  // 지우는 중 · 지운 뒤 떠나는 중 — 그동안은 '찾을 수 없음'으로 목록에 보내지 않는다(번쩍임 · 두 번 이동 없이)
  const leaving = del.leaving === id;

  /* 없는 ID — 프로토타입처럼 그 기준의 목록으로(기록을 남기지 않음) */
  useEffect(() => {
    if (data === null && !leaving) router.replace(listHref(base));
  }, [data, router, base, leaving]);

  let body: ReactNode;
  if (data === undefined) {
    body = error ? (
      <div className={styles.screen}>
        <p role="alert" className={styles.error}>
          분석 건을 불러오지 못했습니다.
          <Button size="sm" variant="secondary" onClick={() => void refresh()} className={styles.errorBtn}>
            다시 불러오기
          </Button>
        </p>
      </div>
    ) : (
      <DetailSkeleton />
    );
  } else if (data === null) {
    body = leaving ? <DetailSkeleton /> : <DetailSkeleton label="분석 건을 찾을 수 없어 목록으로 돌아갑니다." />;
  } else {
    body = <DetailView analysis={data} initial={initial} onDelete={() => del.ask({ id: data.id })} />;
  }
  return (
    <>
      {body}
      {del.modal}
    </>
  );
}

/** 실제 분석 상세로 그릴 때(LiveDetailScreen) */
export interface DetailLiveOptions {
  /** 실제 분석 전용 통로(원본 파일 · 단계별 JSON) — useLiveExtras() */
  extras: LiveExtras | null;
  /** 최신 상태를 다시 받지 못했을 때의 문구(있으면 띠로 보인다) */
  notice?: string;
}

export interface DetailViewProps {
  analysis: Analysis;
  initial?: Partial<DetailUiState>;
  /** 실제 분석 — 없으면 데모 */
  live?: DetailLiveOptions;
  /** 머리글 '삭제' — 확인 창을 연다(화면이 useDeleteAnalysis 로 처리). 없으면 버튼이 없다 */
  onDelete?: () => void;
}

/** 상세 검토 화면 본체 — 데모 분석, 또는 실제 분석(live) */
export function DetailView({ analysis: a, initial, live, onDelete }: DetailViewProps) {
  const router = useRouter();
  const base = useRouteBase();
  const ui = useDetailUi(a, initial);
  const detailActions = useDetailActions(a, ui);
  const liveId = live ? a.id : null;
  const liveExtras = live ? live.extras : null;
  const liveFile = useLiveFile(liveId, liveExtras);
  const liveStages = useLiveStages(liveId, liveExtras, a.raw?.result ?? null);
  const s = ui.state;
  const mobile = ui.mobile;

  const x = detailFacts(a, s);
  // 검토 기록을 불러오지 못한 실제 분석 — 검토 동작은 아무것도 하지 않는다(버튼도 막혀 있다)
  const actions = x.readOnly ? READ_ONLY_ACTIONS : detailActions;
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
    /* 다시 분석하는 동안 띠의 버튼이 사라졌다가 다시 생긴다 — 끝난 뒤 포커스를 돌려줄 자리(focusRescue) */
    dataSlot: b.key === 'retryFailed' ? 'retry-failed' : undefined,
    onClick: () => {
      if (b.key === 'trySample') router.push(trySampleHref(base));
      else if (b.key === 'showFailedDoc') {
        const d = a.docs.find((doc) => doc.status === 'failed');
        if (d) ui.pickDoc(d.id);
      } else if (b.key === 'retryFailed') actions.retry();
      else router.push(reportHref(base, a.id));
    },
  }));

  return (
    <div className={styles.screen}>
      <DetailHeader model={head} analysisId={a.id} mobile={mobile} actions={actions} onDelete={onDelete} />
      {banner ? <Banner variant={banner.variant} icon={banner.icon} title={banner.title} description={banner.text} actions={bannerActions} /> : null}
      {live && live.notice ? <Banner variant="partial" icon="dg-i-info" title="최신 상태를 확인하지 못했습니다." description={live.notice} /> : null}
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
              live={live ? { file: liveFile.state, paperW: ui.metrics?.paperW ?? 0, onRetryFile: liveFile.retry, onPageReady: ui.recenter } : undefined}
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
              summary={live ? <LiveSummaryTab analysis={a} stages={liveStages.state} onLoadStages={liveStages.load} /> : undefined}
            />
          ) : null}
        </div>
      )}
      {/* 모달 자리 — 오탐 표시 · 분류 수정 · 메모 · 해결 · 연결 판단 · 검토 완료 · 다시 열기(원본 703–755) */}
      <ReviewModal analysis={a} ui={ui} />
    </div>
  );
}
