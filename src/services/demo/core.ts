/* ==========================================================================
   ④ 데모 서비스 — 동기 코어. 원본: Main.dc.html 1206–1406줄 createDemoService(onChange, onEvent).
   - 로직을 그대로 옮겼다: 메모리 db, seq, fixedNow/at(), 타이머(later), 이력 log(),
     runSample/finishSample, makeAnalysis, 모든 메서드.
   - 화면은 이 코어를 직접 쓰지 않는다. 바깥에는 비동기 겉면(service.ts)만 내보낸다.
   - 지연 시간은 ① CONFIG.sim, 담당자 이름은 CONFIG.user, 브랜드 기본값은 CONFIG.brandName.
   - 원본에 없는 것: remove(aid) — 분석 하나를 지운다(실제 분석의 삭제와 같은 자리). 분석에 딸린 남은 타이머(요청 응답 ·
     샘플 진행 · 다시 분석)를 취소해 지운 뒤에 상태를 바꾸거나 '분석 완료' 이벤트를 내지 않게 한다. 기다리던 Promise 는
     지울 때 끝낸다(분석 요청 = 그 id, 다시 분석 = { ok: false, message: '' } — 화면은 빈 이유면 토스트를 띄우지 않는다).
   ========================================================================== */

import { CONFIG } from '@/config/app';
import {
  analysisStatusView,
  FSTATUS,
  HKIND,
  LSTATUS,
  reviewStatusView,
  riskView,
  RTYPE,
  type ExportFormat,
  type FpReason,
} from '@/display/rules';
import { fmtDT, fmtSize, nowStr, utf8Len } from '@/lib/format';
import { loanDocs, loanResults, mkA, rawSamples, summaryText } from '@/samples';
import type {
  ExportLogState,
  LinkDecision,
  Pending,
  ReclassifyPatch,
  RequestAnalysisInput,
  RetryResult,
  ServiceEvent,
} from '../analysis-service';
import type {
  Analysis,
  AnalysisDoc,
  DocLink,
  ExportFile,
  Finding,
  HistoryEntry,
  ReviewItem,
  UploadFile,
} from '../types';
import { seedReviewActions } from './seed';

/** 원본 uid(p) — 화면에서 쓰는 임시 ID(샘플 파일 등) */
let UIDN = 0;
const uid = (p?: string) => (p || 'id') + '-' + (++UIDN) + '-' + Date.now().toString(36);

/** 이력 한 줄 입력 — id · at 은 자동, actor 기본은 담당자, reason 기본은 빈 문자열 */
type LogInput = Pick<HistoryEntry, 'kind' | 'target' | 'change'> & Partial<Pick<HistoryEntry, 'actor' | 'reason'>>;

/** createQueued 가 쓰는 파일 정보 */
export type QueuedFileInput = Pick<UploadFile, 'name' | 'ext' | 'size'>;

/** 내보내기 탐지 항목 한 줄(열 이름 = 키, 순서 그대로) */
type ExportRow = Record<string, string | number>;

/** 동기 코어 — 프로토타입 svc 객체와 같은 메서드 */
export interface DemoCore {
  dispose(): void;
  /** 고정 시각으로 fn 을 실행한다(샘플 검토 동작용) */
  at(time: string, fn: () => void): void;
  reset(): void;
  clearAll(): void;
  /** 분석 하나를 지운다(남은 타이머 취소). 없으면 false */
  remove(aid: string): boolean;
  /** 내부 배열 그대로 — 복사는 겉면이 한다 */
  list(): Analysis[];
  get(id: string): Analysis | null;
  sampleFiles(): UploadFile[];
  requestAnalysis(input: RequestAnalysisInput): Promise<string>;
  createQueued(name: string, files: QueuedFileInput[]): string;
  retry(aid: string, docId?: string): Promise<RetryResult>;
  setStatus(aid: string, fid: string, status: 'open' | 'confirmed', reason?: string): void;
  confirmMany(aid: string, fids: string[]): void;
  markFalsePositive(aid: string, fid: string, reasonType: FpReason, note: string): void;
  restore(aid: string, fid: string, note?: string): void;
  reclassify(aid: string, fid: string, patch: ReclassifyPatch, reason: string): boolean;
  saveFindingMemo(aid: string, fid: string, text: string): void;
  resolveItem(aid: string, rid: string, note: string): void;
  reopenItem(aid: string, rid: string): void;
  decideLink(aid: string, lid: string, decision: LinkDecision, note: string): void;
  saveMemo(aid: string, text: string): void;
  pending(aid: string): Pending;
  completeReview(aid: string, note: string): void;
  reopenReview(aid: string, reason: string): void;
  logExport(aid: string, file: Pick<ExportFile, 'name' | 'format' | 'size'>, state: ExportLogState): void;
  buildExport(aid: string, format: ExportFormat, brand?: string): ExportFile;
}

export function createDemoCore(onChange: () => void, onEvent?: (event: ServiceEvent) => void): DemoCore {
  const db: { analyses: Analysis[] } = { analyses: [] };
  let seq = 100;
  let fixedNow: string | null = null;
  type Timer = ReturnType<typeof setTimeout>;
  const timers = new Set<Timer>();
  /** 분석별 남은 타이머 — 값은 지울 때 대신 부를 끝내기(기다리던 Promise 를 끝낸다, 없으면 undefined) */
  const owned = new Map<string, Map<Timer, (() => void) | undefined>>();
  const now = () => fixedNow || nowStr();
  /** ms 뒤에 fn. owner 를 주면 그 분석을 지울 때 취소하고 onCancel 을 부른다 */
  const later = (ms: number, fn: () => void, owner?: string, onCancel?: () => void) => {
    const t = setTimeout(() => {
      timers.delete(t);
      if (owner) owned.get(owner)?.delete(t);
      try {
        fn();
      } finally {
        onChange();
      }
    }, ms);
    timers.add(t);
    if (owner) {
      let mine = owned.get(owner);
      if (!mine) owned.set(owner, (mine = new Map()));
      mine.set(t, onCancel);
    }
  };
  /** 모든 타이머 취소(reset · dispose — 원본과 같이 기다리던 Promise 는 끝내지 않는다) */
  const clearTimers = () => {
    timers.forEach(clearTimeout);
    timers.clear();
    owned.clear();
  };
  /** 그 분석의 남은 타이머를 취소하고 기다리던 Promise 를 끝낸다 */
  const cancelOwned = (aid: string) => {
    const mine = owned.get(aid);
    if (!mine) return;
    owned.delete(aid);
    mine.forEach((onCancel, t) => {
      clearTimeout(t);
      timers.delete(t);
      onCancel?.();
    });
  };
  const getA = (id: string): Analysis | null => db.analyses.find((a) => a.id === id) || null;
  const getF = (a: Analysis | null, id: string): Finding | null => (a ? a.findings.find((f) => f.id === id) : null) || null;
  const getI = (a: Analysis | null, id: string): ReviewItem | null => (a ? a.items.find((i) => i.id === id) : null) || null;
  const getL = (a: Analysis | null, id: string): DocLink | null => (a ? a.links.find((l) => l.id === id) : null) || null;
  const log = (a: Analysis, e: LogInput) => {
    a.history.push({ id: 'H' + (++seq), at: now(), actor: CONFIG.user.name, reason: '', ...e });
  };
  const fLabel = (f: Finding) => f.id + ' ' + f.cat;

  function runSample(a: Analysis) {
    const s = CONFIG.sim;
    later(
      s.startMs,
      () => {
        a.status = 'running';
        if (a.docs[0]) a.docs[0].status = 'running';
      },
      a.id,
    );
    a.docs.forEach((d, i) =>
      later(
        s.startMs + s.docMs * (i + 1),
        () => {
          d.status = 'done';
          const nx = a.docs[i + 1];
          if (nx) nx.status = 'running';
          if (i === a.docs.length - 1) finishSample(a);
        },
        a.id,
      ),
    );
  }
  function finishSample(a: Analysis) {
    const r = loanResults();
    Object.assign(a, { status: 'done', risk: 'high', review: 'needed', analyzedAt: now(), findings: r.findings, items: r.items, links: r.links, riskReasons: r.riskReasons, recs: r.recs, limits: r.limits } satisfies Partial<Analysis>);
    log(a, { actor: '시스템', kind: 'ai', target: '분석 건', change: summaryText(a) });
    if (onEvent) onEvent({ type: 'done', id: a.id, name: a.name, items: a.items.length, findings: a.findings.length });
  }
  function makeAnalysis(name: string, files: QueuedFileInput[], isSample: boolean): Analysis {
    const id = 'A' + (++seq);
    const at = now();
    const docs: AnalysisDoc[] = isSample
      ? loanDocs().map((d) => Object.assign(d, { status: 'queued' } as const))
      : files.map((f, i) => ({ id: 'u' + (i + 1), title: f.name, name: f.name, ext: f.ext, size: f.size, status: 'queued', pageCount: null, pages: null, error: '' }));
    const a = mkA({ id, code: 'DG-' + at.slice(0, 10).replace(/-/g, '') + '-' + String(seq).padStart(4, '0'), name, submittedAt: at, status: 'queued', risk: 'unrated', review: 'none', docs, demoQueued: !isSample });
    log(a, { kind: 'request', target: '분석 건', change: '문서 ' + docs.length + '개 분석 요청' });
    db.analyses.unshift(a);
    return a;
  }

  const svc: DemoCore = {
    dispose() {
      clearTimers();
    },
    at(time, fn) {
      fixedNow = time;
      try {
        fn();
      } finally {
        fixedNow = null;
      }
    },
    reset() {
      clearTimers();
      db.analyses = rawSamples();
      seedReviewActions(svc);
    },
    clearAll() {
      db.analyses = [];
    },
    remove(aid) {
      const i = db.analyses.findIndex((a) => a.id === aid);
      if (i < 0) return false;
      db.analyses.splice(i, 1);
      cancelOwned(aid);
      return true;
    },
    list() {
      return db.analyses;
    },
    get: getA,
    sampleFiles() {
      return loanDocs().map((d) => ({ id: uid('s'), name: d.name, ext: d.ext, size: d.size, kind: 'sample', state: 'ready', error: '' }));
    },
    /* 분석 요청 — 실제: 파일 업로드 → 분석 실행 요청 → 분석 ID 반환, 이후 상태 조회로 진행을 확인 */
    requestAnalysis(input) {
      const files = input.files || [];
      const isSample = files.length > 0 && files.every((f) => f.kind === 'sample');
      const a = makeAnalysis(input.name, files, isSample);
      return new Promise((resolve) =>
        later(
          CONFIG.sim.requestMs,
          () => {
            resolve(a.id);
            if (isSample) runSample(a);
          },
          a.id,
          () => resolve(a.id),
        ),
      );
    },
    createQueued(name, files) {
      return makeAnalysis(name, files, false).id;
    },
    /* 다시 분석 — 데모에서는 같은 파일이므로 같은 이유로 다시 실패합니다 */
    retry(aid, docId) {
      const a = getA(aid);
      if (!a || a.retrying) return Promise.resolve({ ok: false, message: '' });
      const targets = a.docs.filter((d) => d.status === 'failed' && (!docId || d.id === docId));
      if (!targets.length) return Promise.resolve({ ok: false, message: '' });
      const prev = a.status;
      const names = targets.map((d) => d.name).join(', ');
      a.retrying = true;
      a.status = 'running';
      targets.forEach((d) => {
        d.status = 'running';
      });
      log(a, { kind: 'retry', target: names, change: '같은 파일로 다시 분석 요청' });
      return new Promise((resolve) =>
        later(
          CONFIG.sim.retryMs,
          () => {
            targets.forEach((d) => {
              d.status = 'failed';
            });
            a.status = prev;
            a.retrying = false;
            log(a, { actor: '시스템', kind: 'retry', target: names, change: '다시 분석했지만 같은 이유로 실패', reason: targets[0].error });
            resolve({ ok: false, message: targets[0].error });
          },
          a.id,
          () => resolve({ ok: false, message: '' }),
        ),
      );
    },
    setStatus(aid, fid, status, reason) {
      const a = getA(aid);
      const f = getF(a, fid);
      if (!a || !f) return;
      const before = FSTATUS[f.status].label;
      f.status = status;
      f.updatedAt = now();
      log(a, { kind: status === 'confirmed' ? 'confirm' : 'unconfirm', target: fLabel(f), change: before + ' → ' + FSTATUS[status].label, reason: reason || '' });
    },
    confirmMany(aid, fids) {
      const a = getA(aid);
      if (!a) return;
      const list = fids.map((id) => getF(a, id)).filter((f): f is Finding => !!f && f.status === 'open');
      list.forEach((f) => {
        f.status = 'confirmed';
        f.updatedAt = now();
      });
      if (list.length) log(a, { kind: 'confirm', target: '탐지 항목 ' + list.length + '건', change: '미확인 → 확인함', reason: list.map((f) => f.id).join(', ') });
    },
    markFalsePositive(aid, fid, reasonType, note) {
      const a = getA(aid);
      const f = getF(a, fid);
      if (!a || !f) return;
      f.status = 'false_positive';
      f.fpType = reasonType;
      f.fpNote = note;
      f.updatedAt = now();
      log(a, { kind: 'fp', target: f.id + ' ' + f.label, change: f.cat + ' → 오탐 (' + reasonType + ')', reason: note });
    },
    restore(aid, fid, note) {
      const a = getA(aid);
      const f = getF(a, fid);
      if (!a || !f) return;
      const changed = f.cat !== f.ai.cat || f.subject !== f.ai.subject || f.exposure !== f.ai.exposure;
      f.status = changed ? 'reclassified' : 'open';
      f.fpType = '';
      f.fpNote = '';
      f.updatedAt = now();
      log(a, { kind: 'restore', target: f.id + ' ' + f.label, change: '오탐 → ' + FSTATUS[f.status].label, reason: note || '' });
    },
    reclassify(aid, fid, patch, reason) {
      const a = getA(aid);
      const f = getF(a, fid);
      if (!a || !f) return false;
      const changes: string[] = [];
      /* 원본: [['cat','정보 종류'], ['subject','정보주체'], ['exposure','노출 상태']] 순서대로 비교 */
      if (patch.cat && patch.cat !== f.cat) {
        changes.push('정보 종류: ' + f.cat + ' → ' + patch.cat);
        f.cat = patch.cat;
      }
      if (patch.subject && patch.subject !== f.subject) {
        changes.push('정보주체: ' + f.subject + ' → ' + patch.subject);
        f.subject = patch.subject;
      }
      if (patch.exposure && patch.exposure !== f.exposure) {
        changes.push('노출 상태: ' + f.exposure + ' → ' + patch.exposure);
        f.exposure = patch.exposure;
      }
      if (!changes.length) return false;
      f.status = 'reclassified';
      f.reclassNote = reason;
      f.updatedAt = now();
      log(a, { kind: 'reclass', target: f.id + ' ' + f.label, change: changes.join(', '), reason });
      return true;
    },
    saveFindingMemo(aid, fid, text) {
      const a = getA(aid);
      const f = getF(a, fid);
      if (!a || !f) return;
      f.memo = text;
      log(a, { kind: 'fmemo', target: fLabel(f), change: text ? '항목 메모 저장' : '항목 메모 삭제', reason: text });
    },
    resolveItem(aid, rid, note) {
      const a = getA(aid);
      const it = getI(a, rid);
      if (!a || !it) return;
      it.resolved = true;
      it.note = note;
      it.resolvedAt = now();
      it.resolvedBy = CONFIG.user.name;
      log(a, { kind: 'resolve', target: it.id + ' ' + RTYPE[it.type].label, change: '미해결 → 해결', reason: note });
    },
    reopenItem(aid, rid) {
      const a = getA(aid);
      const it = getI(a, rid);
      if (!a || !it) return;
      it.resolved = false;
      log(a, { kind: 'reopenItem', target: it.id + ' ' + RTYPE[it.type].label, change: '해결 → 미해결', reason: '' });
    },
    decideLink(aid, lid, decision, note) {
      const a = getA(aid);
      const l = getL(a, lid);
      if (!a || !l) return;
      l.decision = decision;
      l.decisionNote = note;
      l.decidedAt = now();
      l.decidedBy = CONFIG.user.name;
      log(a, { kind: 'link', target: l.id + ' ' + l.title, change: decision === 'linked' ? '같은 사람 · 같은 건으로 판단' : '연결 아님으로 판단', reason: note });
      a.items
        .filter((it) => it.linkId === lid && !it.resolved)
        .forEach((it) => {
          it.resolved = true;
          it.note = '문서 간 연결 판단(' + (decision === 'linked' ? '연결 맞음' : '연결 아님') + ') — ' + note;
          it.resolvedAt = now();
          it.resolvedBy = CONFIG.user.name;
          log(a, { kind: 'resolve', target: it.id + ' ' + RTYPE[it.type].label, change: '미해결 → 해결 (연결 판단 반영)', reason: note });
        });
    },
    saveMemo(aid, text) {
      const a = getA(aid);
      if (!a) return;
      a.memo = text;
      a.memoAt = now();
      log(a, { kind: 'memo', target: '분석 건', change: text ? '검토 메모 저장' : '검토 메모 삭제', reason: text });
    },
    pending(aid) {
      const a = getA(aid);
      const openF = a ? a.findings.filter((f) => f.status === 'open') : [];
      const openI = a ? a.items.filter((i) => !i.resolved) : [];
      const openL = a ? a.links.filter((l) => l.status === 'check' && !l.decision) : [];
      return { openF, openI, openL, any: openF.length + openI.length + openL.length > 0 };
    },
    /* 검토 완료 — 검토 상태와 기록만 바꿉니다. 위험등급 · 최초 탐지 결과는 유지합니다. */
    completeReview(aid, note) {
      const a = getA(aid);
      if (!a) return;
      const p = svc.pending(aid);
      const before = reviewStatusView(a.review).label;
      a.review = 'done';
      a.reviewedAt = now();
      a.reviewer = CONFIG.user.name;
      a.completionNote = note;
      const rest: string[] = [];
      if (p.openF.length) rest.push('미확인 탐지 ' + p.openF.length + '건');
      if (p.openI.length) rest.push('미해결 검토사항 ' + p.openI.length + '건');
      if (p.openL.length) rest.push('확인 필요 연결 ' + p.openL.length + '건');
      log(a, { kind: 'complete', target: '분석 건', change: before + ' → 검토 완료' + (rest.length ? ' (남은 항목: ' + rest.join(', ') + ')' : ''), reason: note });
    },
    reopenReview(aid, reason) {
      const a = getA(aid);
      if (!a) return;
      a.review = 'needed';
      a.reviewedAt = '';
      log(a, { kind: 'reopen', target: '분석 건', change: '검토 완료 → 검토 필요', reason });
    },
    logExport(aid, file, state) {
      const a = getA(aid);
      if (!a) return;
      log(a, { kind: 'export', target: file.name, change: (file.format === 'csv' ? 'CSV' : 'JSON') + ' · ' + fmtSize(file.size) + (state === 'saved' ? ' · 저장 완료' : ' · 다운로드 요청'), reason: '민감한 값 마스킹' });
    },
    /* 내보내기 파일 생성 — 마스킹된 표시값만 담습니다 */
    buildExport(aid, format, brand) {
      const a = getA(aid);
      /* 원본은 없는 분석에서 TypeError 로 끝나고 화면이 try/catch 로 받는다. 같은 뜻의 오류를 분명하게 던진다. */
      if (!a) throw new Error('분석 건을 찾을 수 없습니다: ' + aid);
      const docT = (id: string) => {
        const d = a.docs.find((x) => x.id === id);
        return d ? d.title || d.name : '';
      };
      const rows: ExportRow[] = a.findings.map((f) => ({
        항목ID: f.id, 정보종류: f.cat, 세부항목: f.label, 표시값_마스킹: f.masked, 정보주체: f.subject, 문서: docT(f.docId), 페이지: f.page,
        원문위치: f.anchors.length ? '확인됨' : '위치 확인 필요', 노출상태: f.exposure, 위험등급: riskView(f.risk).label, 판단근거: f.reason, 적용규칙: f.rule,
        확인상태: FSTATUS[f.status].label, 담당자메모: f.memo || '', 최초AI_정보종류: f.ai.cat, 최초AI_정보주체: f.ai.subject, 최초AI_노출상태: f.ai.exposure,
      }));
      const base = (brand || CONFIG.brandName) + '_' + a.code + '_검토결과';
      if (format === 'csv') {
        const cols = rows.length ? Object.keys(rows[0]) : ['항목ID'];
        const esc = (v: string | number | null | undefined) => {
          const s = String(v == null ? '' : v);
          return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
        };
        const lines = [cols.join(',')].concat(rows.map((r) => cols.map((c) => esc(r[c])).join(',')));
        const text = '﻿' + lines.join('\r\n') + '\r\n';
        return { format: 'csv', name: base + '_탐지항목.csv', mime: 'text/csv;charset=utf-8', text, size: utf8Len(text), preview: lines.slice(0, 6).join('\n') };
      }
      const obj = {
        보고서: { 서비스: brand || CONFIG.brandName, 생성시각: fmtDT(now()), 데모데이터: true, 마스킹: '민감한 값은 마스킹된 표시값만 포함' },
        분석: { 분석ID: a.code, 분석명: a.name, 접수일시: fmtDT(a.submittedAt), 분석상태: analysisStatusView(a.status).label, 위험등급: riskView(a.risk).label, 검토상태: reviewStatusView(a.review).label, 검토자: a.reviewer || '', 검토완료시각: a.reviewedAt ? fmtDT(a.reviewedAt) : '' },
        대상문서: a.docs.map((d) => ({ 문서: d.title || d.name, 파일명: d.name, 형식: d.ext, 페이지: d.pageCount || (d.pages ? d.pages.length : null), 처리상태: analysisStatusView(d.status).label, 오류: d.error || '' })),
        주요위험사유: a.riskReasons,
        탐지항목: rows,
        검토사항: a.items.map((i) => ({ ID: i.id, 유형: RTYPE[i.type].label, 내용: i.title, 상태: i.resolved ? '해결' : '미해결', 처리내용: i.note || '' })),
        문서간연결: a.links.map((l) => ({ ID: l.id, 내용: l.title, 판단: l.decision ? (l.decision === 'linked' ? '연결 맞음' : '연결 아님') : LSTATUS[l.status].label, 근거: l.basis })),
        권장조치: a.recs,
        검토메모: a.memo || '',
        검토이력: a.history.map((h) => ({ 시각: fmtDT(h.at), 처리자: h.actor, 구분: HKIND[h.kind] || h.kind, 대상: h.target, 내용: h.change, 사유: h.reason || '' })),
      };
      const text = JSON.stringify(obj, null, 2);
      return { format: 'json', name: base + '.json', mime: 'application/json', text, size: utf8Len(text), preview: text.split('\n').slice(0, 16).join('\n') };
    },
  };
  return svc;
}
