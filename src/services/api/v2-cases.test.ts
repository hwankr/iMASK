/* 백엔드가 만든 설정 60 결과(fixtures/v2-cases.json — tests/test_v2_fixture_sync.py 가 백엔드 출력과 바이트까지 같은지 지킨다. 값은 모두 가상 값) →
   toAnalysis → 판정 칸 · 위험 배지 · 탐지 항목(등급 · 표 칸) · 검토사항(새 종류) · 연결 · 요약 줄 · 서류 이름 · 보고서 · 내보내기.
   판정 7갈래: A 상 · E 중 · L·M 형식 · N·U 불일치 · P·S 누락 · R 대상외 · T 중복. 옛 키 5개 모양은 그대로인지도 본다. */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { CONFIG } from '@/config/app';
import { RTYPE, docTypeName, type ReviewItemType } from '@/display/rules';
import { READ_ONLY_ACTIONS } from '@/components/detail/detailActions';
import { detailFacts, findingModel, itemModel, linkModel, resultsModel, viewerModel, type ViewerMetrics } from '@/components/detail/detailModel';
import {
  SCROLL_TOP,
  createDetailState,
  focusAnchors,
  maskPicked,
  planOpenLink,
  planPickFinding,
  planPickItem,
  planPickItemEvidence,
  toggledMaskPick,
  type DetailUiState,
} from '@/components/detail/detailState';
import { FindingRow } from '@/components/detail/FindingRow';
import { LinkCards } from '@/components/detail/LinkCards';
import { maskPlan } from '@/components/detail/maskPdf';
import { ReviewItems } from '@/components/detail/ReviewItems';
import { LiveSummaryTab } from '@/components/live/LiveSummaryTab';
import { decisionView, finalFlowRows, summaryRows } from '@/components/live/liveModel';
import { completeModel, reviewModalModel } from '@/components/modals/reviewModalModel';
import { reportView, type ReportView } from '@/components/report/reportModel';
import { ReportHead } from '@/components/report/ReportHead';
import { ReportHistory } from '@/components/report/ReportHistory';
import { ReportMemo, ReportReasons, ReportRecs, ReportRemaining } from '@/components/report/ReportLists';
import { ReportSummary } from '@/components/report/ReportSummary';
import { ReportDocTable, ReportFindings } from '@/components/report/ReportTables';
import { CSV_COLUMNS, buildExportFile } from '@/services/export-file';
import { rawValueMasker } from '@/services/raw-mask';
import { reportSafeAnalysis } from '@/services/report-safe';
import type { Analysis, Finding, RawDecisionV2 } from '@/services/types';
import { createApiClient } from './client';
import { MAX_DECISION_ITEMS, MAX_V2_DECISION_ITEMS, readDecision } from './contract';
import { readAnalysisList, toAnalysis } from './mapping';
import { createApiService } from './service';
import { analysisOut, contractResult, fakeFetch, finalFlowRun, json, v2Case, type V2Case } from './testing';

type Obj = Record<string, unknown>;
interface RawFinding {
  id: string;
  field: string;
  label: string;
  risk: string;
  value: string;
  masked: string;
  page: number;
  risk_reason: string | null;
}
interface RawItem {
  id: string;
  number: string;
  type: ReviewItemType;
  title: string;
  desc: string;
  next: string;
  link_id: string | null;
  evidence: { label: string; page: number; finding_ids: string[]; finding_id: string | null }[];
}
interface RawLink {
  id: string;
  number: string;
  status: 'confirmed' | 'check';
  state: string;
  title: string;
  label: string;
  docs: { document_index: number; page: number; fields: string; finding_ids: string[] }[];
  basis: string[];
  missing: string;
  check: string;
}
interface RawV2Decision {
  risk_level: string;
  document_types: string[];
  high_risk_items: string[];
  medium_risk_items: string[];
  low_risk_items: string[];
  review_reasons: string[];
  recommended_action: string;
  reason: string;
}

const ALL: readonly V2Case[] = ['A', 'E', 'L', 'M', 'N', 'P', 'R', 'S', 'T', 'U'];
const M: ViewerMetrics = { width: 760 + 48 + 6, padX: 24, paperW: 760 };

const review = (patch: Obj = {}): Obj => ({ status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, items: {}, history: [], version: 0, ...patch });
const liveOf = (result: Obj, rv: Obj = review()): Analysis => toAnalysis(analysisOut({ status: 'done', result, upstage_job_id: 'job_test', upstage_status: 'completed', review: rv }));
const live = (key: V2Case): Analysis => liveOf(v2Case(key));
const stateOf = (a: Analysis, patch: Partial<DetailUiState> = {}): DetailUiState => ({ ...createDetailState(a).state, ...patch });
const results = (a: Analysis, s: DetailUiState = stateOf(a)) => resultsModel(a, s, detailFacts(a, s));
const viewer = (a: Analysis, patch: Partial<DetailUiState> = {}) => {
  const s = stateOf(a, patch);
  return viewerModel(a, s, detailFacts(a, s), M);
};

const rawDecision = (key: V2Case) => v2Case(key).decision as unknown as RawV2Decision;
const rawFindings = (r: Obj) => r.findings as RawFinding[];
const rawItems = (r: Obj) => r.items as RawItem[];
const rawLinks = (r: Obj) => r.links as RawLink[];
const tableCells = (a: Analysis) => a.findings.filter((f) => (f.live?.id ?? '').includes('['));

const summaryHtml = (a: Analysis) => renderToStaticMarkup(createElement(LiveSummaryTab, { analysis: a, stages: { status: 'idle' }, onLoadStages: () => {} }));
/** dl 줄 [data-row, dt, dd] 차례로 */
function rowsOf(markup: string): [string, string, string][] {
  const out: [string, string, string][] = [];
  const re = /<div class="[^"]*" data-row="([^"]+)"><dt class="[^"]*">([^<]*)<\/dt><dd class="[^"]*">([^<]*)<\/dd><\/div>/g;
  for (let m = re.exec(markup); m; m = re.exec(markup)) out.push([m[1], m[2], m[3]]);
  return out;
}
const HTML_ENTITIES: Record<string, string> = { '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#x27;': "'" };
const unescapeHtml = (s: string) => s.replace(/&(?:amp|lt|gt|quot|#x27);/g, (e) => HTML_ENTITIES[e]);

const SECTIONS = [ReportSummary, ReportReasons, ReportDocTable, ReportFindings, ReportRemaining, ReportRecs, ReportMemo, ReportHistory];
const renderReport = (v: ReportView) =>
  [renderToStaticMarkup(createElement(ReportHead, { v, generatedAt: '2026.11.04 09:00' })), ...SECTIONS.map((C) => renderToStaticMarkup(createElement(C, { v })))].join('\n');
const file = (a: Analysis, format: 'csv' | 'json') => buildExportFile(reportSafeAnalysis(a), format, { brand: CONFIG.brandName, generatedAt: '2026-11-04 15:07', live: true });

/** raw-mask.ts 의 예외 칸 — 시험은 구현을 가져다 쓰지 않고 전체 꼴을 따로 맞춘다 */
const SELF_CELL = /^(?:[^[\]]+\[\d+\]\.)?(?:중_관계|중_대리인_관계|중_법정대리인_관계|중_가족관계)(?:#\d+)?$/;

/* 원문 검사 — 일치한 자리로 판단한다.
   후보(rawValues): 탐지 항목 value 전부. 어떤 칸 표시값에 들어 있어도 후보에서 빼지 않는다. 뺀 것은 둘 — 한 글자 값(raw-mask.ts 의 바꾸기 대상이 아니다)과
   정해진 관계 칸(risk_source workflow)의 값이 정확히 '본인' 인 항목(raw-mask.ts 의 유일한 예외 — 같은 값이 다른 칸에 있으면 그 항목 때문에 후보다).
   글 단위: 마크업은 같은 글 흐름의 이어진 글 하나 · 속성 값 하나(markupUnits — 인라인 태그를 넘어 합치고 블록 요소 · 표 칸 · br 등 그 밖의 태그에서 끊어, 칸 경계에서 우연히 생기는 겹침은 막고
   인라인 자식으로 갈린 값은 잡는다), CSV 는 칸 하나(csvUnits), JSON 은 값 · 키 하나, 안전한 사본은 문자열 값 하나(valueUnits).
   판단(hits): 글 단위 안의 탐지 항목 표시값(masked 전체 글자) 안에 통째로 든 일치만 허용하고, 표시값 밖의 일치는 실패다. 표시값이 앞 · 뒤 어디를 보여 주든, 인라인 자식으로 갈려 있어도 이 자리뿐이다.
   표시값을 지운 뒤 찾는 것과 같은 자리를 허용하되 실제로 지우지 않고 자리로 비교한다 — 지우면 표시값에 걸친 일치를 놓치고 지운 양쪽이 붙어 없던 일치가 생긴다.
   3자 이하 숫자만인 값은 앞뒤가 숫자가 아닌 자리만 일치로 센다. 경계는 글자 노드 안에서 본다 — 옆 노드의 숫자가 실제로 붙어 보이는지 마크업만으로는 모른다. */
function rawValues(a: Analysis): string[] {
  const out = new Set<string>();
  for (const f of a.findings) {
    const v = f.live?.value ?? '';
    if (Array.from(v).length < 2) continue;
    if (v === '본인' && f.live?.riskSource === 'workflow' && SELF_CELL.test(f.live.field)) continue;
    out.add(v);
  }
  return [...out];
}
const masksOf = (a: Analysis): string[] => a.findings.map((f) => f.masked).filter(Boolean);

const isDigit = (c: string | undefined) => c !== undefined && c >= '0' && c <= '9';
/** 글 단위 — 글 하나, 또는 글자 노드가 갈린 이어진 글(cuts = 노드가 갈리는 자리) */
type Unit = string | { text: string; cuts: number[] };
/** 값이 글 단위 하나에서 표시값 밖에 있는지 */
function outsideMask(value: string, unit: Unit, masks: readonly string[]): boolean {
  const text = typeof unit === 'string' ? unit : unit.text;
  const cuts = typeof unit === 'string' ? [] : unit.cuts;
  const short = /^\d{1,3}$/.test(value);
  const digitBeside = (i: number, edge: number) => isDigit(text[i]) && !cuts.includes(edge);
  for (let start = text.indexOf(value); start !== -1; start = text.indexOf(value, start + 1)) {
    const end = start + value.length;
    if (short && (digitBeside(start - 1, start) || digitBeside(end, end))) continue;
    const covered = masks.some((m) => {
      for (let at = text.indexOf(m); at !== -1 && at <= start; at = text.indexOf(m, at + 1)) if (end <= at + m.length) return true;
      return false;
    });
    if (!covered) return true;
  }
  return false;
}
/** 값 꼴 — 실패 메시지에 값을 내지 않는다 */
const shapeOf = (v: string) => `${Array.from(v).length}자${/^\d+$/.test(v) ? '·숫자' : ''}`;
/** 어느 글 단위에서든 표시값 밖에 일치가 있는 값(꼴만) */
const hits = (raws: readonly string[], units: readonly Unit[], masks: readonly string[]) => raws.filter((v) => units.some((u) => outsideMask(v, u, masks))).map(shapeOf);

/** 같은 글 흐름을 잇는 인라인 태그 — 마크업에는 배치가 없어 태그로 정한다. 그 밖(블록 요소 · 표 칸 · br · 버튼 · 그림 · svg 등)은 글 흐름을 끊는다 */
const INLINE_TAGS = new Set(['a', 'abbr', 'b', 'bdi', 'bdo', 'cite', 'code', 'data', 'del', 'dfn', 'em', 'i', 'ins', 'kbd', 'label', 'mark', 'q', 's', 'samp', 'small', 'span', 'strong', 'sub', 'sup', 'time', 'u', 'var', 'wbr']);
/** renderToStaticMarkup 글 → 이어진 글 · 속성 값 하나씩(엔티티를 푼 글). React 는 글과 속성의 < > " 를 엔티티로 적으므로 태그를 이렇게 나눠도 된다 */
function markupUnits(markup: string): Unit[] {
  const units: Unit[] = [];
  let nodes: string[] = [];
  const closeRun = () => {
    if (nodes.length === 0) return;
    const cuts: number[] = [];
    let offset = 0;
    for (const node of nodes.slice(0, -1)) {
      offset += node.length;
      cuts.push(offset);
    }
    units.push({ text: nodes.join(''), cuts });
    nodes = [];
  };
  const tag = /<\/?([^\s/>]+)[^>]*>/g;
  let at = 0;
  for (let m = tag.exec(markup); m; m = tag.exec(markup)) {
    if (m.index > at) nodes.push(unescapeHtml(markup.slice(at, m.index)));
    at = tag.lastIndex;
    if (!INLINE_TAGS.has(m[1].toLowerCase())) closeRun();
    for (const attr of m[0].matchAll(/\s[^\s=]+="([^"]*)"/g)) units.push(unescapeHtml(attr[1]));
  }
  if (at < markup.length) nodes.push(unescapeHtml(markup.slice(at)));
  closeRun();
  return units;
}
const unitText = (unit: Unit) => (typeof unit === 'string' ? unit : unit.text);
/** CSV 글 → 칸 하나씩(BOM · CRLF · 따옴표 규칙을 푼 글) */
function csvUnits(text: string): string[] {
  const units: string[] = [];
  const body = text.replace(/^\uFEFF/, '');
  let cell = '';
  let quoted = false;
  for (let i = 0; i < body.length; i++) {
    const c = body[i];
    if (quoted) {
      if (c !== '"') cell += c;
      else if (body[i + 1] === '"') {
        cell += '"';
        i += 1;
      } else quoted = false;
    } else if (c === '"') quoted = true;
    else if (c === ',' || c === '\n') {
      units.push(cell.replace(/\r$/, ''));
      cell = '';
    } else cell += c;
  }
  if (cell) units.push(cell);
  return units;
}
/** 값 → 문자열 값 하나씩. whole 이면 숫자 값 · 키도 하나씩(내보낸 JSON — 좌표 같은 숫자가 있는 안전한 사본은 문자열만 본다) */
function valueUnits(value: unknown, whole = false, out: string[] = []): string[] {
  if (typeof value === 'string' || (whole && typeof value === 'number')) out.push(String(value));
  else if (value && typeof value === 'object') {
    for (const [key, part] of Object.entries(value)) {
      if (whole && !Array.isArray(value)) out.push(key);
      valueUnits(part, whole, out);
    }
  }
  return out;
}
const fileUnits = (a: Analysis, format: 'csv' | 'json') => (format === 'csv' ? csvUnits(file(a, format).text) : valueUnits(JSON.parse(file(a, format).text), true));

/** 케이스마다 기대 모양(tests/test_v2_fixture_sync.py SHAPES 와 같은 값) */
const WANT: Record<V2Case, { risk: string; badge: string; kinds: ReviewItemType[]; bundle: string; linkRow: string | null; next: string; docs: string[] }> = {
  A: { risk: 'high', badge: '높음', kinds: ['lowconf', 'weaklink', 'lowconf'], bundle: '통과', linkRow: '연결 2 · 확인 필요 1', next: '권장 조치', docs: ['자동이체 신청서', 'FATCA/CRS 본인확인서', '휴면예금 지급신청서', '상속예금 위임장'] },
  E: { risk: 'medium', badge: '보통', kinds: [], bundle: '통과', linkRow: null, next: '권장 조치', docs: ['FATCA/CRS 본인확인서'] },
  L: { risk: 'review', badge: '검토 필요', kinds: ['format', 'lowconf'], bundle: '실패 · 실패 1', linkRow: null, next: '검토 안내', docs: ['소비자피해보상금 지급신청서'] },
  M: { risk: 'review', badge: '검토 필요', kinds: ['format', 'lowconf'], bundle: '실패 · 실패 1', linkRow: null, next: '검토 안내', docs: ['외국인 세대구성원 확인서'] },
  N: { risk: 'review', badge: '검토 필요', kinds: ['lowconf', 'mismatch'], bundle: '실패 · 실패 1', linkRow: null, next: '검토 안내', docs: ['지급보증거래 신청서'] },
  P: { risk: 'review', badge: '검토 필요', kinds: ['unreadable', 'missing'], bundle: '실패 · 실패 2', linkRow: null, next: '검토 안내', docs: ['소비자피해보상금 지급신청서'] },
  R: { risk: 'review', badge: '검토 필요', kinds: ['other'], bundle: '실패 · 실패 1', linkRow: null, next: '검토 안내', docs: ['기타'] },
  S: { risk: 'review', badge: '검토 필요', kinds: ['missing', 'missing'], bundle: '실패 · 실패 2', linkRow: null, next: '검토 안내', docs: ['자동이체 신청서'] },
  T: { risk: 'review', badge: '검토 필요', kinds: ['duplicate', 'lowconf'], bundle: '실패 · 실패 1', linkRow: null, next: '검토 안내', docs: ['소비자피해보상금 지급신청서', '소비자피해보상금 지급신청서 2'] },
  U: { risk: 'review', badge: '검토 필요', kinds: ['mismatch', 'lowconf', 'mismatch'], bundle: '실패 · 실패 3', linkRow: '연결 0 · 확인 필요 2', next: '검토 안내', docs: ['지급보증거래 신청서', '외국인 세대구성원 확인서', '소비자피해보상금 지급신청서'] },
};

describe('판정 8키 읽기(readDecision)', () => {
  it.each(ALL)('%s — high_risk_items 키가 있으면 v2, 값은 응답 그대로(토큰은 받은 글자 그대로)', (key) => {
    const raw = rawDecision(key);
    expect(readDecision(v2Case(key))).toEqual({
      shape: 'v2',
      riskLevel: raw.risk_level,
      documentTypes: raw.document_types,
      highRiskItems: raw.high_risk_items,
      mediumRiskItems: raw.medium_risk_items,
      lowRiskItems: raw.low_risk_items,
      reviewReasons: raw.review_reasons,
      recommendedAction: raw.recommended_action,
      reason: raw.reason,
    });
  });

  it('못 읽은 값은 null · 빈 목록은 [] 로 가른다, high_risk_items 가 null 이어도 키가 있으면 v2', () => {
    const d = readDecision({ decision: { risk_level: null, document_types: 'x', high_risk_items: null, medium_risk_items: [], low_risk_items: [3, '', ' 서식.칸 '], review_reasons: {}, recommended_action: 7, reason: '  ' } });
    expect(d).toEqual({ shape: 'v2', riskLevel: null, documentTypes: null, highRiskItems: null, mediumRiskItems: [], lowRiskItems: ['서식.칸'], reviewReasons: null, recommendedAction: null, reason: null });
  });

  it('글은 한 길(safeText)을 지난다 — 토큰 · 권장 조치 · 판단 근거 모두 mask, 서류 종류 코드는 그대로', () => {
    const mask = (s: string) => s.replace('비밀', '**');
    const d = readDecision({ decision: { risk_level: '상', document_types: ['비밀코드'], high_risk_items: ['서식.비밀'], medium_risk_items: [], low_risk_items: [], review_reasons: ['비밀 사유'], recommended_action: '비밀 조치', reason: '비밀 근거' } }, mask) as RawDecisionV2;
    expect(d.highRiskItems).toEqual(['서식.**']);
    expect(d.reviewReasons).toEqual(['** 사유']);
    expect(d.recommendedAction).toBe('** 조치');
    expect(d.reason).toBe('** 근거');
    expect(d.documentTypes).toEqual(['비밀코드']);
  });

  it(`토큰 목록 한도는 ${MAX_V2_DECISION_ITEMS}개 — 경계까지 그대로, 넘으면 앞 ${MAX_V2_DECISION_ITEMS}개만(옛 ${MAX_DECISION_ITEMS} 한도를 쓰지 않는다)`, () => {
    const tokens = (n: number) => Array.from({ length: n }, (_, i) => `서식.칸${i}`);
    const read = (n: number) =>
      readDecision({ decision: { high_risk_items: tokens(n), medium_risk_items: tokens(n), low_risk_items: tokens(n), review_reasons: tokens(n), document_types: tokens(n) } }) as RawDecisionV2;
    for (const list of [read(500).highRiskItems, read(500).mediumRiskItems, read(500).lowRiskItems, read(500).reviewReasons, read(500).documentTypes]) expect(list).toEqual(tokens(500));
    expect(read(501).lowRiskItems).toEqual(tokens(500));
    expect(read(100000).highRiskItems?.length).toBe(500);
  });

  it('옛 키 5개 모양은 그대로 — shape 키 없음, 목록 한도 50, 정보 종류 · 검토 사유 줄', () => {
    const items = Array.from({ length: 60 }, (_, i) => `값${i}`);
    const d = readDecision({ decision: { risk_level: '상', document_types: ['income_proof'], sensitive_categories: items, review_reasons: items, reason: '근거' } });
    expect(d && Object.keys(d)).toEqual(['riskLevel', 'documentTypes', 'sensitiveCategories', 'reviewReasons', 'reason']);
    expect(d?.sensitiveCategories?.length).toBe(MAX_DECISION_ITEMS);
    expect(d?.reviewReasons?.length).toBe(MAX_DECISION_ITEMS);
    expect(decisionView(d)?.rows.map((r) => r.key)).toEqual(['sensitive_categories', 'review_reasons']);
    // 백엔드가 만든 옛 결과도 같은 모양 — 등급별 항목이 없고 정보 종류 줄이 있다
    const old = decisionView(liveOf(finalFlowRun('C')).raw?.decision);
    expect(old?.groups).toEqual([]);
    expect(old?.rows.map((r) => r.label)).toContain('정보 종류');
    expect(liveOf(finalFlowRun('C')).raw?.decision?.shape).toBeUndefined();
  });
});

describe('위험도 판정 칸 7갈래(decisionView · 분석 요약 탭)', () => {
  it.each([
    ['판정_상', 'A'],
    ['판정_중', 'E'],
    ['판정_형식', 'L'],
    ['판정_불일치', 'N'],
    ['판정_누락', 'P'],
    ['판정_대상외', 'R'],
    ['판정_중복', 'T'],
    ['판정_형식(표 칸)', 'M'],
    ['판정_누락(빈 서식)', 'S'],
    ['판정_불일치(서류 간)', 'U'],
  ] as const)('%s(%s) — 판단 근거는 글로, 값이 있는 줄만, 항목은 등급 · 서류별로(코드 · 밑줄 없음), 가장 높은 등급만 펼침', (_branch, key) => {
    const raw = rawDecision(key);
    const a = live(key);
    const view = decisionView(a.raw?.decision);
    expect(view?.reason).toBe(raw.reason);
    expect(view?.rows).toEqual(raw.review_reasons.length ? [{ key: 'review_reasons', label: '검토 사유', value: raw.review_reasons.join(', ') }] : []);
    const tokens = [
      ['high', raw.high_risk_items],
      ['medium', raw.medium_risk_items],
      ['low', raw.low_risk_items],
    ] as const;
    const present = tokens.filter(([, list]) => list.length);
    expect(view?.groups.map((g) => [g.level, g.docs.flatMap((d) => d.items).length])).toEqual(present.map(([level, list]) => [level, list.length]));
    // 토큰 하나가 빠짐없이 '서류 이름 · 칸 이름' 하나가 된다
    const shown = (token: string) => {
      const dot = token.indexOf('.');
      return `${docTypeName(token.slice(0, dot))} | ${token.slice(dot + 1).replace(/_/g, ' ')}`;
    };
    for (const g of view?.groups ?? []) {
      const list = tokens.find(([level]) => level === g.level)?.[1] ?? [];
      expect(g.docs.flatMap((d) => d.items.map((item) => `${d.name} | ${item}`)).sort()).toEqual(list.map(shown).sort());
    }
    const html = summaryHtml(a);
    expect(rowsOf(html).map(([k]) => k).filter((k) => ['risk', 'risk_level', 'document_types', 'reason'].includes(k))).toEqual([]);
    expect(unescapeHtml(html)).toContain(`>${raw.reason}</p>`);
    const groups = [...html.matchAll(/<details[^>]*data-group="(\w+)"[^>]*>/g)].map((m) => [m[1], / open=""/.test(m[0])]);
    expect(groups).toEqual(present.map(([level], i) => [level, i === 0]));
  });

  it.each(ALL)('%s — recommended_action 은 표에 없고 다음 단계 구역에 한 번만, 판정 본문은 표가 대신한다', (key) => {
    const raw = rawDecision(key);
    const html = summaryHtml(live(key));
    expect(rowsOf(html).map(([k]) => k)).not.toContain('recommended_action');
    expect(html.split(raw.recommended_action).length - 1).toBe(1);
    expect(html).toContain(`id="live-next-title"`);
    expect(html).toMatch(new RegExp(`id="live-next-title"[^>]*>${WANT[key].next}</h3><p[^>]*>${raw.recommended_action}</p>`));
  });

  it('값이 없으면 줄 · 등급을 만들지 않는다(E 상 등급 · 검토 사유 없음, R · S 항목 없음)', () => {
    const view = (key: V2Case) => decisionView(live(key).raw?.decision);
    expect(view('E')?.groups.map((g) => g.level)).toEqual(['medium', 'low']);
    expect(view('E')?.rows).toEqual([]);
    expect(view('R')?.groups).toEqual([]);
    expect(view('S')?.groups).toEqual([]);
  });
});

describe('위험 배지 · 요약 줄 · 서류 이름', () => {
  it.each(ALL)('%s — 분석 건 위험도 · 머리 배지 · 묶음 검증 · 연결 줄 · 서류 이름', (key) => {
    const r = v2Case(key);
    const a = liveOf(r);
    const want = WANT[key];
    expect(a.risk).toBe(want.risk);
    expect(summaryHtml(a)).toContain(`${want.badge}</span>`);
    const rows = finalFlowRows(a.raw?.bundleCheck, a.links);
    expect(rows[0]).toEqual({ key: 'bundle', label: '묶음 검증', value: want.bundle });
    expect(rows[1]?.value ?? null).toBe(want.linkRow);
    expect(a.docs.map((d) => d.title)).toEqual(want.docs);
    // 보고서 · 내보내기도 같은 이름
    expect(reportView(reportSafeAnalysis(a)).docs.map((d) => d.title)).toEqual(want.docs);
    expect(JSON.parse(file(a, 'json').text).대상문서.map((d: Obj) => d.문서)).toEqual(want.docs);
  });

  it('목록 항목의 위험등급 — 결과 요약의 risk_level 그대로(상 · 중 · 검토 필요)', () => {
    const rows = ALL.map((key) => ({ id: 'x-' + key, status: 'done', name: key, documents: [], risk_level: (v2Case(key).summary as Obj).risk_level, review: 'needed' }));
    expect(readAnalysisList({ analyses: rows })?.map((a) => a.risk)).toEqual(ALL.map((key) => WANT[key].risk));
  });

  it("결과 요약의 '분류한 서류'도 이름(코드가 보이지 않는다), 대상 외는 기타", () => {
    const docs = (key: V2Case) => summaryRows(v2Case(key), { createdAt: '', updatedAt: '', jobId: '' }).find((r) => r.key === 'docs')?.value;
    expect(docs('R')).toBe('1개 — 기타');
    expect(docs('A')).toBe('4개 — 자동이체 신청서 · FATCA/CRS 본인확인서 · 휴면예금 지급신청서 · 상속예금 위임장');
    expect(docs('T')).toBe('2개 — 소비자피해보상금 지급신청서 · 소비자피해보상금 지급신청서');
  });
});

describe('탐지 항목 — 등급 · 표 칸', () => {
  const RISK_OF: Record<string, string> = { high: 'high', medium: 'medium', low: 'low' };

  it.each(ALL)('%s — 항목 수 · 등급(접두어)이 계약 그대로, 판단 근거는 비어 있다', (key) => {
    const r = v2Case(key);
    const a = liveOf(r);
    const raw = rawFindings(r);
    expect(a.findings.map((f) => [f.live?.id, f.risk, f.live?.riskSource, f.reason])).toEqual(raw.map((f) => [f.id, RISK_OF[f.risk], 'workflow', '']));
    const chips = Object.fromEntries(results(a).chips.map((c) => [c.value, c.count]));
    expect(chips).toEqual({
      all: raw.length,
      open: raw.length,
      high: raw.filter((f) => f.risk === 'high').length,
      medium: raw.filter((f) => f.risk === 'medium').length,
      low: raw.filter((f) => f.risk === 'low').length,
    });
  });

  it('표 칸 id([ ] .)는 계약 id 그대로 live 에, 화면 번호 · 위치 ID 는 D1-01 꼴(글자 그대로 쓰지 않는다)', () => {
    const r = v2Case('A');
    const a = liveOf(r);
    const cells = tableCells(a);
    expect(cells.length).toBe(35);
    for (const f of cells) {
      expect(f.live?.id).toMatch(/^\d+:.+\[\d+\]\..+$/);
      expect(f.id).toMatch(/^D\d+-\d{2,}$/);
      expect(f.anchors.length).toBeGreaterThan(0);
      for (const an of f.anchors) expect(an).toMatch(/^D\d+-\d{2,}#\d+$/);
      expect(f.label).toMatch(/ \d+행$/);
      const raw = rawFindings(r).find((x) => x.id === f.live?.id);
      expect(f.label).toBe(raw?.label);
      expect(f.live?.field).toBe(raw?.field);
    }
  });

  it('표 칸 행을 고르면 그 서류 · 쪽 · 상자로 간다(처음 상태의 저절로 고름 포함), 목록 행 data-card 는 화면 번호', () => {
    const a = live('A');
    const f = tableCells(a)[0];
    const plan = planPickFinding(stateOf(a), a, f.id, {}, false);
    expect(plan?.patch).toMatchObject({ focus: { kind: 'finding', id: f.id }, docId: f.docId, page: f.page });
    expect(plan?.viewer).toBe(f.anchors[0]);
    expect(focusAnchors(a, { kind: 'finding', id: f.id })).toEqual(f.anchors);
    // 처음 상태 — 미확인 '높음' 첫 항목을 저절로 고른다(옛 분석은 미평가라 고르지 않았다)
    const first = stateOf(a).focus;
    expect(first?.kind).toBe('finding');
    expect(a.findings.find((x) => x.id === first?.id)?.risk).toBe('high');
    const html = renderToStaticMarkup(createElement(FindingRow, { f: findingModel(a, f, { kind: 'finding', id: f.id }), locked: false, onToggle: () => {}, onReveal: () => {}, actions: READ_ONLY_ACTIONS }));
    expect(html).toContain(`data-card="${f.id}"`);
    expect(html).not.toContain(f.live?.id ?? '');
    expect(html).toContain(f.label);
  });

  it('펼친 행 — 판단 근거가 없으면 그 줄을 뺀다(서류 · 쪽은 메타 줄에 있다), 옛 미평가 항목은 안내 글이 있어 줄이 있다', () => {
    const row = (a: Analysis, f: Finding) => findingModel(a, f, { kind: 'finding', id: f.id });
    const render = (a: Analysis, f: Finding) => renderToStaticMarkup(createElement(FindingRow, { f: row(a, f), locked: false, onToggle: () => {}, onReveal: () => {}, actions: READ_ONLY_ACTIONS }));
    const a = live('A');
    expect(row(a, a.findings[0]).hasReason).toBe(false);
    expect(render(a, a.findings[0])).not.toContain('판단 근거');
    expect(render(a, a.findings[0])).not.toContain('원문 위치');
    expect(render(a, a.findings[0])).toContain(row(a, a.findings[0]).where);
    const old = liveOf(contractResult());
    expect(row(old, old.findings[0]).hasReason).toBe(true);
    expect(render(old, old.findings[0])).toContain('판단 근거');
  });

  it('항목별 가림 — 표 칸도 화면 번호로 켜고 끈다, 미리보기 상자 · 가림 계획이 그 값을 따른다', () => {
    const a = live('A');
    const f = tableCells(a)[0];
    expect(maskPicked({}, f)).toBe(true);
    const off = toggledMaskPick({}, f);
    expect(maskPicked(off, f)).toBe(false);
    const box = (pick: DetailUiState['maskPick']) =>
      viewer(a, { mask: true, maskPick: pick, docId: f.docId, page: f.page, focus: null }).live?.boxes.find((b) => b.findingId === f.id);
    expect(box({})).toMatchObject({ masked: true, pressed: true });
    expect(box(off)).toMatchObject({ masked: false, pressed: false });
    const all = maskPlan(a, {}, 7);
    expect(all.picked).toEqual(a.findings.map((x) => x.id));
    expect(all.missed).toEqual([]);
    expect(all.pages[0].some((t) => t.findingId === f.id)).toBe(true);
    const without = maskPlan(a, off, 7);
    expect(without.picked).not.toContain(f.id);
    expect(without.pages.flat().some((t) => t.findingId === f.id)).toBe(false);
  });

  it('검토 동작 — 표 칸의 계약 id 를 그대로 본문에 담아 보낸다, 저장된 값은 그 칸에만 덧씌운다', async () => {
    const ID = 'ab12cd34-0000-4000-8000-000000000000';
    const a = live('A');
    const f = tableCells(a)[0];
    const key = f.live?.id ?? '';
    const out = analysisOut({ id: ID, status: 'done', result: v2Case('A'), review: review() });
    const { fetch, seen } = fakeFetch((req) => json(200, req.method === 'POST' ? { analysis: out, changed: true } : out));
    const service = createApiService({ client: createApiClient({ fetch }), upload: async () => {} });
    await service.setStatus(ID, f.id, 'confirmed');
    await service.saveFindingMemo(ID, f.id, '메모');
    const posts = seen.filter((x) => x.method === 'POST');
    expect(posts.map((p) => p.url)).toEqual([`/api/py/analyses/${ID}/review-actions`, `/api/py/analyses/${ID}/review-actions`]);
    expect(posts[0].body).toMatchObject({ type: 'set_status', finding_id: key, status: 'confirmed' });
    expect(posts[1].body).toMatchObject({ finding_id: key });

    const saved = liveOf(v2Case('A'), review({ findings: { [key]: { status: 'confirmed', memo: '확인함' } } }));
    expect(saved.findings.filter((x) => x.status === 'confirmed').map((x) => x.id)).toEqual([f.id]);
    expect(saved.findings.find((x) => x.id === f.id)?.memo).toBe('확인함');
    expect(saved.findings.find((x) => x.id === f.id)?.risk).toBe(f.risk);
  });

  it('보고서 · 내보내기 — 표 칸 행은 화면 번호 · 이름 · 표시값으로, 계약 id 를 넣지 않는다', () => {
    const a = live('A');
    const f = tableCells(a)[0];
    const v = reportView(reportSafeAnalysis(a));
    expect(v.findings.map((x) => x.id)).toEqual(a.findings.map((x) => x.id));
    expect(v.findings.find((x) => x.id === f.id)?.masked).toBe(f.masked);
    const json = JSON.parse(file(a, 'json').text);
    expect(json.탐지항목.find((x: Obj) => x.항목ID === f.id)).toMatchObject({ 세부항목: f.label, 표시값_마스킹: f.masked, 판단근거: '', 위험등급: '높음' });
    for (const format of ['csv', 'json'] as const) expect(file(a, format).text).not.toContain(f.live?.id ?? '');
  });
});

describe('새 검토 종류 · 항목 모양', () => {
  it.each(ALL)('%s — 종류 · 번호 · 계약 id · 글이 응답 그대로, 라벨 · 아이콘은 표시 규칙', (key) => {
    const r = v2Case(key);
    const a = liveOf(r);
    const raw = rawItems(r);
    expect(a.items.map((i) => [i.id, i.type, i.live?.id, i.title, i.desc, i.next])).toEqual(raw.map((i) => [i.number, i.type, i.id, i.title, i.desc, i.next]));
    expect(a.items.map((i) => i.type)).toEqual(WANT[key].kinds);
    const f = detailFacts(a, stateOf(a));
    for (const i of a.items) {
      const m = itemModel(a, i, null);
      expect(m.type).toBe(RTYPE[i.type].label);
      expect(m.icon).toBe(RTYPE[i.type].icon);
      expect(m.where).toMatch(/ · \d+쪽$/);
    }
    expect(f.openItems).toBe(raw.length);
  });

  it('검토 필요 탭 — 새 종류 행이 그려지고 근거 버튼 · 해결 버튼이 있다, 없는 연결 버튼은 없다', () => {
    const cases: [V2Case, string, boolean][] = [
      ['L', '형식 오류', false],
      ['M', '형식 오류', false],
      ['T', '같은 서식 여러 건', false],
      ['P', '판독 불가', false],
      ['N', '값 불일치', false],
      ['U', '값 불일치', true],
      ['A', '연결 근거 부족', true],
    ];
    for (const [key, label, hasLink] of cases) {
      const a = live(key);
      const rs = results(a, stateOf(a, { tab: 'review' }));
      const html = renderToStaticMarkup(
        createElement(ReviewItems, { keep: rs.keep, nOpen: rs.nOpen, nDone: rs.nDone, items: rs.items, locked: rs.itemsLocked, emptyText: rs.itemsEmptyText, onEvidence: () => {}, onOpenLink: () => {}, actions: READ_ONLY_ACTIONS }),
      );
      expect(html, key).toContain(label);
      expect(html.includes('연결 보기'), key).toBe(hasLink);
      expect(html.split('해결로 표시</button>').length - 1, key).toBe(a.items.length);
      for (const i of a.items) for (const e of i.evidence) expect(html, key).toContain(e.label);
    }
  });

  it('review:<종류> · link_id 없는 mismatch — 연결 보기 없음(N), 검토 동작은 계약 id 로', async () => {
    const a = live('N');
    const it0 = a.items.find((i) => i.live?.id === 'review:mismatch');
    expect(it0).toMatchObject({ type: 'mismatch', evidence: [{ anchors: [] }] });
    expect(it0?.linkId).toBeUndefined();

    const ID = 'ab12cd34-0000-4000-8000-000000000000';
    const out = analysisOut({ id: ID, status: 'done', result: v2Case('N'), review: review() });
    const { fetch, seen } = fakeFetch((req) => json(200, req.method === 'POST' ? { analysis: out, changed: true } : out));
    const service = createApiService({ client: createApiClient({ fetch }), upload: async () => {} });
    await service.resolveItem(ID, it0?.id ?? '', '확인');
    expect(seen.find((x) => x.method === 'POST')?.body).toMatchObject({ type: 'resolve_item', item_id: 'review:mismatch', note: '확인' });
    // 저장된 해결 기록을 그 항목에 덧씌운다
    const saved = liveOf(v2Case('N'), review({ items: { 'review:mismatch': { resolved: true, note: '확인', resolved_at: '2026-11-07T00:00:00+00:00', resolved_by: '담당' } } }));
    expect(saved.items.filter((i) => i.resolved).map((i) => i.live?.id)).toEqual(['review:mismatch']);
  });

  it('format:<i>:<규칙> · 규칙 mismatch(link_id null) · verdict:<i> · duplicate:<코드> — 합성 변형도 깨지지 않는다', () => {
    const r = v2Case('P');
    const base = rawItems(r);
    const extra = (id: string, number: string, type: ReviewItemType): RawItem & Obj => ({ ...base[0], id, number, type, link_id: null, finding_id: null, document_index: 0 });
    r.items = [...base, extra('mismatch:0:서식_칸_일치', 'R-03', 'mismatch'), extra('verdict:0', 'R-04', 'missing'), extra('format:0:서식_칸', 'R-05', 'format'), extra('duplicate:서식', 'R-06', 'duplicate')];
    const a = liveOf(r);
    expect(a.items.map((i) => [i.id, i.type, i.linkId, i.live?.id])).toEqual([
      ['R-01', 'unreadable', undefined, 'unreadable:0:중_신청인_성명'],
      ['R-02', 'missing', undefined, 'missing:0:소비자피해보상금_지급신청서_신청인_성명'],
      ['R-03', 'mismatch', undefined, 'mismatch:0:서식_칸_일치'],
      ['R-04', 'missing', undefined, 'verdict:0'],
      ['R-05', 'format', undefined, 'format:0:서식_칸'],
      ['R-06', 'duplicate', undefined, 'duplicate:서식'],
    ]);
    const v = reportView(reportSafeAnalysis(a));
    expect(v.remaining.map((x) => x.type)).toEqual(['판독 불가', '필수 항목 없음', '값 불일치', '필수 항목 없음', '형식 오류', '같은 서식 여러 건']);
    expect(JSON.parse(file(a, 'json').text).검토사항.map((x: Obj) => x.유형)).toEqual(['판독 불가', '필수 항목 없음', '값 불일치', '필수 항목 없음', '형식 오류', '같은 서식 여러 건']);
  });

  it('검토 모달 · 검토 완료 — 새 종류 라벨로 대상 카드 · 남은 항목 줄을 그린다', () => {
    const a = live('T');
    const m = reviewModalModel(a, { type: 'resolve', rid: 'R-01', note: '', error: '' }, null);
    expect(m?.target).toMatchObject({ id: 'R-01', title: a.items[0].title, meta: '같은 서식 여러 건 · 소비자피해보상금 지급신청서 1쪽' });
    const done = completeModel(a, { openF: [], openI: a.items, openL: [], any: true });
    expect(done.items[0].label).toBe('같은 서식 여러 건 · ' + a.items[0].title);
    const f = reviewModalModel(live('M'), { type: 'fp', fid: tableCells(live('M'))[0].id, reason: '기타', note: '', error: '' }, null);
    expect(f?.target?.id).toBe(tableCells(live('M'))[0].id);
    expect(f?.target?.title).toContain('1행');
  });

  it('근거 버튼 — finding_ids 여러 개면 그 칸들의 상자로 이동(M 표 칸 3행), 첫 상자에 이름표', () => {
    const r = v2Case('M');
    const a = liveOf(r);
    const raw = rawItems(r)[0];
    expect(raw.evidence[0].finding_ids.length).toBe(3);
    const cells = raw.evidence[0].finding_ids.map((id) => a.findings.find((f) => f.live?.id === id) as Finding);
    const anchors = cells.flatMap((f) => f.anchors);
    expect(a.items[0].evidence[0].anchors).toEqual(anchors);
    const plan = planPickItemEvidence(a, 'R-01', 0, false, false);
    expect(plan?.patch).toMatchObject({ focus: { kind: 'item', id: 'R-01', idx: 0 }, docId: 'doc-0', page: 1 });
    expect(plan?.viewer).toBe(anchors[0]);
    expect(focusAnchors(a, { kind: 'item', id: 'R-01', idx: 0 })).toEqual(anchors);
    const v = viewer(a, { focus: { kind: 'item', id: 'R-01', idx: 0 } });
    expect(v.live?.boxes.filter((b) => b.on).map((b) => b.anchor)).toEqual(anchors);
    expect(v.live?.boxes.filter((b) => b.tag).map((b) => b.anchor)).toEqual([anchors[0]]);
    expect(v.tag.text).toBe('R-01 · 형식 오류');
    // 항목을 고를 때도(첫 근거 — 스크롤은 첫 상자, 검토 필요 탭)
    const pick = planPickItem(a, 'R-01', false);
    expect(pick?.patch.tab).toBe('review');
    expect(pick?.viewer).toBe(anchors[0]);
    expect(pick?.card).toBe('R-01');
  });

  it('근거 버튼 — 다른 서류 · 쪽의 근거(A R-03 위임장, 4건), 근거 칸이 없는 항목(P)은 그 쪽 맨 위 + 공지', () => {
    const a = live('A');
    const plan = planPickItemEvidence(a, 'R-03', 0, false, false);
    expect(plan?.patch).toMatchObject({ docId: 'doc-3', page: 1 });
    expect(a.items[2].evidence[0].anchors.length).toBeGreaterThan(1);
    expect(plan?.viewer).toBe(a.items[2].evidence[0].anchors[0]);

    const p = live('P');
    expect(p.items[0].evidence[0].anchors).toEqual([]);
    expect(planPickItemEvidence(p, 'R-01', 0, false, false)?.viewer).toBe(SCROLL_TOP);
    const v = viewer(p, { focus: { kind: 'item', id: 'R-01', idx: 0 } });
    expect(v.notices.map((n) => n.title)).toContain('R-01 · 판독 불가');
  });

  it("'유지' 안내는 실제 분석에 없다 — 높음 + 판독 불가가 있어도(P), 설명 글을 새로 넣지 않는다", () => {
    const p = live('P');
    expect(p.findings.some((f) => f.risk === 'high')).toBe(true);
    expect(p.items.some((i) => i.type === 'unreadable')).toBe(true);
    expect(results(p).keep).toBeNull();
  });
});

describe('연결 탭', () => {
  const linkHtml = (a: Analysis) => {
    const rs = results(a, stateOf(a, { tab: 'links' }));
    return renderToStaticMarkup(createElement(LinkCards, { links: rs.links, locked: rs.locked, intro: rs.linksIntro, onPickDoc: () => {}, actions: READ_ONLY_ACTIONS }));
  };

  it('A — 칸 이름 · 표시값(fields) · 본인 성명 글이 그대로, insufficient 카드(값 없음 · 부족한 근거)도 그려진다, 판단 버튼 · 설명 줄 없음', () => {
    const r = v2Case('A');
    const a = liveOf(r);
    const raw = rawLinks(r);
    expect(a.links.map((l) => [l.id, l.status, l.live?.id])).toEqual(raw.map((l) => [l.number, l.status, l.id]));
    expect(a.links.map((l) => l.docs.map((d) => d.fields))).toEqual(raw.map((l) => l.docs.map((d) => d.fields)));
    expect(a.links.map((l) => [l.title, l.basis, l.missing, l.check])).toEqual(raw.map((l) => [l.title, l.basis, l.missing, l.check]));
    expect(raw.every((l) => l.label === '본인 성명')).toBe(true);
    const html = linkHtml(a);
    for (const l of raw) {
      expect(html).toContain(l.title);
      for (const d of l.docs) expect(html).toContain(d.fields);
    }
    expect(html).toContain('두 서류의 본인 성명이 같습니다.');
    // insufficient — 기준 칸은 값이 있어도 weaklink 문구, 대상 칸은 '본인 성명 값 없음'
    const weak = raw[2];
    expect(weak.state).toBe('insufficient');
    expect(weak.docs[1].fields).toBe('본인 성명 값 없음');
    expect(a.links[2]).toMatchObject({ status: 'check', basis: [], missing: weak.missing });
    expect(a.links[2].docs[1].anchors).toEqual([]);
    expect(html).toContain('<strong>부족한 근거</strong> · ' + weak.missing);
    expect(linkModel(a, a.links[2], null).canDecide).toBe(false);
    expect(html).not.toContain('연결 아님');
    expect(html).not.toContain('문서 사이에서 같은 사람');
    expect(results(a).tabs.map((t) => t.value)).toEqual(['findings', 'review', 'links', 'summary']);
  });

  it("U — unmatched 두 카드, mismatch 항목의 '연결 보기'가 그 카드로, 근거 보기는 칸 위치로", () => {
    const r = v2Case('U');
    const a = liveOf(r);
    expect(a.links.map((l) => [l.id, l.status, l.docs.map((d) => d.anchors.length > 0)])).toEqual([
      ['L-01', 'check', [true, true]],
      ['L-02', 'check', [true, true]],
    ]);
    expect(a.items.map((i) => [i.id, i.type, i.linkId])).toEqual([
      ['R-01', 'mismatch', 'L-01'],
      ['R-02', 'lowconf', undefined],
      ['R-03', 'mismatch', 'L-02'],
    ]);
    const plan = planOpenLink(a, 'L-02', false);
    expect(plan?.patch.tab).toBe('links');
    expect(plan?.card).toBe('L-02');
    expect(plan?.patch.docId).toBe('doc-1');
    expect(plan?.viewer).toBe(a.links[1].docs[0].anchors[0]);
    const html = linkHtml(a);
    expect(html.split('근거 보기</button>').length - 1).toBe(4);
    expect(html).toContain('두 서류의 본인 성명이 다릅니다.');
    for (const l of rawLinks(r)) for (const d of l.docs) expect(html).toContain(d.fields.split(' ').slice(0, 2).join(' '));
  });

  it('연결이 없는 결과는 문서 간 연결 탭이 없다(E · T)', () => {
    for (const key of ['E', 'T'] as const) expect(results(live(key)).tabs.map((t) => t.value)).toEqual(['findings', 'review', 'summary']);
  });
});

describe('빈 서식 · 대상 외 · 같은 서식 두 건', () => {
  it('S 빈 서식 — 탐지 0 · 필수 항목 없음 2 · 원문 쪽은 그대로, 보고서 · 내보내기 0건', () => {
    const a = live('S');
    expect(a.raw?.detailReady).toBe(true);
    expect(a.findings).toEqual([]);
    expect(a.items.map((i) => i.title)).toEqual(['예금주 성명이 없습니다', '출금계좌번호가 없습니다']);
    expect(results(a).findings).toEqual([]);
    expect(stateOf(a).focus).toBeNull();
    expect(viewer(a).hasPage).toBe(true);
    expect(viewer(a).live?.boxes).toEqual([]);
    const v = reportView(reportSafeAnalysis(a));
    expect(v.nFind).toBe(0);
    expect(v.remaining.length).toBe(2);
    expect(renderReport(v)).toContain('필수 항목 없음');
    const csv = file(a, 'csv').text.replace(/^﻿/, '').trim().split('\r\n');
    expect(csv).toEqual([CSV_COLUMNS.join(',')]);
    expect(maskPlan(a, {}, 2)).toMatchObject({ picked: [], missed: [] });
  });

  it('R 대상 외 — 서류 기타 · 탐지 0 · 기타 서류 항목 하나, 원문에 기타 서류 안내', () => {
    const a = live('R');
    expect(a.docs.map((d) => [d.title, d.source?.kind])).toEqual([['기타', 'other']]);
    expect(a.findings).toEqual([]);
    expect(a.items.map((i) => [i.type, i.live?.id])).toEqual([['other', 'other:0']]);
    expect(viewer(a).notices.map((n) => n.title)).toContain('기타 서류 안내');
    // 추출 단계가 없는 대상 외 — '읽지 못함' 이 아니라 0개
    expect(summaryRows(v2Case('R'), { createdAt: '', updatedAt: '', jobId: '' }).find((r) => r.key === 'extracted')?.value).toBe('0개');
    expect(rowsOf(summaryHtml(a)).find(([k]) => k === 'extracted')?.[2]).toBe('0개');
    expect(finalFlowRows(a.raw?.bundleCheck, a.links)).toEqual([{ key: 'bundle', label: '묶음 검증', value: '실패 · 실패 1' }]);
    expect(reportView(reportSafeAnalysis(a)).remaining.map((x) => x.type)).toEqual(['기타 서류']);
    expect(file(a, 'csv').text.split('\r\n').length).toBe(2);
  });

  it('T 같은 서식 두 건 — 서류 둘(이름 구별) · 번호는 서류별, 같은 서식 여러 건 항목은 첫 서류, 연결 없음', () => {
    const a = live('T');
    expect(a.docs.map((d) => [d.id, d.title, d.source?.pageStart])).toEqual([
      ['doc-0', '소비자피해보상금 지급신청서', 1],
      ['doc-1', '소비자피해보상금 지급신청서 2', 2],
    ]);
    expect(a.findings.filter((f) => f.docId === 'doc-0').every((f) => f.id.startsWith('D1-'))).toBe(true);
    expect(a.findings.filter((f) => f.docId === 'doc-1').every((f) => f.id.startsWith('D2-'))).toBe(true);
    expect(a.findings.filter((f) => f.docId === 'doc-1').length).toBeGreaterThan(0);
    expect(a.items[0]).toMatchObject({ type: 'duplicate', docId: 'doc-0', page: 1 });
    expect(a.items[0].live?.id).toBe('duplicate:소비자피해보상금_지급신청서');
    expect(a.links).toEqual([]);
    expect(JSON.parse(file(a, 'json').text)).not.toHaveProperty('문서간연결');
    expect(reportView(reportSafeAnalysis(a)).cards.map((c) => c.key)).toEqual(['findings', 'reviewed', 'remaining']);
  });
});

describe('보고서 · 내보내기 안전 사본', () => {
  it.each(ALL)('%s — 표시값 밖에 원문 값 없음(안전한 사본의 글 값 · 보고서 마크업 · CSV · JSON), 사본의 raw.result 는 null, 판정 토큰은 그대로', (key) => {
    const a = live(key);
    const raws = rawValues(a);
    const masks = masksOf(a);
    if (a.findings.length) expect(raws.length).toBeGreaterThan(0);
    const safe = reportSafeAnalysis(a);
    expect(safe.raw?.result).toBeNull();
    expect(safe.findings.every((f) => f.evidence === '' && f.live?.value === '')).toBe(true);
    expect(safe.raw?.decision).toEqual(a.raw?.decision);
    expect(hits(raws, valueUnits(safe), masks)).toEqual([]);
    expect(hits(raws, markupUnits(renderReport(reportView(safe))), masks)).toEqual([]);
    for (const format of ['csv', 'json'] as const) expect(hits(raws, fileUnits(a, format), masks), format).toEqual([]);
  });

  it('판정 토큰 500개 경계 — 사본도 500개까지 읽어 원문을 가린다(500번째 안 값까지), 501번째는 읽지 않는다', () => {
    const r = v2Case('E');
    const base = live('E');
    const raw = rawValues(base)[0];
    const masked = base.findings.find((f) => f.live?.value === raw)?.masked ?? '';
    const tokens = Array.from({ length: 501 }, (_, i) => `서식.칸${i}`);
    tokens[499] = `서식.${raw}`;
    tokens[500] = `서식.뒤${raw}`;
    const d = r.decision as RawV2Decision;
    d.medium_risk_items = tokens;
    const a = liveOf(r);
    const shown = a.raw?.decision as RawDecisionV2;
    expect(shown.mediumRiskItems?.length).toBe(500);
    expect(shown.mediumRiskItems?.[499]).toBe(`서식.${raw}`);
    const safe = reportSafeAnalysis(a).raw?.decision as RawDecisionV2;
    expect(safe.mediumRiskItems?.length).toBe(500);
    expect(safe.mediumRiskItems?.[499]).toBe(`서식.${masked}`);
    expect(safe.mediumRiskItems?.[498]).toBe('서식.칸498');
    expect(JSON.stringify(decisionView(safe))).not.toContain(raw);
    // 사유 줄에 토큰은 들어가지 않는다 — 내보내기 파일에도 판정 토큰 목록은 없다
    for (const format of ['csv', 'json'] as const) expect(file(a, format).text).not.toContain('서식.칸498');
  });

  it('판단 근거 · 권장 조치 · 검토 사유에 원문 값이 섞여 와도 보고서 · 내보내기에서 가린다(상세 판정 칸은 원래 글)', () => {
    const r = v2Case('P');
    const base = live('P');
    const raw = rawValues(base)[0];
    const d = r.decision as RawV2Decision;
    d.reason = `근거 ${raw}`;
    d.review_reasons = [`사유 ${raw}`];
    d.recommended_action = `조치 ${raw}`;
    const overall = r.overall as Obj;
    overall.text = d.reason;
    overall.next_text = d.recommended_action;
    const a = liveOf(r);
    expect(decisionView(a.raw?.decision)?.reason).toBe(`근거 ${raw}`);
    const safe = reportSafeAnalysis(a);
    const masks = masksOf(a);
    expect(hits([raw], valueUnits(safe.raw?.decision), masks)).toEqual([]);
    expect(hits([raw], valueUnits(safe.riskReasons), masks)).toEqual([]);
    expect(hits([raw], valueUnits(safe.recs), masks)).toEqual([]);
    expect(hits([raw], markupUnits(renderReport(reportView(safe))), masks)).toEqual([]);
    for (const format of ['csv', 'json'] as const) expect(hits([raw], fileUnits(a, format), masks), format).toEqual([]);
  });
});

describe('원문 검사 규칙 — 표시값 안의 일치만 허용한다', () => {
  /** 시험 안에서 만드는 값(음절 둘 · 숫자) — 고정 자료 · 고정 글에 없다 */
  const word = (n: number) => Array.from({ length: 2 }, (_, i) => String.fromCodePoint(0xb2e4 + n * 53 + i)).join('');
  const W = word(1);
  const N = String(60 + 37);
  const stars = (n: number) => '*'.repeat(n);

  it('표시값 안은 통과 — 앞부분 · 뒷부분 · 가운데 · 긴 글 속의 표시값', () => {
    for (const mask of [`${W}${stars(4)}`, `${stars(4)}${W}`, `${stars(2)}-${W}-${stars(2)}`]) {
      expect(hits([W], [mask], [mask])).toEqual([]);
      expect(hits([W], [`앞 글 ${mask} 뒤 글`], [mask])).toEqual([]);
    }
  });

  it('표시값 밖은 실패 — 같은 글 단위 · 다른 글 단위, 표시값이 없으면 어디든', () => {
    const mask = `${stars(4)}${W}`;
    expect(hits([W], [`${mask} ${W}`], [mask])).toEqual(['2자']);
    expect(hits([W], [mask, `앞 글 ${W}`], [mask])).toEqual(['2자']);
    expect(hits([W], [W], [])).toEqual(['2자']);
  });

  it('표시값에 걸친 일치 · 표시값 일부만 있는 글 · 한 글자 표시값은 허용하지 않는다(지운 뒤 찾으면 놓치는 자리)', () => {
    const [first, second] = Array.from(W);
    expect(hits([W], [`${stars(2)}${W}`], [`${stars(2)}${first}`])).toEqual(['2자']);
    expect(hits([W], [`${W}${stars(1)}`], [`${W}${stars(4)}`])).toEqual(['2자']);
    expect(hits([W], [W], [first, second])).toEqual(['2자']);
  });

  it('지운 양쪽이 붙어 생기는 일치는 만들지 않는다', () => {
    const [first, second] = Array.from(W);
    expect(hits([W], [`${first}${stars(3)}${second}`], [stars(3)])).toEqual([]);
  });

  it('3자 이하 숫자는 앞뒤가 숫자가 아닌 자리만 센다, 4자 이상은 어디든 센다', () => {
    for (const text of [`1${N}`, `${N}1`, `1${N}1`]) expect(hits([N], [text], [])).toEqual([]);
    for (const text of [N, `"${N}"`, `가${N}나`, `a${N}b`, `1.${N}`, `${N}.5`, `-${N}%`]) expect(hits([N], [text], [])).toEqual(['2자·숫자']);
    const three = `${N}3`;
    expect(hits([three], [`1${three}`], [])).toEqual([]);
    expect(hits([three], [`-${three}-`], [])).toEqual(['3자·숫자']);
    const four = `${three}4`;
    expect(hits([four], [`1${four}2`], [])).toEqual(['4자·숫자']);
  });

  it('후보 — 표시값에 든 값 · 표시값과 같은 값도 남는다, 뺀 것은 한 글자 값 · 정해진 관계 칸의 본인뿐', () => {
    const SELF = '본인';
    const analysis = (...cells: [string, string, string, ('workflow' | null)?][]) =>
      ({ findings: cells.map(([field, value, masked, source = 'workflow']) => ({ masked, live: { field, value, riskSource: source } })) }) as unknown as Analysis;
    expect(rawValues(analysis(['중_비율', N, stars(2)], ['중_전화', `010${N}`, `${stars(3)}${N}`]))).toEqual([N, `010${N}`]);
    expect(rawValues(analysis(['중_번호', `${N}****`, `${N}****`]))).toEqual([`${N}****`]);
    expect(rawValues(analysis(['중_a', '1', '*'], ['중_b', '가', '*'], ['중_c', String.fromCodePoint(0x1f600), '*'], ['중_d', '', '']))).toEqual([]);
    for (const field of ['중_관계', '중_대리인_관계', '법적대리인[0].중_법정대리인_관계', '가족카드신청인정보[3].중_가족관계#2']) expect(rawValues(analysis([field, SELF, '본*'])), field).toEqual([]);
    expect(rawValues(analysis(['중_관계', SELF, '본*', null]))).toEqual([SELF]);
    expect(rawValues(analysis(['중_관계x', SELF, '본*']))).toEqual([SELF]);
    expect(rawValues(analysis(['중_관계', `${SELF}인`, '본**']))).toEqual([`${SELF}인`]);
    expect(rawValues(analysis(['중_관계', SELF, '본*'], ['중_성명', SELF, '본*']))).toEqual([SELF]);
  });

  it('글 단위 — 마크업은 이어진 글 · 속성 값 하나씩, 엔티티는 풀고, 칸 경계에서 생기는 겹침은 일치가 아니다', () => {
    const [first, second] = Array.from(W);
    const cells = `<tr><td class="a">앞${first}</td><td>${second}뒤</td></tr>`;
    expect(cells.replace(/<[^>]*>/g, '')).toContain(W);
    expect(markupUnits(cells).map(unitText)).toEqual(['a', `앞${first}`, `${second}뒤`]);
    expect(hits([W], markupUnits(cells), [])).toEqual([]);
    expect(hits([W], markupUnits(`<td>칸 ${W}</td>`), [])).toEqual(['2자']);
    expect(hits([W], markupUnits(`<i title="칸 ${W}"></i>`), [])).toEqual(['2자']);
    expect(markupUnits('<p data-x="&lt;a&gt; &quot;b&quot; &#x27;c&#x27;">&amp;lt; 1 &gt; 2</p>\n').map(unitText)).toEqual(['<a> "b" \'c\'', '&lt; 1 > 2', '\n']);
    const special = `${W}&<`;
    expect(hits([special], markupUnits(renderToStaticMarkup(createElement('p', { title: special }))), [])).toEqual(['4자']);
    expect(hits([special], markupUnits(renderToStaticMarkup(createElement('p', null, special))), [])).toEqual(['4자']);
  });

  describe('이어진 인라인 글(검증 V-T3-2 minor 1)', () => {
    /** 코드로 만든 여섯 글자 값 — 앞뒤로 나눠 넣는다 */
    const LONG = Array.from({ length: 6 }, (_, i) => String.fromCodePoint(0xc544 + i * 29)).join('');
    const front = LONG.slice(0, 3);
    const back = LONG.slice(3);
    const fail = ['6자'];

    it.each([
      ['일반 글 + 자식 span', `<p>${front}<span>${back}</span></p>`],
      ['자식 span 둘', `<p><span>${front}</span><span>${back}</span></p>`],
      ['b + i', `<div><b>${front}</b><i>${back}</i></div>`],
      ['겹친 인라인', `<p><span><b>${front}</b></span><a href="#x"><em>${back}</em></a></p>`],
      ['세 조각', `<p>${LONG.slice(0, 2)}<strong>${LONG.slice(2, 4)}</strong>${LONG.slice(4)}</p>`],
      ['표 칸 안의 인라인', `<td>${front}<span>${back}</span></td>`],
      ['블록 안에서 이어진 글', `<div><p>앞 글</p><p>${front}<span>${back}</span> 뒤 글</p></div>`],
    ])('인라인 자식을 넘어 합친다 — %s', (_name, html) => {
      expect(hits([LONG], markupUnits(html), [])).toEqual(fail);
    });

    it.each([
      ['표 칸', `<table><tbody><tr><td>${front}</td><td>${back}</td></tr></tbody></table>`],
      ['머리 칸', `<tr><th>${front}</th><th>${back}</th></tr>`],
      ['칸 안의 인라인', `<tr><td><span>${front}</span></td><td><span>${back}</span></td></tr>`],
      ['블록 둘', `<div>${front}</div><div>${back}</div>`],
      ['블록 + 글', `<div><p>${front}</p>${back}</div>`],
      ['빈 블록 사이', `<div>${front}<p></p>${back}</div>`],
      ['목록 항목', `<ul><li>${front}</li><li>${back}</li></ul>`],
      ['br', `<p>${front}<br/>${back}</p>`],
      ['그림', `<p>${front}<img src="x"/>${back}</p>`],
      ['버튼', `<p>${front}<button>${back}</button></p>`],
      ['svg', `<p>${front}<svg><text>${back}</text></svg></p>`],
    ])('블록 · 표 칸 등의 경계는 넘지 않는다 — %s', (_name, html) => {
      expect(hits([LONG], markupUnits(html), [])).toEqual([]);
    });

    it('표시값 범위는 합친 글에 적용한다 — 인라인 자식으로 갈린 표시값 안은 통과, 그 밖은 실패', () => {
      const mask = `${stars(4)}${N}`;
      expect(hits([N], markupUnits(`<p>${stars(4)}<span>${N}</span></p>`), [mask])).toEqual([]);
      expect(hits([LONG], markupUnits(`<p>${stars(2)}${front}<b>${back}</b></p>`), [`${stars(2)}${LONG}`])).toEqual([]);
      expect(hits([N], markupUnits(`<p>${stars(4)}<span>${N}</span> <b>${N}</b></p>`), [mask])).toEqual(['2자·숫자']);
      expect(hits([LONG], markupUnits(`<p>${stars(2)}${front}<b>${back}</b></p>`), [`${stars(2)}${front}`])).toEqual(fail);
    });

    it('숫자 경계는 글자 노드 안에서 본다 — 옆 노드의 숫자는 경계를 없애지 않고, 갈린 숫자는 합쳐서 찾는다', () => {
      expect(hits([N], markupUnits(`<p><span>${N}</span><span>3건</span></p>`), [])).toEqual(['2자·숫자']);
      expect(hits([N], markupUnits(`<p><span>1${N}</span></p>`), [])).toEqual([]);
      expect(hits([N], markupUnits(`<p>${N[0]}<span>${N[1]}</span></p>`), [])).toEqual(['2자·숫자']);
      expect(hits([N], markupUnits(`<p>1${N[0]}<span>${N[1]}</span></p>`), [])).toEqual([]);
    });
  });

  it('글 단위 — CSV 는 칸 하나씩, JSON 은 값 · 키 하나씩, 안전한 사본은 문자열 값만', () => {
    const text = `\uFEFF항목ID,판단근거\r\n"D1-01","${W},""${N}""\n끝"\r\nD1-02,${W}\r\n`;
    expect(csvUnits(text)).toEqual(['항목ID', '판단근거', 'D1-01', `${W},"${N}"\n끝`, 'D1-02', W]);
    expect(csvUnits('a,b\r\nc,d')).toEqual(['a', 'b', 'c', 'd']);
    expect(hits([W], csvUnits(`앞${W.slice(0, 1)},${W.slice(1)}뒤\r\n`), [])).toEqual([]);
    const value = { 칸: [{ 쪽: Number(N), 글: W }], 없음: null, 참: true };
    expect(valueUnits(value, true)).toEqual(['칸', '쪽', N, '글', W, '없음', '참']);
    expect(valueUnits(value)).toEqual([W]);
  });

  it('실제 출력 — 다른 칸 표시값 뒤쪽에 든 값은 그 자리에서 통과, 표시값 밖에 넣으면 보고서 · CSV · JSON · 안전한 사본 모두 실패', () => {
    const r = v2Case('A');
    const [one, two] = rawFindings(r);
    one.value = N;
    one.masked = stars(2);
    two.masked = `${stars(6)}${N}`;
    const a = liveOf(r);
    const masks = masksOf(a);
    const safe = reportSafeAnalysis(a);
    const report = renderReport(reportView(safe));
    const csv = file(a, 'csv').text;
    const json = JSON.parse(file(a, 'json').text) as { 주요위험사유: string[] };
    const fail = ['2자·숫자'];
    // 재료가 실제로 들어갔다 — 후보에 남아 있고 그 표시값이 출력의 글 단위에 있다
    expect(rawValues(a)).toContain(N);
    expect(markupUnits(report).map(unitText)).toContain(two.masked);
    expect(csvUnits(csv)).toContain(two.masked);
    expect(valueUnits(json)).toContain(two.masked);
    expect(valueUnits(safe)).toContain(two.masked);
    // 그 자리에서는 통과한다(표시값을 주지 않으면 같은 글이 실패한다)
    expect(hits([N], markupUnits(report), masks)).toEqual([]);
    expect(hits([N], csvUnits(csv), masks)).toEqual([]);
    expect(hits([N], valueUnits(json, true), masks)).toEqual([]);
    expect(hits([N], valueUnits(safe), masks)).toEqual([]);
    expect(hits([N], markupUnits(report), [])).toEqual(fail);
    expect(hits([N], csvUnits(csv), [])).toEqual(fail);
    // 표시값 밖에 넣는다
    expect(hits([N], markupUnits(`${report}<p>칸 ${N}</p>`), masks)).toEqual(fail);
    expect(hits([N], markupUnits(`${report}<i title="칸 ${N}"></i>`), masks)).toEqual(fail);
    expect(hits([N], markupUnits(`${report}<p>칸 ${N[0]}<span>${N[1]}</span></p>`), masks)).toEqual(fail);
    expect(hits([N], csvUnits(`${csv}${','.repeat(10)}"칸 ${N}"\r\n`), masks)).toEqual(fail);
    expect(hits([N], valueUnits({ ...json, 주요위험사유: [...json.주요위험사유, `칸 ${N}`] }, true), masks)).toEqual(fail);
    expect(hits([N], valueUnits({ ...safe, 더한글: `칸 ${N}` }), masks)).toEqual(fail);
  });
});

describe('원문 값 바꾸기 — 관계 칸의 예외는 값 본인 하나(실제 응답의 고정 글 충돌 · 검증 V-T2-1 M1)', () => {
  /** 시험 안에서 만드는 임의 값(음절 10개) — 고정 자료 · 고정 글에 없다 */
  const marker = (n = 0) => Array.from({ length: 10 }, (_, i) => String.fromCodePoint(0xac10 + n * 31 + i)).join('');
  /** 백엔드가 text 칸을 가리는 모양 — 첫 글자 + 별(tests/test_v2_fixture_sync.py 가 실제 출력과 같은지 지킨다) */
  const maskedOf = (v: string) => Array.from(v)[0] + '*'.repeat(Array.from(v).length - 1);

  /** 네 출력 — 안전한 사본 · 보고서 마크업 · 내보내기 CSV · JSON */
  const outputs = (a: Analysis) => {
    const safe = reportSafeAnalysis(a);
    return { safe: JSON.stringify(safe), report: renderReport(reportView(safe)), csv: file(a, 'csv').text, json: file(a, 'json').text };
  };
  const leaks = (a: Analysis, raw: string) => Object.entries(outputs(a)).filter(([, text]) => text.includes(raw)).map(([name]) => name);

  /** 칸 하나의 값을 바꾼 자료(필요하면 칸 이름도) — 백엔드가 만드는 모양 그대로 */
  function withCell(key: V2Case, field: string, value: string, renamed = field): Obj {
    const r = v2Case(key);
    const cell = rawFindings(r).find((f) => f.field === field);
    if (!cell) throw new Error('칸이 없다');
    cell.field = renamed;
    cell.value = value;
    cell.masked = maskedOf(value);
    return r;
  }

  /** 칸 값 + 판정 reason · recommended_action 에 같은 글(overall 은 백엔드처럼 판정을 따른다) */
  function withCopied(key: V2Case, field: string, value: string, renamed = field): Obj {
    const r = withCell(key, field, value, renamed);
    const d = r.decision as RawV2Decision;
    d.reason = value;
    d.recommended_action = value;
    const overall = r.overall as Obj;
    overall.text = value;
    overall.next_text = value;
    return r;
  }

  const allTokens = (d: RawV2Decision | RawDecisionV2 | null | undefined): string[] =>
    d && 'high_risk_items' in d ? [...d.high_risk_items, ...d.medium_risk_items, ...d.low_risk_items] : d ? [...(d.highRiskItems ?? []), ...(d.mediumRiskItems ?? []), ...(d.lowRiskItems ?? [])] : [];

  describe('관계 칸의 임의 값은 판정 글에 복사돼 와도 가린다(백엔드 경로 — 검증자 재현)', () => {
    it.each([
      ['U', '세대구성원[0].중_관계', '세대구성원[0].중_관계'],
      ['U', '세대구성원[0].중_관계', '세대구성원[0].중_관계#2'],
      ['M', '세대구성원[1].중_관계', '세대구성원[1].중_관계'],
      ['A', '중_대리인_관계', '중_대리인_관계'],
      ['A', '중_대리인_관계', '중_대리인_관계#2'],
      ['U', '세대구성원[0].중_관계', '법적대리인[0].중_법정대리인_관계'],
      ['U', '세대구성원[0].중_관계', '가족카드신청인정보[0].중_가족관계'],
      ['U', '세대구성원[0].중_관계', '상_관계'],
      ['U', '세대구성원[0].중_관계', '중_개인정보관계'],
    ] as const)('%s %s → %s — 안전한 사본 · 보고서 마크업 · CSV · JSON 어디에도 없다', (key, field, renamed) => {
      const raw = marker(2);
      const masked = maskedOf(raw);
      const a = liveOf(withCopied(key, field, raw, renamed));
      // 재료가 실제로 들어갔다 — 상세 판정 칸은 원래 글(대회용 원문 표시 허용), 사본에서만 가린다
      expect(a.raw?.decision?.reason).toBe(raw);
      expect(a.raw?.overall?.nextText).toBe(raw);
      expect(leaks(a, raw)).toEqual([]);
      const safe = reportSafeAnalysis(a);
      expect(safe.raw?.decision?.reason).toBe(masked);
      expect((safe.raw?.decision as RawDecisionV2).recommendedAction).toBe(masked);
      expect(safe.raw?.overall).toMatchObject({ text: masked, nextText: masked });
      expect(safe.riskReasons[0]).toBe(masked);
      expect(safe.recs).toEqual([masked]);
      const json = JSON.parse(file(a, 'json').text);
      expect(json.주요위험사유[0]).toBe(masked);
      expect(json.권장조치).toEqual([masked]);
    });

    it('대조 — risk_source 가 null 이어도 같다(옛 결과의 가림 그대로)', () => {
      const raw = marker(2);
      const r = withCopied('U', '세대구성원[0].중_관계', raw);
      const nulled = rawFindings(r).find((f) => f.value === raw) as RawFinding & { risk_source: string | null };
      nulled.risk_source = null;
      expect(leaks(liveOf(r), raw)).toEqual([]);
    });

    it('바깥 응답이 관계 칸 값을 연결 글 · 항목 판단 근거 · 검토사항 글에 넣어도 가린다(방어 경계 — 백엔드는 만들지 않는다)', () => {
      const raw = marker(3);
      const masked = maskedOf(raw);
      const r = withCopied('U', '세대구성원[0].중_관계', raw);
      rawLinks(r)[0].basis = [`근거 ${raw}`];
      rawLinks(r)[0].check = `확인 ${raw}`;
      (rawFindings(r).find((f) => f.value === raw) as RawFinding).risk_reason = `사유 ${raw}`;
      rawItems(r)[0].title = `제목 ${raw}`;
      const a = liveOf(r);
      // 연결 글은 읽을 때 가린다(상세 카드도)
      expect(a.links[0].basis).toEqual([`근거 ${masked}`]);
      expect(a.links[0].check).toBe(`확인 ${masked}`);
      expect(leaks(a, raw)).toEqual([]);
      expect(file(a, 'csv').text).toContain(`사유 ${masked}`);
    });

    it.each(['A', 'M', 'U'] as const)('%s — 고정 자료의 관계 칸 값도 원문 검사 대상이다(뺀 값 없이 사본 · 보고서 · 내보내기에 없다)', (key) => {
      const a = live(key);
      const cells = a.findings.filter((f) => SELF_CELL.test(f.live?.field ?? ''));
      expect(cells.length).toBeGreaterThan(0);
      const raws = cells.map((f) => f.live?.value ?? '').filter((v) => Array.from(v).length >= 2);
      expect(raws.length).toBeGreaterThan(0);
      for (const v of raws) {
        expect(rawValues(a)).toContain(v);
        expect(leaks(a, v)).toEqual([]);
      }
    });
  });

  describe('값이 정확히 본인이면 고정 글이 그대로다', () => {
    const SELF_TOKEN = '외국인_세대구성원_확인서.본인_성명';

    it.each([
      ['U', '세대구성원[0].중_관계', '세대구성원[0].중_관계'],
      ['U', '세대구성원[0].중_관계', '세대구성원[0].중_관계#2'],
      ['M', '세대구성원[1].중_관계', '세대구성원[1].중_관계'],
    ] as const)('%s %s → %s — 판정 토큰 …본인_성명 · 검토사항 글이 사본에서도 그대로, 그 칸의 원문 값은 사본에 없다', (key, field, renamed) => {
      const r = withCell(key, field, '본인', renamed);
      const safe = reportSafeAnalysis(liveOf(r));
      const d = r.decision as RawV2Decision;
      expect(allTokens(d)).toContain(SELF_TOKEN);
      expect(allTokens(safe.raw?.decision as RawDecisionV2)).toEqual(allTokens(d));
      expect(safe.items.map((i) => [i.title, i.desc, i.next])).toEqual(rawItems(r).map((i) => [i.title, i.desc, i.next]));
      const cell = safe.findings.find((f) => f.masked === '본*');
      expect(cell).toMatchObject({ evidence: '' });
      expect(cell?.live?.value).toBe('');
      for (const text of Object.values(outputs(liveOf(r)))) expect(text).not.toContain('본*_성명');
    });

    it('U — 연결 카드의 본인 성명(제목 · fields · 부족한 근거)과 보고서 · 내보내기 글이 그대로', () => {
      const r = withCell('U', '세대구성원[0].중_관계', '본인');
      const raw = rawLinks(r);
      const text = (l: { title: string; basis: string[]; missing: string; check: string; docs: { fields: string }[] }) => [l.title, l.basis, l.missing, l.check, l.docs.map((d) => d.fields)];
      const a = liveOf(r);
      expect(a.links.map(text)).toEqual(raw.map(text));
      expect(a.links[0].docs[0].fields).toContain('본인 성명');
      expect(a.links[0].missing).toContain('본인 성명');
      const safe = reportSafeAnalysis(a);
      expect(safe.links.map(text)).toEqual(raw.map(text));
      const out = outputs(a);
      expect(out.report).toContain('본인 성명');
      expect(out.json).toContain('본인 성명');
      expect(out.report).not.toContain('본* 성명');
      expect(out.json).not.toContain('본* 성명');
      const html = renderToStaticMarkup(createElement(LinkCards, { links: results(a, stateOf(a, { tab: 'links' })).links, locked: false, intro: false, onPickDoc: () => {}, actions: READ_ONLY_ACTIONS }));
      expect(html).toContain('두 서류의 본인 성명이 다릅니다.');
      expect(html).not.toContain('본* 성명');
    });

    it('A — 표 밖 관계 칸(중_대리인_관계)도 같다: 연결 근거 · 값 없음 글이 그대로', () => {
      const r = withCell('A', '중_대리인_관계', '본인');
      const a = reportSafeAnalysis(liveOf(r));
      expect(a.links[0].basis).toEqual(['두 서류의 본인 성명이 같습니다.']);
      expect(a.links[2].docs[1].fields).toBe('본인 성명 값 없음');
      expect(a.links[2].missing).toBe('비교할 본인 성명이 없습니다.');
    });

    it('다른 원문 값은 그대로 가린다 — 이름 값을 연결 글에 넣으면 사본에 없다', () => {
      const r = withCell('U', '세대구성원[0].중_관계', '본인');
      const name = rawFindings(r).find((f) => f.field === '중_본인_성명');
      if (!name) throw new Error('본인 성명 칸이 없다');
      rawLinks(r)[0].basis = [`근거 ${name.value}`];
      const a = liveOf(r);
      expect(a.links[0].basis).toEqual([`근거 ${name.masked}`]);
      expect(leaks(a, name.value)).toEqual([]);
    });
  });

  describe('예외의 경계(rawValueMasker)', () => {
    const FIXED = '본인 성명 · 외국인_세대구성원_확인서.본인_성명';
    const BROKEN = '본* 성명 · 외국인_세대구성원_확인서.본*_성명';
    /** riskSource 'none' = 그 키가 없는 항목 */
    const cell = (field: string, value = '본인', riskSource: 'workflow' | null | 'none' = 'workflow') =>
      ({ masked: maskedOf(value), live: { id: 'x', field, value, mappingStatus: 'ok', confidence: null, ...(riskSource === 'none' ? {} : { riskSource }) } }) as unknown as Finding;

    it.each([
      '중_관계',
      '중_관계#2',
      '세대구성원[0].중_관계',
      '세대구성원[12].중_관계#2',
      '중_대리인_관계',
      '중_대리인_관계#3',
      '법적대리인[0].중_법정대리인_관계',
      '법적대리인[1].중_법정대리인_관계#2',
      '가족카드신청인정보[0].중_가족관계',
    ])('예외 — %s 의 값 본인은 대상이 아니다', (field) => {
      expect(rawValueMasker([cell(field)])(FIXED)).toBe(FIXED);
    });

    it.each([
      '상_관계',
      '하_관계',
      '세대구성원[0].상_관계',
      '중_개인정보관계',
      '세대구성원[0].중_개인정보관계',
      '중_가족관계확인_본인성명',
      '가족카드신청인정보[0].중_가족관계확인_본인성명',
      '관계',
      '중_관계x',
      'x중_관계',
      '중_관계#',
      '중_관계#x',
      '중_관계#2#3',
      '중_관계 ',
      '세대구성원.중_관계',
      '세대구성원[x].중_관계',
      '세대구성원[0]중_관계',
      '[0].중_관계',
      '세대구성원[0].세대구성원[1].중_관계',
      '중_성명',
      '',
    ])('예외 아님 — %s 의 값 본인은 대상이다', (field) => {
      expect(rawValueMasker([cell(field)])(FIXED)).toBe(BROKEN);
    });

    it.each(['중_관계', '세대구성원[0].중_관계', '중_대리인_관계', '법적대리인[0].중_법정대리인_관계', '가족카드신청인정보[0].중_가족관계'])(
      '옛 결과(risk_source null · 없음) — %s 도 대상이다(동작 그대로)',
      (field) => {
        expect(rawValueMasker([cell(field, '본인', null)])(FIXED)).toBe(BROKEN);
        expect(rawValueMasker([cell(field, '본인', 'none')])(FIXED)).toBe(BROKEN);
      },
    );

    it.each(['배우자', '자녀', '본인 ', ' 본인', '본인1', '1본인', '본 인', '본인본인', '본인인'])('정해진 관계 칸이어도 다른 값(%s)은 대상이다', (value) => {
      for (const field of ['세대구성원[0].중_관계', '중_대리인_관계', '법적대리인[0].중_법정대리인_관계', '가족카드신청인정보[0].중_가족관계', '세대구성원[0].중_관계#2']) {
        expect(rawValueMasker([cell(field, value)])(`앞 ${value} 뒤`)).toBe(`앞 ${maskedOf(value)} 뒤`);
      }
    });

    it('같은 본인이 다른 칸에도 있으면 그 칸 때문에 대상이다(차례 무관)', () => {
      expect(rawValueMasker([cell('세대구성원[0].중_관계'), cell('중_성명')])(FIXED)).toBe(BROKEN);
      expect(rawValueMasker([cell('중_성명'), cell('세대구성원[0].중_관계')])(FIXED)).toBe(BROKEN);
    });

    it('본인이 빠져도 같은 분석의 다른 값은 그대로 가린다', () => {
      const other = marker(4);
      expect(rawValueMasker([cell('세대구성원[0].중_관계'), cell('세대구성원[1].중_관계', other)])(`본인 ${other}`)).toBe(`본인 ${maskedOf(other)}`);
    });

    it('칸 이름이 아주 길어도 곧 끝난다(선형 — 꼴 전체를 맞추는 한 번)', () => {
      const long = '가'.repeat(200_000);
      const digits = '1'.repeat(200_000);
      const t0 = performance.now();
      expect(rawValueMasker([cell(`${long}[0].${long}`)])('본인')).toBe('본*');
      expect(rawValueMasker([cell(`[${long}`)])('본인')).toBe('본*');
      expect(rawValueMasker([cell(`${long}[${digits}`)])('본인')).toBe('본*');
      expect(rawValueMasker([cell(`${long}[${digits}].`)])('본인')).toBe('본*');
      expect(rawValueMasker([cell(`${long}#${digits}`)])('본인')).toBe('본*');
      expect(rawValueMasker([cell(`${long}[${digits}].중_관계#${digits}`)])('본인')).toBe('본인');
      expect(performance.now() - t0).toBeLessThan(1000);
    });
  });
});
