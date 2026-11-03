/* ==========================================================================
   공통 계약(result.documents · findings · overall) → 화면 도메인 값 — 순수 함수
   - 백엔드와 맞춘 계약(BRIEF §2)을 방어적으로 읽는다: 필드가 빠졌거나 타입이 달라도 예외 없이 안전한 기본값.
   - 서류(documents[]) → AnalysisDoc(source 에 묶음 파일 안 쪽 범위). 같은 index 는 처음 것만, index 순.
   - 탐지 항목(findings[]) → Finding. 화면에 보이는 번호는 'D<서류 목록 순번(1부터)>-<그 서류 안 순번 두 자리>'(D1-01)로
     새로 만들고 계약 id('<document_index>:<field>')는 live.id 에 둔다. 서류 목록 순번은 정렬·중복 제거한 서류 목록의
     위치라 index 에 빈 번호가 있어도 D1·D2·D3 으로 이어진다(계약 index 는 source.index · 서류 id doc-<index> 에 남는다).
     짝이 되는 서류가 없는 항목은 버린다.
   - 항목 위험등급은 risk_source 가 'workflow' 일 때만 받은 값, 그 밖(null·없음)은 '미평가'다(워크플로우 판정 전).
   - 쪽은 파일 전체 기준 → 서류 안 쪽(1부터)으로 바꾼다. 쪽을 모르거나 서류 범위 밖이면 1쪽 · 위치 없음(anchors []).
   - 상자는 꼭짓점 2개 이상이고 모든 x·y 가 유한한 수인 것만, 값은 0~1 로 자르지 않는다(화면 변환이 자른다).
     쪽(0~1)과 전혀 겹치지 않는 상자는 그릴 수 없으므로 버린다 — 화면 변환과 같은 기준(unitBoxOnPage)이라
     위치 ID(anchors)가 그린 상자와 같아 이름표 · 스크롤 · '위치 확인 필요'가 어긋나지 않는다.
   - 원문 값(value)은 대회용 합성 자료라 화면에 보여도 된다(사용자 결정) — evidence · live.value 에 둔다.
   ========================================================================== */

import { CATS, EXPOSURES, RISK, SUBJECTS, docTypeName, type Exposure, type InfoCategory, type InfoSubject, type RiskLevel } from '@/display/rules';
import { pad2 } from '@/lib/format';
import { unitBoxOnPage } from '@/lib/pageBox';
import type { AnalysisDoc, DocSource, Finding, FindingBox, FindingLive, RawFileInfo, RawOverall } from '../types';

/** 항목 위험등급이 없고(risk_source null) 사유도 없을 때 보이는 판단 근거 */
export const UNRATED_REASON = '워크플로우가 항목별 위험등급을 아직 판정하지 않아 미평가로 표시합니다.';
/** 라벨·필드가 모두 빈 항목의 이름 */
export const UNNAMED_FINDING = '이름 없는 항목';
/** 분류 코드가 빈 서류의 이름 */
export const UNNAMED_DOC = '분류 없는 서류';

type Obj = Record<string, unknown>;

const isObj = (v: unknown): v is Obj => !!v && typeof v === 'object' && !Array.isArray(v);
const str = (v: unknown): string => (typeof v === 'string' ? v : '');
const isInt = (v: unknown): v is number => typeof v === 'number' && Number.isInteger(v);
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const own = (table: object, key: string): boolean => Object.prototype.hasOwnProperty.call(table, key);

/** 목록 안의 값이면 그대로, 아니면 대체값 */
function pick<T extends string>(list: readonly T[], value: unknown, fallback: T): T {
  return typeof value === 'string' && (list as readonly string[]).includes(value) ? (value as T) : fallback;
}

/* ---------- Markdown → 줄 목록 ---------- */

/** 목록 기호(- · * · + · 1. · 1)) — 뒤에 공백이 오거나 기호만 있는 줄 */
const LIST_MARK = /^(?:[-*+]|\d+[.)])(?:\s+|$)/;
/** 구분선(---, ***, ___) */
const RULE_LINE = /^(?:[-*_]\s*){3,}$/;
/** 인용 표시(【†3】 · 【3†source】 등) */
const CITATION = /【[^】]*】/g;

/**
 * Markdown → 줄 목록. 줄마다 앞뒤 공백을 떼고 빈 줄·제목 줄(#)·구분선은 뺀다.
 * 목록 기호 · 인용 표시(【…】) · 굵게 표시(**)를 지우고, 지운 뒤 빈 줄도 뺀다. 문자열이 아니면 [].
 */
export function markdownLines(md: unknown): string[] {
  if (typeof md !== 'string') return [];
  const out: string[] = [];
  for (const rawLine of md.split(/\r\n|\r|\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#') || RULE_LINE.test(line)) continue;
    const cleaned = line
      .replace(LIST_MARK, '')
      .replace(CITATION, '')
      .replace(/\*\*/g, '')
      .replace(/[ \t]{2,}/g, ' ')
      .trim();
    if (cleaned) out.push(cleaned);
  }
  return out;
}

/* ---------- 올린 파일 · overall ---------- */

/** documents 첫 행 → 올린 파일. 없거나 객체가 아니면 null */
export function readFile(documents: unknown): RawFileInfo | null {
  const first = Array.isArray(documents) ? documents[0] : undefined;
  if (!isObj(first)) return null;
  return {
    id: str(first.id),
    name: str(first.filename),
    mime: str(first.mime_type),
    size: isNum(first.size_bytes) && first.size_bytes >= 0 ? first.size_bytes : 0,
  };
}

/** result.overall → RawOverall. 객체가 아니면 null, 빠진 값은 '' */
export function readOverall(result: unknown): RawOverall | null {
  if (!isObj(result) || !isObj(result.overall)) return null;
  const o = result.overall;
  return { level: str(o.level), text: str(o.text), nextStage: str(o.next_stage), nextText: str(o.next_text) };
}

/* ---------- 서류 ---------- */

/** 유효한 documents[] 행 → DocSource(index 순, 같은 index 는 처음 것만). 배열이 아니면 [] */
export function readDocSources(documents: unknown): DocSource[] {
  if (!Array.isArray(documents)) return [];
  const seen = new Set<number>();
  const out: DocSource[] = [];
  for (const d of documents) {
    if (!isObj(d)) continue;
    const { index, page_start: start, page_end: end } = d;
    if (!isInt(index) || index < 0 || !isInt(start) || start < 1 || !isInt(end) || end < 1) continue;
    if (seen.has(index)) continue;
    seen.add(index);
    out.push({
      index,
      type: str(d.type),
      pageStart: start,
      pageEnd: Math.max(start, end),
      kind: d.kind === 'other' ? 'other' : 'extracted',
      otherGuide: str(d.other_guide),
      validation: str(d.validation),
    });
  }
  return out.sort((a, b) => a.index - b.index);
}

/** 서류 이름 — 분류 코드의 한국어 이름(기타 서류도 같다: 'Other' → '기타'), 코드가 비면 대체 이름 */
function baseDocTitle(s: DocSource): string {
  const name = docTypeName(s.type.trim()).trim();
  if (name) return name;
  return s.kind === 'other' ? docTypeName('Other') : UNNAMED_DOC;
}

/** 서류 id — 분석 안에서 겹치지 않는 고정 값 */
export const docIdFor = (index: number): string => `doc-${index}`;

/** DocSource 목록 → 문서 목록. 같은 이름은 두 번째부터 ' 2' · ' 3' 을 붙인다 */
export function toLiveDocs(sources: readonly DocSource[], file: RawFileInfo | null, ext: string): AnalysisDoc[] {
  const counts = new Map<string, number>();
  return sources.map((s) => {
    const base = baseDocTitle(s);
    const nth = (counts.get(base) ?? 0) + 1;
    counts.set(base, nth);
    return {
      id: docIdFor(s.index),
      title: nth > 1 ? `${base} ${nth}` : base,
      name: file?.name ?? '',
      ext,
      size: file?.size ?? 0,
      status: 'done',
      error: '',
      pages: null,
      pageCount: s.pageEnd - s.pageStart + 1,
      source: { ...s },
    };
  });
}

/* ---------- 탐지 항목 ---------- */

/** 상자 하나 — 꼭짓점 2개 이상, 모든 x·y 가 유한한 수. 아니면 null */
function readPoints(box: unknown): { x: number; y: number }[] | null {
  if (!Array.isArray(box) || box.length < 2) return null;
  const points: { x: number; y: number }[] = [];
  for (const p of box) {
    if (!isObj(p) || !isNum(p.x) || !isNum(p.y)) return null;
    points.push({ x: p.x, y: p.y });
  }
  return points;
}

/**
 * 표시용 항목 번호 — 'D<서류 목록 순번(1부터)>-<서류 안 순번 두 자리>'.
 * 서류 목록 순번은 정렬 · 중복 제거한 서류 목록(화면의 서류 순서) 위치다 — 계약 index 에 더하지 않는다
 * (큰 정수 index 는 + 1 이 반올림돼 서로 다른 서류가 같은 번호가 될 수 있다).
 */
export const findingNumber = (docNo: number, seq: number): string => `D${docNo}-${pad2(seq)}`;

function mappingStatus(v: unknown): FindingLive['mappingStatus'] {
  return v === 'ok' || v === 'needs_review' || v === 'unknown' ? v : 'unknown';
}

function confidence(v: unknown): FindingLive['confidence'] {
  return v === 'high' || v === 'low' ? v : null;
}

/**
 * findings[] → 탐지 항목(계약 순서 그대로). 짝이 되는 서류가 없는 항목은 버린다.
 * updatedAt = 분석 시각('YYYY-MM-DD HH:mm', 없으면 '').
 */
export function toLiveFindings(findings: unknown, sources: readonly DocSource[], updatedAt: string): Finding[] {
  if (!Array.isArray(findings)) return [];
  // 계약 index → 서류와 서류 목록 순번(1부터, 처음 나온 것). 번호는 순번으로 만든다(index 로 셈하지 않음)
  const byIndex = new Map<number, { src: DocSource; docNo: number }>();
  sources.forEach((src, i) => {
    if (!byIndex.has(src.index)) byIndex.set(src.index, { src, docNo: i + 1 });
  });
  const seqByDoc = new Map<number, number>();
  const out: Finding[] = [];
  for (const f of findings) {
    if (!isObj(f) || !isInt(f.document_index)) continue;
    const hit = byIndex.get(f.document_index);
    if (!hit) continue;
    const { src, docNo } = hit;
    const seq = (seqByDoc.get(docNo) ?? 0) + 1;
    seqByDoc.set(docNo, seq);
    const id = findingNumber(docNo, seq);

    const cat: InfoCategory = pick(CATS, f.category, '기타 개인정보');
    const subject: InfoSubject = pick(SUBJECTS, f.subject, '기타');
    const exposure: Exposure = pick(EXPOSURES, f.exposure, '전체 노출');

    const riskSource: FindingLive['riskSource'] = f.risk_source === 'workflow' ? 'workflow' : null;
    const risk: RiskLevel = riskSource === 'workflow' && typeof f.risk === 'string' && own(RISK, f.risk) ? (f.risk as RiskLevel) : 'unrated';
    const givenReason = str(f.risk_reason).trim();
    const reason = givenReason || (risk === 'unrated' ? UNRATED_REASON : '');

    // 쪽: 파일 기준 → 서류 안(1부터). 모르거나 범위 밖이면 1쪽 · 위치 없음
    const filePage = f.page;
    const located = isInt(filePage) && filePage >= src.pageStart && filePage <= src.pageEnd;
    const page = located ? filePage - src.pageStart + 1 : 1;

    const boxes: FindingBox[] = [];
    if (located && Array.isArray(f.boxes)) {
      for (const box of f.boxes) {
        const points = readPoints(box);
        // 쪽과 전혀 겹치지 않는 상자는 그릴 수 없다 — 위치 ID 에서도 뺀다(번호는 남은 상자만 차례로)
        if (points && unitBoxOnPage(points)) boxes.push({ a: `${id}#${boxes.length + 1}`, points });
      }
    }

    const field = str(f.field);
    const value = str(f.value);
    out.push({
      id,
      cat,
      label: str(f.label).trim() || field.trim() || UNNAMED_FINDING,
      masked: str(f.masked),
      subject,
      exposure,
      risk,
      reason,
      rule: '',
      docId: docIdFor(src.index),
      page,
      anchors: boxes.map((b) => b.a),
      evidence: value,
      status: 'open',
      memo: '',
      fpType: '',
      fpNote: '',
      reclassNote: '',
      updatedAt,
      ai: { cat, subject, exposure },
      boxes,
      live: {
        id: str(f.id),
        field,
        value,
        mappingStatus: mappingStatus(f.mapping_status),
        confidence: confidence(f.confidence),
        riskSource,
      },
    });
  }
  return out;
}

/* ---------- 새 형식 판단 ---------- */

/** 완료 + documents 배열(유효한 서류 1개 이상) + findings 배열이면 공통 계약 결과로 본다 */
export function isDetailReady(status: string, result: unknown, sources: readonly DocSource[]): boolean {
  return status === 'done' && isObj(result) && Array.isArray(result.documents) && sources.length > 0 && Array.isArray(result.findings);
}
