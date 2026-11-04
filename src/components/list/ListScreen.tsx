'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Suspense, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { Icon, useToast } from '@/components/ui';
import { useIsMobile } from '@/lib/hooks/useMediaQuery';
import { useReplayToggle } from '@/lib/hooks/useStagger';
import { detailHref, newAnalysisHref } from '@/lib/routes';
import { useDeleteAnalysis } from '@/components/modals/DeleteAnalysis';
import { useRetryAnalysis } from '@/components/modals/useRetryAnalysis';
import { useAnalyses, useDemoControls, useRouteBase, useService, useServiceMode } from '@/services/react';
import type { Analysis } from '@/services/types';
import { AnalysisCardList } from './AnalysisCardList';
import { AnalysisTable } from './AnalysisTable';
import { ErrorModal } from './ErrorModal';
import { captureListAnchor, findDeleteReturn, takeListFocusOnArrive, type ListAnchor } from './listFocus';
import { ListEmpty } from './ListEmpty';
import { ListSkeleton } from './ListSkeleton';
import { ListToolbar } from './ListToolbar';
import { CLEARED_FILTERS, listModel, replaySignature, type ListFilters } from './listModel';
import { NO_OVERLAY, applyListOverlay, type ListOverlay } from './listOverlay';
import { ResultBar } from './ResultBar';
import { SummaryCards } from './SummaryCards';
import { useLocalListFilters, useUrlListFilters, type SetListFilters } from './useListFilters';
import { useListPolling } from './useListPolling';
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
 * 표의 행 '삭제' → 확인 창(useDeleteAnalysis), '재시도' · 오류 확인 창 '다시 시도' → useRetryAnalysis(요청 한 번 · 결과 토스트).
 * 지운 행 · 다시 분석을 시작한 행은 새 목록이 올 때까지 덧씌워 보인다(listOverlay). 실제 분석 모드에서는 진행 중 행을
 * 3초마다 조회한다(useListPolling — 데모는 하지 않는다). 상세에서 지우고 왔으면 그린 뒤 한 번 검색칸으로 포커스(listFocus).
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
  const live = useServiceMode() === 'api';
  const toast = useToast();
  const mobile = useIsMobile();
  const { data, loading, error, refresh } = useAnalyses();
  const replay = useReplayToggle(replaySignature(filters));
  // 오류 모달 — 연 분석 건과, 여는 순간의 목록 조작 기준점(행 순서 · 걸린 필터; 닫을 때 돌아갈 자리)
  const [errorOpen, setErrorOpen] = useState<{ id: string; anchor: ListAnchor } | null>(null);

  /* 덧씌움 — 지운 행 · 다시 분석을 시작한 행은 그때의 목록 데이터와 함께 둔다(새 목록이 오면 버린다), 요청 중인 다시 분석은 끝날 때까지 */
  const dataRef = useRef(data);
  useLayoutEffect(() => {
    dataRef.current = data;
  });
  const [held, setHeld] = useState<{ data: Analysis[] | undefined; hidden: ReadonlySet<string>; started: ReadonlySet<string> }>(() => ({
    data: undefined,
    hidden: new Set(),
    started: new Set(),
  }));
  const [retrying, setRetrying] = useState<ReadonlySet<string>>(() => new Set());
  const retryLock = useRef(new Set<string>());
  const hold = (kind: 'hidden' | 'started', id: string) =>
    setHeld((prev) => {
      const cur = dataRef.current;
      const keep = prev.data === cur ? prev : { data: cur, hidden: new Set<string>(), started: new Set<string>() };
      return { ...keep, [kind]: new Set([...keep[kind], id]) };
    });
  const overlay: ListOverlay = held.data === data ? { hidden: held.hidden, started: held.started, retrying } : { ...NO_OVERLAY, retrying };
  const shown = data ? applyListOverlay(data, overlay) : undefined;

  const runRetry = useRetryAnalysis();
  const del = useDeleteAnalysis({ onRemoved: (id) => hold('hidden', id) });
  // 진행 중 행 조회 — 실제 분석 모드만
  useListPolling(live, shown, refresh);
  // 상세에서 지우고 왔으면 — 목록을 그린 뒤 한 번 검색칸(없으면 첫 조작)으로 포커스(listFocus)
  const ready = !!shown;
  useEffect(() => {
    if (ready) takeListFocusOnArrive()?.focus({ preventScroll: true });
  }, [ready]);

  if (loading || !data || !shown) {
    if (error && !loading) return <ListFrame failed onRetry={() => void refresh()} />;
    return <ListFrame loading />;
  }

  const m = listModel(shown, filters);
  const openDetail = (id: string) => router.push(detailHref(base, id));
  const resetFilters = () => setFilters(CLEARED_FILTERS);
  /* 다시 분석 — 목록 '재시도' · 오류 확인 창 '다시 시도'. 요청 중에는 그 행을 '재시도 중'(버튼 막힘), 두 번 눌러도 요청은 한 번.
     실제 분석에서 시작하면 오류 확인 창을 닫고 그 행을 새 목록이 올 때까지 '분석 중'으로(목록 진행 중 행 조회가 완료까지 따라간다).
     시작하지 못했으면 창을 그대로 둔다. 데모는 지금 그대로(서비스가 '다시 분석하는 중' → 같은 이유로 실패). */
  const retry = (id: string) => {
    if (retryLock.current.has(id)) return;
    retryLock.current.add(id);
    setRetrying((prev) => new Set([...prev, id]));
    void runRetry(id).then((r) => {
      retryLock.current.delete(id);
      if (r?.started) {
        hold('started', id);
        setErrorOpen((cur) => (cur && cur.id === id ? null : cur));
      }
      setRetrying((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    });
  };
  /* 지우기 — 확인 창(목록 표의 행 '삭제'). 지운 행은 바로 빠지고, 포커스는 이웃 행 · 목록 조작으로, 마지막 행이었으면
     본문의 첫 조작(빈 목록의 '새 분석')으로(listFocus findDeleteReturn) */
  const askDelete = (id: string) => {
    const anchor = captureListAnchor(id, filters);
    del.ask({ id, returnFocus: () => findDeleteReturn(anchor) });
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
  const errorAnalysis = errorOpen ? shown.find((a) => a.id === errorOpen.id) ?? null : null;

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
            <ListToolbar all={shown} filters={filters} setFilters={setFilters} mobile={mobile} />
            <ResultBar model={m} onReset={resetFilters} />
            {mobile ? (
              <AnalysisCardList model={m} replay={replay} onShowError={showError} onReset={resetFilters} />
            ) : (
              <AnalysisTable model={m} replay={replay} onOpen={openDetail} onShowError={showError} onRetry={retry} onDelete={askDelete} onReset={resetFilters} />
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
      {del.modal}
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
