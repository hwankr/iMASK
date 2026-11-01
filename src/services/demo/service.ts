/* ==========================================================================
   ④ 데모 서비스 — 비동기 겉면. AnalysisService(실제 API와 같은 계약) + DemoControls.
   - 모든 메서드는 Promise를 돌려준다(subscribe 만 예외).
   - 조회(list · get · pending · sampleFiles · buildExport)는 깊은 복사본(structuredClone)을 돌려준다.
     바깥에서 결과를 고쳐도 서비스 안의 데이터는 바뀌지 않는다.
   - 변경 메서드는 코어를 실행한 뒤 곧바로 끝난다(프로토타입처럼 지연 없음).
     requestAnalysis · retry 만 원래 지연(CONFIG.sim.requestMs · retryMs)을 지킨다.
   - 변경할 때마다 구독자에게 알린다(프로토타입이 동작마다 화면을 다시 그리던 것과 같다).
     코어 타이머가 상태를 바꾸면 listener(), 분석이 끝나면 listener(event) 를 부른다.
   - 처음 만들면 reset() 상태(샘플 6건 + 미리 해 둔 검토 동작)로 시작한다.
   - 코어는 처음 한 번만 만든다(원본 constructor 1491·1493줄: createDemoService + reset).
     reset() · prepare() 는 같은 코어의 reset()(타이머 취소 · 샘플 다시 채움 · seedReviewActions,
     seq 는 이어 씀)을 부른다 — 원본의 '샘플 다시 불러오기'(1661줄) · 상태 바꾸기(1516줄)와 같다.
     그래서 reset 뒤에 새로 만드는 분석 · 이력 ID 는 앞 순번에 이어진다.
   ========================================================================== */

import type { AnalysisService, DemoControls, ServiceEvent } from '../analysis-service';
import { createDemoCore } from './core';
import { applyScenario } from './scenarios';

export type DemoService = AnalysisService & DemoControls & {
  /** 남은 타이머를 지우고 구독을 모두 끊는다 */
  dispose(): void;
};

type Listener = (event?: ServiceEvent) => void;

/** 이 모듈이 만든 데모 서비스 — getDemoControls 의 판별용 */
const demoServices = new WeakSet<object>();

/** 데모 서비스인지 확인한다(이 모듈이 만든 객체만 true) */
export function isDemoService(service: unknown): service is DemoService {
  return typeof service === 'object' && service !== null && demoServices.has(service);
}

export function createDemoService(): DemoService {
  const listeners = new Set<Listener>();

  /** 구독자에게 알린다. 한 구독자의 오류가 다른 구독자 · 서비스 동작을 막지 않게 한다. */
  const emit = (event?: ServiceEvent) => {
    for (const listener of Array.from(listeners)) {
      if (!listeners.has(listener)) continue; // 알리는 도중 해제된 구독
      try {
        if (event) listener({ ...event });
        else listener();
      } catch (err) {
        queueMicrotask(() => {
          throw err;
        });
      }
    }
  };

  /** 서비스가 끝날 때까지 쓰는 코어 하나 — 원본처럼 만들자마자 reset() 한다 */
  const core = createDemoCore(
    () => emit(),
    (event) => emit(event),
  );
  core.reset();

  /** 조회 — 코어 값의 깊은 복사본. 코어가 던진 오류는 거절된 Promise 가 된다. */
  const read = async <T,>(fn: () => T): Promise<T> => structuredClone(fn());
  /** 변경 — 코어 실행 후 구독자에게 알리고 곧바로 끝난다 */
  const write = async <T,>(fn: () => T): Promise<T> => {
    const result = fn();
    emit();
    return result;
  };

  const service: DemoService = {
    /* ---------- AnalysisService ---------- */
    list: () => read(() => core.list()),
    get: (id) => read(() => core.get(id)),
    pending: (id) => read(() => core.pending(id)),
    sampleFiles: () => read(() => core.sampleFiles()),
    /* 분석 건은 곧바로 '대기'로 생기므로 바로 알리고, ID는 requestMs 뒤에 돌려준다 */
    requestAnalysis: async (input) => {
      const idLater = core.requestAnalysis(structuredClone(input));
      emit();
      return idLater;
    },
    /* 문서가 곧바로 '분석 중'으로 바뀌므로 바로 알리고, 결과는 retryMs 뒤에 돌려준다 */
    retry: async (id, docId) => {
      const resultLater = core.retry(id, docId);
      emit();
      return resultLater;
    },
    setStatus: (id, fid, status, reason) => write(() => core.setStatus(id, fid, status, reason)),
    confirmMany: (id, fids) => write(() => core.confirmMany(id, [...fids])),
    markFalsePositive: (id, fid, reasonType, note) => write(() => core.markFalsePositive(id, fid, reasonType, note)),
    restore: (id, fid, note) => write(() => core.restore(id, fid, note)),
    reclassify: (id, fid, patch, reason) => write(() => core.reclassify(id, fid, { ...patch }, reason)),
    saveFindingMemo: (id, fid, text) => write(() => core.saveFindingMemo(id, fid, text)),
    resolveItem: (id, rid, note) => write(() => core.resolveItem(id, rid, note)),
    reopenItem: (id, rid) => write(() => core.reopenItem(id, rid)),
    decideLink: (id, lid, decision, note) => write(() => core.decideLink(id, lid, decision, note)),
    saveMemo: (id, text) => write(() => core.saveMemo(id, text)),
    completeReview: (id, note) => write(() => core.completeReview(id, note)),
    reopenReview: (id, reason) => write(() => core.reopenReview(id, reason)),
    buildExport: (id, format, brand) => read(() => core.buildExport(id, format, brand)),
    logExport: (id, file, state) => write(() => core.logExport(id, file, state)),
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },

    /* ---------- DemoControls ---------- */
    /* 원본 loadSamples(1661줄)의 svc.reset() — 타이머 취소 · 샘플 다시 채움 · seedReviewActions, seq 유지 */
    reset: () => write(() => core.reset()),
    clearAll: () => write(() => core.clearAll()),
    /* 원본 componentDidUpdate(1516줄)의 svc.reset() 뒤 initScenario 데이터 부분 — 돌려주는 ID 는 그때 만든 것 */
    prepare: (state) =>
      write(() => {
        core.reset();
        return applyScenario(core, state);
      }),

    dispose() {
      core.dispose();
      listeners.clear();
    },
  };

  demoServices.add(service);
  return service;
}
