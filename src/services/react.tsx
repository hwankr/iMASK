'use client';

/* ==========================================================================
   ④ 데이터 서비스 — React 연결. 화면은 이 파일의 훅(또는 useService())으로만 데이터를 다룬다.
   - 모드는 주소 기준이다: ServiceProvider 가 usePathname() 으로 모드(modeForPath — `/demo` 아래는 언제나 데모,
     그 밖은 빌드 모드 SERVICE_MODE)와 기준 경로(routeBaseFor — '' 또는 '/demo')를 한 번 계산해 내린다.
     화면은 useServiceMode() · useRouteBase() 로 받는다(SERVICE_MODE 를 직접 읽지 않는다). 모드 · 기준 경로는
     서버에서도 주소로 정해지므로 첫 그림부터 맞다(하이드레이션 불일치 없음).
   - 서비스는 모드별 브라우저 싱글턴(데모 하나 · 실제 분석 하나 — createServiceCache)이다. 그 모드를 처음 쓸 때 만들고
     화면을 옮겨도 그대로 쓰므로 상태가 이어진다(상세에서 검토 완료 → 목록 숫자에 반영, 실제 모드 빌드에서 `/demo` 를
     오가도 데모 상태 유지). 쓰지 않은 모드의 서비스는 만들지 않는다.
   - 서버 렌더와 하이드레이션 첫 렌더에서는 서비스가 없다(null). 데이터 훅은 '불러오는 중'을 돌려준다.
   - 데이터 훅은 서비스 변경 알림(subscribe)이 오면 다시 불러온다. 늦게 도착한 응답이 새 응답을
     덮어쓰지 않고(마지막 요청이 이김), 언마운트 뒤에는 상태를 바꾸지 않는다. 서비스가 바뀌면(`/` ↔ `/demo`)
     새 서비스 값이 올 때까지 '불러오는 중'이다(다른 서비스의 값을 보이지 않는다).
   ========================================================================== */

import { usePathname } from 'next/navigation';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useEffectEvent,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from 'react';
import { routeBaseFor, type RouteBase } from '@/lib/routes';
import type { AnalysisService, DemoControls, LiveExtras, Pending, ServiceEvent } from './analysis-service';
import { createServiceCache, getDemoControls, getLiveExtras } from './index';
import { modeForPath, SERVICE_MODE, type ServiceMode } from './mode';
import type { Analysis } from './types';

/* ---------- 모드별 서비스 하나(브라우저 전용) ---------- */

const browserServices = createServiceCache();

/** 브라우저에서만 그 모드의 서비스를 준다(처음 쓸 때 만든다). 서버에서는 null. */
function getBrowserService(mode: ServiceMode): AnalysisService | null {
  if (typeof window === 'undefined') return null;
  return browserServices.get(mode);
}

const noSubscribe = () => () => {};
const getServerService = () => null;

/** undefined = Provider 밖(설정 실수) / null = 아직 서비스 없음(서버 렌더 · 하이드레이션) */
const ServiceContext = createContext<AnalysisService | null | undefined>(undefined);

/** 주소로 정한 모드 · 기준 경로. undefined = Provider 밖 */
interface RouteInfo {
  mode: ServiceMode;
  base: RouteBase;
}
const RouteContext = createContext<RouteInfo | undefined>(undefined);

export interface ServiceProviderProps {
  children: ReactNode;
  /** 서비스를 직접 넣을 때(테스트 등). 없으면 주소 기준 모드의 브라우저 싱글턴을 쓴다. */
  service?: AnalysisService;
}

/** 앱 전역 데이터 서비스 · 주소 기준 모드. src/app/providers.tsx 가 감싼다. */
export function ServiceProvider({ children, service }: ServiceProviderProps) {
  /* 경로가 없으면(null) 빌드 모드 · 기준 '' */
  const pathname = usePathname();
  const mode = modeForPath(pathname, SERVICE_MODE);
  const base = routeBaseFor(pathname);
  /* 하이드레이션 때는 서버 값(null)을 쓰고, 그 뒤에 브라우저 서비스로 바뀐다(불일치 없음).
     서비스를 직접 넣었으면 브라우저 싱글턴을 만들지 않는다. */
  const getSnapshot = useCallback(() => (service ? null : getBrowserService(mode)), [service, mode]);
  const shared = useSyncExternalStore(noSubscribe, getSnapshot, getServerService);
  const route = useMemo<RouteInfo>(() => ({ mode, base }), [mode, base]);
  return (
    <RouteContext.Provider value={route}>
      <ServiceContext.Provider value={service ?? shared}>{children}</ServiceContext.Provider>
    </RouteContext.Provider>
  );
}

/**
 * 데이터 서비스. 서버 렌더 · 하이드레이션 첫 렌더에서는 null 이다
 * (이벤트 처리기는 브라우저에서만 돌므로 그때는 항상 있다).
 */
export function useService(): AnalysisService | null {
  const service = useContext(ServiceContext);
  if (service === undefined) throw new Error('useService 는 <ServiceProvider> 안에서만 쓸 수 있습니다.');
  return service;
}

function useRouteInfo(hook: string): RouteInfo {
  const route = useContext(RouteContext);
  if (route === undefined) throw new Error(`${hook} 는 <ServiceProvider> 안에서만 쓸 수 있습니다.`);
  return route;
}

/** 지금 화면의 서비스 모드(주소 기준) — `/demo` 아래는 'demo', 그 밖은 빌드 모드. 서버 렌더에서도 같은 값이다. */
export function useServiceMode(): ServiceMode {
  return useRouteInfo('useServiceMode').mode;
}

/** 지금 화면의 기준 경로 — `/demo` 아래는 '/demo', 그 밖은 ''. 이동 주소는 src/lib/routes.ts 함수에 넘겨 만든다. */
export function useRouteBase(): RouteBase {
  return useRouteInfo('useRouteBase').base;
}

/** 데모 전용 조작. 데모 서비스가 아니거나 아직 서비스가 없으면 null. */
export function useDemoControls(): DemoControls | null {
  return getDemoControls(useService());
}

/** 실제 분석 전용 통로(원본 파일 · 단계별 JSON). 실제 분석 서비스가 아니거나 아직 서비스가 없으면 null. */
export function useLiveExtras(): LiveExtras | null {
  return getLiveExtras(useService());
}

/** 서비스 이벤트(분석 완료 등)를 받는다. listener 가 바뀌어도 다시 구독하지 않는다. */
export function useServiceEvent(listener: (event: ServiceEvent) => void): void {
  const service = useService();
  const onEvent = useEffectEvent(listener);
  useEffect(() => {
    if (!service) return;
    return service.subscribe((event) => {
      if (event) onEvent(event);
    });
  }, [service]);
}

/* ---------- 데이터 훅 ---------- */

export interface QueryResult<T> {
  /** 받은 값. 처음 불러오기 전에는 undefined */
  data: T | undefined;
  /** 지금 조건(서비스 · ID)으로 아직 한 번도 받지 못했다 — 뒤에서 다시 불러올 때는 false(전 값을 그대로 보여 준다) */
  loading: boolean;
  /** 마지막 요청이 실패했으면 그 오류 */
  error: unknown;
  /** 다시 불러온다. 끝나면 풀린다. */
  refresh: () => Promise<void>;
}

type Fetcher<T> = (service: AnalysisService) => Promise<T>;

interface Settled<T> {
  service: AnalysisService;
  fetcher: Fetcher<T>;
  data: T | undefined;
  error: unknown;
}

/**
 * 공통 조회 훅. fetcher 는 useCallback 으로 고정해 넘긴다(바뀌면 새 조건으로 다시 불러온다).
 * - 처음 · 조건이 바뀔 때 · 변경 알림이 올 때 불러온다.
 * - 요청마다 번호를 매겨 마지막 요청의 응답만 반영한다.
 * - 효과를 정리하면(언마운트 · Strict Mode 재실행) 구독을 끊고, 그 뒤 도착한 응답은 버린다.
 */
function useServiceQuery<T>(fetcher: Fetcher<T>): QueryResult<T> {
  const service = useService();
  const [settled, setSettled] = useState<Settled<T> | null>(null);
  const ticket = useRef(0);
  const runRef = useRef<(() => Promise<void>) | null>(null);

  useEffect(() => {
    if (!service) return;
    let alive = true;
    const run = (): Promise<void> => {
      const mine = ++ticket.current;
      const apply = (data: T | undefined, error: unknown) => {
        if (!alive || mine !== ticket.current) return; // 언마운트 뒤 · 더 새 요청이 있음
        setSettled((prev) => ({
          service,
          fetcher,
          /* 실패하면 같은 조건의 전 값을 남긴다 */
          data: error === undefined ? data : prev && prev.service === service && prev.fetcher === fetcher ? prev.data : undefined,
          error,
        }));
      };
      return fetcher(service).then(
        (data) => apply(data, undefined),
        (error: unknown) => apply(undefined, error ?? new Error('불러오지 못했습니다.')),
      );
    };
    runRef.current = run;
    void run();
    const unsubscribe = service.subscribe(() => {
      void run();
    });
    return () => {
      alive = false;
      unsubscribe();
      if (runRef.current === run) runRef.current = null;
    };
  }, [service, fetcher]);

  const refresh = useCallback(() => (runRef.current ? runRef.current() : Promise.resolve()), []);

  const current = settled !== null && settled.service === service && settled.fetcher === fetcher ? settled : null;
  return {
    data: current ? current.data : undefined,
    loading: current === null,
    error: current ? current.error : undefined,
    refresh,
  };
}

/** 분석 목록 */
export function useAnalyses(): QueryResult<Analysis[]> {
  const fetcher = useCallback((s: AnalysisService) => s.list(), []);
  return useServiceQuery(fetcher);
}

/** 분석 건 하나. data: undefined = 불러오는 중 / null = 없음 */
export function useAnalysis(id: string): QueryResult<Analysis | null> {
  const fetcher = useCallback((s: AnalysisService) => s.get(id), [id]);
  return useServiceQuery(fetcher);
}

/** 검토 완료 전에 남은 항목 */
export function usePending(id: string): QueryResult<Pending> {
  const fetcher = useCallback((s: AnalysisService) => s.pending(id), [id]);
  return useServiceQuery(fetcher);
}
