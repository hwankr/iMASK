'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Suspense, useState, type ReactNode } from 'react';
import { Icon, useToast } from '@/components/ui';
import { useIsMobile } from '@/lib/hooks/useMediaQuery';
import { useReplayToggle } from '@/lib/hooks/useStagger';
import { detailHref, newAnalysisHref } from '@/lib/routes';
import { useAnalyses, useDemoControls, useRouteBase, useService } from '@/services/react';
import { AnalysisCardList } from './AnalysisCardList';
import { AnalysisTable } from './AnalysisTable';
import { ErrorModal } from './ErrorModal';
import { captureListAnchor, type ListAnchor } from './listFocus';
import { ListEmpty } from './ListEmpty';
import { ListSkeleton } from './ListSkeleton';
import { ListToolbar } from './ListToolbar';
import { CLEARED_FILTERS, listModel, replaySignature, type ListFilters } from './listModel';
import { ResultBar } from './ResultBar';
import { SummaryCards } from './SummaryCards';
import { useLocalListFilters, useUrlListFilters, type SetListFilters } from './useListFilters';
import styles from './ListScreen.module.css';

export interface ListScreenProps {
  /** 처음 필터(검색어 등). URL 과 이을 때는 URL 에 없는 값만 채운다. */
  initialFilters?: Partial<ListFilters>;
  /**
   * 필터를 URL 검색 파라미터(q · risk · status · review · sort)와 잇는다. 기본 true.
   * false 면 컴포넌트 상태로만 다룬다(/dev/states 미리보기).
   */
  syncWithUrl?: boolean;
}

/**
 * / 분석 목록 — 프로토타입 Main.dc.html 114–239(목록 화면), listVM · rowVM(1919–1991).
 * 데이터는 useAnalyses() 로만 받는다. 불러오는 중에는 목록 자리에 뼈대를 보여 준다.
 * /demo 도 같은 화면이다 — 이동 주소(상세 · 새 분석)는 지금 기준 경로(useRouteBase)로 만든다.
 */
export function ListScreen({ initialFilters, syncWithUrl = true }: ListScreenProps) {
  if (!syncWithUrl) return <LocalListScreen initialFilters={initialFilters} />;
  return (
    // useSearchParams 는 Suspense 안에서만 — 정적 렌더에서는 불러오는 중 화면을 그린다
    <Suspense fallback={<ListFrame loading />}>
      <UrlListScreen initialFilters={initialFilters} />
    </Suspense>
  );
}

function UrlListScreen({ initialFilters }: { initialFilters?: Partial<ListFilters> }) {
  const [filters, setFilters] = useUrlListFilters(initialFilters);
  return <ListView filters={filters} setFilters={setFilters} />;
}

function LocalListScreen({ initialFilters }: { initialFilters?: Partial<ListFilters> }) {
  const [filters, setFilters] = useLocalListFilters(initialFilters);
  return <ListView filters={filters} setFilters={setFilters} />;
}

function ListView({ filters, setFilters }: { filters: ListFilters; setFilters: SetListFilters }) {
  const router = useRouter();
  const base = useRouteBase();
  const service = useService();
  const demo = useDemoControls();
  const toast = useToast();
  const mobile = useIsMobile();
  const { data, loading, error, refresh } = useAnalyses();
  const replay = useReplayToggle(replaySignature(filters));
  // 오류 모달 — 연 분석 건과, 여는 순간의 목록 조작 기준점(행 순서 · 걸린 필터; 닫을 때 돌아갈 자리)
  const [errorOpen, setErrorOpen] = useState<{ id: string; anchor: ListAnchor } | null>(null);

  if (loading || !data) {
    if (error && !loading) return <ListFrame failed onRetry={() => void refresh()} />;
    return <ListFrame loading />;
  }

  const m = listModel(data, filters);
  const openDetail = (id: string) => router.push(detailHref(base, id));
  const resetFilters = () => setFilters(CLEARED_FILTERS);
  const retry = (id: string) => {
    if (!service) return;
    void service.retry(id).then((r) => {
      if (r && r.message) toast('다시 분석했지만 실패했습니다 · ' + r.message, { kind: 'error' });
    });
  };
  // 데모 버튼 '샘플 분석 건 둘러보기' — 프로토타입 loadSamples(1661)
  const loadSamples = async () => {
    if (!demo || !service) return;
    await demo.reset();
    setFilters(CLEARED_FILTERS);
    const list = await service.list();
    toast('샘플 분석 건 ' + list.length + '개를 불러왔습니다.');
  };

  const showError = (id: string) => setErrorOpen({ id, anchor: captureListAnchor(id, filters) });
  const errorAnalysis = errorOpen ? data.find((a) => a.id === errorOpen.id) ?? null : null;

  return (
    <ListFrame lead={m.hasData ? { lead: m.heroLead, strong: m.heroStrong, tail: m.heroTail } : undefined}>
      {m.hasData ? (
        <>
          <SummaryCards
            cards={m.cards}
            onPick={(id) => {
              if (id === 'total') resetFilters();
              else if (id === 'high') setFilters({ risk: filters.risk === 'high' ? 'all' : 'high' });
              else setFilters({ review: filters.review === 'needed' ? 'all' : 'needed' });
            }}
          />
          <section aria-label="분석 목록" className={styles.listSection}>
            <ListToolbar all={data} filters={filters} setFilters={setFilters} mobile={mobile} />
            <ResultBar model={m} onReset={resetFilters} />
            {mobile ? (
              <AnalysisCardList model={m} replay={replay} onShowError={showError} onReset={resetFilters} />
            ) : (
              <AnalysisTable model={m} replay={replay} onOpen={openDetail} onShowError={showError} onRetry={retry} onReset={resetFilters} />
            )}
          </section>
        </>
      ) : (
        <ListEmpty onLoadSamples={demo ? () => void loadSamples() : undefined} />
      )}
      <ErrorModal
        analysis={errorAnalysis}
        anchor={errorOpen?.anchor}
        onClose={() => setErrorOpen(null)}
        onOpenDetail={(id) => {
          setErrorOpen(null);
          openDetail(id);
        }}
        onRetry={retry}
      />
    </ListFrame>
  );
}

/** 머리말 요약 한 줄(분석 건이 있을 때만) — 앞 · 굵게 · 뒤 */
type Lead = { lead: string; strong: string; tail: string };

/**
 * 화면 틀 — 머리말(제목 · 요약 한 줄 · 새 분석) + 본문. 불러오는 중이면 요약 자리와 목록 자리에 뼈대.
 * 분석 건이 없으면 요약 줄을 그리지 않는다(실무자 화면이라 원본의 고정 안내 문구는 뺐다).
 */
function ListFrame({
  lead,
  loading = false,
  failed = false,
  onRetry,
  children,
}: {
  lead?: Lead;
  loading?: boolean;
  failed?: boolean;
  onRetry?: () => void;
  children?: ReactNode;
}) {
  const base = useRouteBase();
  return (
    <div className={styles.screen}>
      <div className={styles.page}>
        <div className={styles.hero}>
          <div className={styles.heroText}>
            <h1 className={styles.title}>문서 분석</h1>
            {lead ? (
              <p className={styles.lead}>
                {lead.lead}
                {lead.strong ? <strong>{lead.strong}</strong> : null}
                {lead.tail}
              </p>
            ) : loading ? (
              <span className={styles.leadSkeleton} aria-hidden="true" />
            ) : null}
          </div>
          <Link href={newAnalysisHref(base)} className={styles.newButton}>
            <Icon name="dg-i-plus" size={18} strokeWidth={2.4} />새 분석
          </Link>
        </div>
        {loading ? <ListSkeleton /> : null}
        {failed ? (
          <div role="alert" className={styles.failed}>
            <span>분석 목록을 불러오지 못했습니다.</span>
            <button type="button" className={styles.failedRetry} onClick={onRetry}>
              <Icon name="dg-i-refresh" size={14} strokeWidth={2.2} />
              다시 불러오기
            </button>
          </div>
        ) : null}
        {children}
      </div>
    </div>
  );
}
