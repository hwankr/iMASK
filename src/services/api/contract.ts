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
   - 검토 기록 덧씌우기(overlayFindingReviews): review.findings[계약 id](자기 속성만)의 확인 상태 · 분류 · 오탐 사유 ·
     수정 사유 · 메모 · 수정 시각을 그 항목에 덧씌운다. 목록 밖 · 타입이 틀린 값은 버리고 AI 값 · 기본값을 쓴다.
     최초 AI 결과(ai) · 위험등급(risk) · 판단 근거(reason) · 계약 원래 값(live)은 바꾸지 않는다.
   - 검토사항(toLiveItems): 서버가 계산한 result.items[](BRIEF §5.3 — 화면은 다시 계산하지 않는다)를 ReviewItem 으로 옮긴다.
     id 가 비지 않은 문자열 · number 가 'R-' + 숫자 2자리 이상 · type 이 RTYPE 자기 키 · document_index 가 보이는 서류인 항목만,
     같은 id · 같은 number 는 처음 것만(받아들인 항목 기준). 화면 id = number, 계약 id 는 live.id. 쪽은 서류 안 쪽(범위 밖 · 정수 아님은 1쪽).
     글(title · desc · next)은 서버 글 그대로(문자열이 아니면 ''). 근거는 label 이 비지 않은 문자열인 객체만 — anchors 는 finding_ids 가
     가리키는 같은 서류 · 같은 쪽 탐지 항목의 위치 ID 를 차례로(겹치는 위치 ID 는 한 번), findingId 는 finding_id 가 같은 서류의 탐지
     항목일 때 그 화면 번호(위치 유무와 무관 — 누르면 그 탐지 항목을 고른다). 탐지 항목 찾기는 Map 이라 항목 · 근거 수에 선형이다.
   - 검토사항 덧씌우기(overlayItemReviews): review.items[계약 id](자기 속성 · 객체만)의 해결 여부(정확히 true 일 때만) · 처리 내용 ·
     해결 시각(서울, 못 읽으면 '') · 처리자를 덧씌운다. 그 밖은 미해결 기본값.
   - 문서 간 연결(toLiveLinks — 최종 흐름 워크플로우의 서류 대조, 읽기 전용): result.links[] 의 앞 MAX_LINKS 개를 DocLink 로 옮긴다.
     id · number 가 식별자(identifier)이고 number 가 'L-' + 숫자 2자리 이상 · status 가 confirmed · check · docs 가 1~MAX_LINK_DOCS 개이고
     모든 서류가 보이는 서류인 연결만, 같은 id · 같은 number 는 처음 받아들인 것만. 화면 id = number, 계약 id 는 live.id. 판단 값은 늘 비어 있다.
     화면 글은 safeText(자르지 않은 글 전체에 원문 값 바꾸기 → 최종 규칙)를 지난다. 연결 서류의 anchors 는 검토사항 근거와 같은 규칙
     (finding_ids 의 같은 서류 · 같은 쪽 탐지 항목 위치 ID, 겹치면 한 번 · 같은 탐지 id 는 한 번만 돈다).
     검토사항의 link_id 가 같은 결과의 연결(live.id)이면 그 연결의 화면 번호를 linkId 로 둔다('연결 보기').
   - 위험도 판정 키(readDecision)와 묶음 검증(readBundleCheck): result.decision · result.bundle_check 를 방어적으로 읽는다
     (객체가 아니면 null, 못 읽은 값은 null — 확인된 빈 목록과 섞지 않는다). 목록은 앞 N개만, 글은 safeText(mask 를 주면 원문 값을
     가린 글 — 보고서 사유), 서류 종류 코드는 식별자. 판정 모양은 둘이다: 옛 키 5개(최종 흐름 워크플로우) · 키 8개(설정 60 v2_full —
     high_risk_items 키가 있으면 v2, shape 'v2'). 등급별 항목 토큰('서식코드.칸')은 받은 글자 그대로이고 목록 한도는 500개(옛 모양은 50개).
   - 검토사항 · 연결의 계약 id 는 어떤 글자든 그대로 다룬다: 표 칸 탐지 항목(`<i>:<표>[<행>].<칸>`), review:<종류> · verdict:<i> · format ·
     duplicate 같은 설정 60 id 도 Map · 자기 속성으로만 찾고 CSS 선택자 · 주소에 넣지 않는다(화면 id 는 번호 D1-01 · R-01 · L-01).
   - 한도 · 서로게이트 규칙은 '바깥 글 · 목록 한도' 절(MAX_* · finalText · safeText · identifier)에 한 자리로 모았다.
     글은 자르지 않는다(넘으면 통째로 버림).
   ========================================================================== */

import {
  CATS,
  EXPOSURES,
  FP_REASONS,
  FSTATUS,
  RISK,
  RTYPE,
  SUBJECTS,
  docTypeName,
  type Exposure,
  type FindingStatus,
  type FpReason,
  type InfoCategory,
  type InfoSubject,
  type ReviewItemType,
  type RiskLevel,
} from '@/display/rules';
import { pad2 } from '@/lib/format';
import { unitBoxOnPage } from '@/lib/pageBox';
import { rawValueMasker } from '../raw-mask';
import type {
  AnalysisDoc,
  DocLink,
  DocSource,
  EvidenceRef,
  Finding,
  FindingBox,
  FindingLive,
  LinkDocRef,
  RawBundleCheck,
  RawDecision,
  RawFileInfo,
  RawOverall,
  ReviewItem,
} from '../types';

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

/* ---------- 바깥 글 · 목록 한도(최종 흐름 워크플로우 — 연결 · 판정 키 · 묶음 검증) ----------
   백엔드가 만든 값이라도 응답 경계에서 한 번 더 막는다(아주 긴 목록 · 글, 짝 없는 서로게이트).
   - 목록(연결 · 근거 줄 · finding_ids · 판정 목록 · 묶음 검증 규칙)은 **앞 N개만 본다** — 뒤는 읽지도 않는다(시간이 한도에 묶인다).
   - 연결 하나의 서류가 한도를 넘으면 그 연결을 버린다(모양이 틀린 연결 — 백엔드는 늘 서류 2개).
   - 화면 · 보고서 글(연결 title · fields · basis · missing · check, 판정 글)은 **한 길(safeText)** 만 지난다:
     자르지 않은 원래 글 전체 → 원문 값 가리기(mask — 있으면) → 최종 규칙(finalText: 짝 없는 서로게이트 → U+FFFD,
     MAX_TEXT 코드 포인트를 넘으면 **통째로 버림**). 글을 자르지 않는다 — 잘린 자리에서 원문 값 조각이 가려지지 않고 남거나,
     가린 결과가 한도 · 서로게이트 규칙을 벗어나는 일이 없게(V-T4-2 F1). 버린 글은 '', 목록 항목이면 그 항목을 버린다.
   - 식별자(identifier — 계약 id · 화면 번호 · 서류 종류 코드)는 바꾸지 않는다: 비었거나 MAX_ID 코드 포인트를 넘거나
     짝 없는 서로게이트가 있으면 그 항목(연결 · 목록 항목)을 버린다(바꾼 id 는 다른 것을 가리킬 수 있으므로). */

/** 연결은 앞 200개만 본다(백엔드 서류 대조는 기준 하나에 대상 50개 한도 — MAX_LINK_TARGETS) */
export const MAX_LINKS = 200;
/** 연결 하나의 서류 수 한도 — 넘으면 그 연결을 버린다(백엔드는 늘 기준 · 대상 2개) */
export const MAX_LINK_DOCS = 10;
/** 연결 서류 하나의 finding_ids 는 앞 50개만(백엔드는 0~1개) */
export const MAX_LINK_FINDING_IDS = 50;
/** 연결 근거 줄은 앞 20줄만(백엔드는 0~1줄) */
export const MAX_LINK_BASIS = 20;
/** 옛 판정 키 목록(서류 종류 · 정보 종류 · 검토 사유)은 앞 50개만(백엔드 MAX_DECISION_ITEMS 와 같다) */
export const MAX_DECISION_ITEMS = 50;
/** 설정 60 판정 목록(서류 종류 · 등급별 항목 토큰 · 검토 사유)은 앞 500개만(백엔드 V2_MAX_DECISION_ITEMS 와 같다 — 옛 50 한도는 묶음에서 넘을 수 있다) */
export const MAX_V2_DECISION_ITEMS = 500;
/** 묶음 검증 규칙은 앞 200개만 센다(백엔드 MAX_CHECKS 와 같다) */
export const MAX_BUNDLE_CHECKS = 200;
/** 화면 · 보고서 글 코드 포인트 한도(백엔드 MAX_DECISION_VALUE_LENGTH 와 같다) — 가린 결과가 넘으면 그 글을 통째로 버린다 */
export const MAX_TEXT = 2000;
/**
 * 원래 글이 이 코드 단위 수를 넘으면 가리기 전에 통째로 버린다('' — 아무것도 보이지 않으므로 원문이 새지 않는다).
 * 가리기 시간(글 길이 × 원문 값 수)을 한도에 묶는다. MAX_TEXT 의 10배라 한도 안에 들 수 있는 글은 모두 가려 본다.
 */
export const MAX_TEXT_SOURCE = 20_000;
/** 식별자 코드 포인트 한도(백엔드 MAX_NAME_LENGTH 와 같다) — 넘으면 그 항목을 버린다 */
export const MAX_ID = 200;

const isHighSurrogate = (c: number): boolean => c >= 0xd800 && c <= 0xdbff;
const isLowSurrogate = (c: number): boolean => c >= 0xdc00 && c <= 0xdfff;
/** 짝 없는 서로게이트(u 플래그 — 짝이 맞는 쌍은 한 코드 포인트라 걸리지 않는다) */
const LONE_SURROGATE = /[\uD800-\uDFFF]/gu;

/** 원문 값 바꾸기 함수(raw-mask.ts rawValueMasker — 탐지 항목 원문 값 → masked) */
export type Masker = (text: string) => string;

/**
 * 최종 규칙 — 짝 없는 서로게이트는 U+FFFD, MAX_TEXT 코드 포인트를 넘으면 통째로 버린다('' — 자르지 않는다).
 * 한 번 훑고(넘는 순간 멈춘다), 바꿀 것이 없으면 받은 글을 그대로 돌려준다. U+FFFD 는 한 코드 포인트라 길이는 그대로다.
 */
export function finalText(s: string): string {
  let n = 0;
  let lone = false;
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (isHighSurrogate(c) && i + 1 < s.length && isLowSurrogate(s.charCodeAt(i + 1))) i++;
    else if (isHighSurrogate(c) || isLowSurrogate(c)) lone = true;
    if (++n > MAX_TEXT) return '';
  }
  return lone ? s.replace(LONE_SURROGATE, '�') : s;
}

/**
 * 바깥 글 → 화면 · 보고서 글 — 연결 글 · 판정 글 · 보고서 사유가 모두 지나는 한 길. 문자열이 아니면 ''.
 * 원래 글이 MAX_TEXT_SOURCE 코드 단위를 넘으면 가리기 전에 통째로 버린다(''). 그 밖은
 * **자르지 않은 원래 글 전체**에 가리기(mask — 있으면) → (trim) → 최종 규칙(finalText). 결과는 늘 MAX_TEXT 코드 포인트 이하이고
 * 짝 없는 서로게이트가 없으며, 원문 값을 가린 뒤에만 길이를 본다(잘린 원문 조각이 남지 않는다).
 */
export function safeText(v: unknown, mask?: Masker | null, trim = false): string {
  if (typeof v !== 'string' || v.length > MAX_TEXT_SOURCE) return '';
  const masked = mask ? mask(v) : v;
  return finalText(trim ? masked.trim() : masked);
}

/** 식별자 — 비지 않은 문자열이고 MAX_ID 코드 포인트 이하 · 짝 없는 서로게이트 없음이면 그대로, 아니면 null(그 항목을 버린다) */
export function identifier(v: unknown): string | null {
  if (typeof v !== 'string' || !v) return null;
  let n = 0;
  for (let i = 0; i < v.length; i++) {
    const c = v.charCodeAt(i);
    if (isHighSurrogate(c) && i + 1 < v.length && isLowSurrogate(v.charCodeAt(i + 1))) i++;
    else if (isHighSurrogate(c) || isLowSurrogate(c)) return null;
    if (++n > MAX_ID) return null;
  }
  return v;
}

/** 배열의 앞 max 개(배열이 아니면 null) — 뒤는 읽지 않는다 */
function head(v: unknown, max: number): unknown[] | null {
  return Array.isArray(v) ? v.slice(0, max) : null;
}

/* ---------- 위험도 판정 키 · 묶음 검증(최종 흐름 워크플로우) ---------- */

/** 판정 글 하나 — safeText(가리기 → 다듬기 → 최종 규칙)의 결과가 비지 않으면 그 글, 아니면 null(못 읽음 · 버림) */
function text(v: unknown, mask?: Masker | null): string | null {
  const s = safeText(v, mask, true);
  return s ? s : null;
}

/** 판정 글 목록 — 배열이 아니면 null(못 읽음), 배열이면 앞 max 개 중 text 가 비지 않은 것만(버린 글은 그 항목을 버림) */
function textList(v: unknown, mask: Masker | null | undefined, max: number): string[] | null {
  const items = head(v, max);
  if (!items) return null;
  const out: string[] = [];
  for (const x of items) {
    const s = text(x, mask);
    if (s !== null) out.push(s);
  }
  return out;
}

/** 식별자 목록(서류 종류 코드) — 배열이 아니면 null, 배열이면 앞 max 개 중 다듬은 값이 식별자인 것만 */
function idList(v: unknown, max: number): string[] | null {
  const items = head(v, max);
  if (!items) return null;
  const out: string[] = [];
  for (const x of items) {
    const s = identifier(typeof x === 'string' ? x.trim() : null);
    if (s !== null) out.push(s);
  }
  return out;
}

/**
 * result.decision → RawDecision. 객체가 아니면 null(옛 결과 · 못 읽음). 모양은 응답으로 가른다:
 * high_risk_items 키가 자기 속성이면 설정 60 의 키 8개(shape 'v2' — 목록 한도 MAX_V2_DECISION_ITEMS), 아니면 옛 키 5개(위험도_판정 본문 — 한도 MAX_DECISION_ITEMS).
 * 글은 모두 safeText 를 지난다. mask 가 없으면 원래 글(상세 판정 표 — 최종 규칙만), 있으면 원문 값을 가린 글
 * (보고서 · 내보내기의 주요 위험 사유 — 자르지 않은 응답 값에서 바로 만든다).
 */
export function readDecision(result: unknown, mask?: Masker | null): RawDecision | null {
  if (!isObj(result) || !isObj(result.decision)) return null;
  const d = result.decision;
  if (own(d, 'high_risk_items')) {
    return {
      shape: 'v2',
      riskLevel: text(d.risk_level, mask),
      documentTypes: idList(d.document_types, MAX_V2_DECISION_ITEMS),
      highRiskItems: textList(d.high_risk_items, mask, MAX_V2_DECISION_ITEMS),
      mediumRiskItems: textList(d.medium_risk_items, mask, MAX_V2_DECISION_ITEMS),
      lowRiskItems: textList(d.low_risk_items, mask, MAX_V2_DECISION_ITEMS),
      reviewReasons: textList(d.review_reasons, mask, MAX_V2_DECISION_ITEMS),
      recommendedAction: text(d.recommended_action, mask),
      reason: text(d.reason, mask),
    };
  }
  return {
    riskLevel: text(d.risk_level, mask),
    documentTypes: idList(d.document_types, MAX_DECISION_ITEMS),
    sensitiveCategories: textList(d.sensitive_categories, mask, MAX_DECISION_ITEMS),
    reviewReasons: textList(d.review_reasons, mask, MAX_DECISION_ITEMS),
    reason: text(d.reason, mask),
  };
}

/** 묶음 검증 판정 값 */
const VERDICTS = ['green', 'yellow', 'red'] as const;

/**
 * result.bundle_check → RawBundleCheck. 객체가 아니면 null(옛 결과 · 못 읽음).
 * 실패 규칙 = checks 의 앞 MAX_BUNDLE_CHECKS 개 중 status 가 'fail' 인 객체.
 */
export function readBundleCheck(result: unknown): RawBundleCheck | null {
  if (!isObj(result) || !isObj(result.bundle_check)) return null;
  const b = result.bundle_check;
  let failed = 0;
  for (const c of head(b.checks, MAX_BUNDLE_CHECKS) ?? []) if (isObj(c) && c.status === 'fail') failed++;
  return { verdict: pick<RawBundleCheck['verdict']>(VERDICTS, b.verdict, ''), failed };
}

/**
 * 주요 위험 사유 줄 — 위험도 판정 키가 있으면 읽을 수 있는 판단 근거(reason) + 검토 사유(review_reasons) 줄만
 * (둘 다 없으면 빈 목록 — 보고서는 '-'), 판정 키가 없을 때만 overall 의 위험도 판정 Markdown 줄(옛 결과).
 */
export function riskReasonLines(decision: RawDecision | null, overall: RawOverall | null): string[] {
  if (decision) return [...(decision.reason !== null ? [decision.reason] : []), ...(decision.reviewReasons ?? [])];
  return markdownLines(overall?.text);
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

/* ---------- 검토 기록 덧씌우기 ---------- */

/**
 * 탐지 항목들에 검토 기록(review.findings — 계약 id → 저장 값)을 덧씌운 새 목록.
 * - 그 항목의 계약 id(live.id)가 saved 의 **자기 속성**일 때만 본다(__proto__ · constructor 등 상속 키는 없는 것).
 * - status 는 확인 상태 키, category · subject · exposure 는 목록 값, fp_type 은 오탐 사유 목록 값(아니면 '').
 *   글(fp_note · reclass_note · memo)은 문자열만. 그 밖은 버리고 AI 값 · 기본값을 쓴다.
 * - updated_at 은 서울 시각으로(toTime) — 없거나 읽지 못하면 지금 값(분석 시각) 그대로.
 * - ai · risk · reason · live 와 위치(anchors · boxes)는 그대로 둔다. saved 가 객체가 아니면 그대로 복사한다.
 */
export function overlayFindingReviews(findings: readonly Finding[], saved: unknown, toTime: (value: unknown) => string): Finding[] {
  const table = isObj(saved) ? saved : null;
  return findings.map((f) => {
    const key = f.live?.id;
    const v = table && typeof key === 'string' && own(table, key) ? table[key] : undefined;
    if (!isObj(v)) return f;
    const status: FindingStatus = typeof v.status === 'string' && own(FSTATUS, v.status) ? (v.status as FindingStatus) : 'open';
    const fpType: FpReason | '' = pick<FpReason | ''>(FP_REASONS, v.fp_type, '');
    return {
      ...f,
      status,
      cat: pick(CATS, v.category, f.ai.cat),
      subject: pick(SUBJECTS, v.subject, f.ai.subject),
      exposure: pick(EXPOSURES, v.exposure, f.ai.exposure),
      fpType,
      fpNote: str(v.fp_note),
      reclassNote: str(v.reclass_note),
      memo: str(v.memo),
      updatedAt: toTime(v.updated_at) || f.updatedAt,
    };
  });
}

/* ---------- 검토사항(result.items — 서버가 계산) ---------- */

/** 검토사항 화면 번호 — 'R-' + 숫자 2자리 이상(백엔드 R-01 · R-100). ASCII 숫자만(\d 는 u 플래그 없이 0-9) */
const ITEM_NUMBER = /^R-\d{2,}$/;

/** 서류 안 쪽(1부터) — 정수이고 서류 범위 안이면 그 쪽, 아니면 1쪽 */
function pageInDoc(page: unknown, src: DocSource): number {
  return isInt(page) && page >= src.pageStart && page <= src.pageEnd ? page - src.pageStart + 1 : 1;
}

/** 보이는 서류(계약 index → 처음 서류) Map */
function sourceMap(sources: readonly DocSource[]): Map<number, DocSource> {
  const byIndex = new Map<number, DocSource>();
  for (const src of sources) if (!byIndex.has(src.index)) byIndex.set(src.index, src);
  return byIndex;
}

/** 같은 서류의 탐지 항목 찾기(계약 id 로 — 처음 것) — 다른 서류 · 없는 id · 문자열 아님은 null */
function findingFinder(findings: readonly Finding[]): (id: unknown, docId: string) => Finding | null {
  const byContractId = new Map<string, Finding>();
  for (const f of findings) {
    const key = f.live?.id;
    if (typeof key === 'string' && key && !byContractId.has(key)) byContractId.set(key, f);
  }
  return (id, docId) => {
    if (typeof id !== 'string') return null;
    const f = byContractId.get(id);
    return f && f.docId === docId ? f : null;
  };
}

/**
 * finding_ids 가 가리키는 같은 서류 · 같은 쪽(서류 안) 탐지 항목의 위치 ID 를 차례로(겹치는 위치 ID 는 한 번). 배열이 아니면 [].
 * 이미 본 탐지 계약 id 는 건너뛴다 — 같은 id 가 N번 와도 그 항목의 위치 목록은 한 번만 돈다(id · 위치 수에 선형).
 * max 가 있으면 finding_ids 의 앞 max 개만 본다(연결 — MAX_LINK_FINDING_IDS).
 */
function anchorsOf(ids: unknown, docId: string, page: number, findingOf: (id: unknown, docId: string) => Finding | null, max = Infinity): string[] {
  const anchors: string[] = [];
  if (!Array.isArray(ids)) return anchors;
  const once = new Set<string>();
  const seenIds = new Set<string>();
  const n = Math.min(ids.length, max);
  for (let k = 0; k < n; k++) {
    const fid: unknown = ids[k];
    if (typeof fid !== 'string' || seenIds.has(fid)) continue;
    seenIds.add(fid);
    const f = findingOf(fid, docId);
    if (!f || f.page !== page) continue;
    for (const a of f.anchors) {
      if (once.has(a)) continue;
      once.add(a);
      anchors.push(a);
    }
  }
  return anchors;
}

/**
 * result.items[] → 검토사항(서버 순서 그대로). 예외 없이 읽는다 — 모양이 틀린 항목 · 근거는 건너뛴다.
 * - items 가 배열이 아니면 []. 항목: 객체 · id(비지 않은 문자열) · number(ITEM_NUMBER) · type(RTYPE 자기 키) ·
 *   document_index(보이는 서류 — sources)일 때만. 같은 id · 같은 number 는 처음 받아들인 것만.
 * - findings 는 같은 결과의 탐지 항목(toLiveFindings) — 계약 id(live.id) → 탐지 항목 Map(처음 것)으로 찾는다.
 * - links 는 같은 결과의 문서 간 연결(toLiveLinks) — link_id 가 그 계약 id(live.id)면 그 연결의 화면 번호를 linkId 로.
 */
export function toLiveItems(items: unknown, sources: readonly DocSource[], findings: readonly Finding[], links: readonly DocLink[] = []): ReviewItem[] {
  if (!Array.isArray(items)) return [];
  const byIndex = sourceMap(sources);
  const findingOf = findingFinder(findings);
  const linkNumber = new Map<string, string>();
  for (const l of links) {
    const key = l.live?.id;
    if (typeof key === 'string' && key && !linkNumber.has(key)) linkNumber.set(key, l.id);
  }

  const seenIds = new Set<string>();
  const seenNumbers = new Set<string>();
  const out: ReviewItem[] = [];
  for (const it of items) {
    if (!isObj(it)) continue;
    const { id, number, type, document_index: index } = it;
    if (typeof id !== 'string' || !id || seenIds.has(id)) continue;
    if (typeof number !== 'string' || !ITEM_NUMBER.test(number) || seenNumbers.has(number)) continue;
    if (typeof type !== 'string' || !own(RTYPE, type)) continue;
    if (!isInt(index)) continue;
    const src = byIndex.get(index);
    if (!src) continue;
    seenIds.add(id);
    seenNumbers.add(number);

    const docId = docIdFor(src.index);
    const evidence: EvidenceRef[] = [];
    if (Array.isArray(it.evidence)) {
      for (const ev of it.evidence) {
        if (!isObj(ev) || typeof ev.label !== 'string' || !ev.label) continue;
        const page = pageInDoc(ev.page, src);
        const anchors = anchorsOf(ev.finding_ids, docId, page, findingOf);
        const target = findingOf(ev.finding_id, docId);
        const ref: EvidenceRef = { label: ev.label, docId, page, anchors };
        if (target) ref.findingId = target.id;
        evidence.push(ref);
      }
    }

    const item: ReviewItem = {
      id: number,
      type: type as ReviewItemType,
      title: str(it.title),
      desc: str(it.desc),
      next: str(it.next),
      docId,
      page: pageInDoc(it.page, src),
      evidence,
      resolved: false,
      note: '',
      resolvedAt: '',
      resolvedBy: '',
      live: { id },
    };
    const related = findingOf(it.finding_id, docId);
    if (related) item.findingId = related.id;
    const linkId = typeof it.link_id === 'string' ? linkNumber.get(it.link_id) : undefined;
    if (linkId) item.linkId = linkId;
    out.push(item);
  }
  return out;
}

/* ---------- 문서 간 연결(result.links — 서버가 계산, 읽기 전용) ---------- */

/** 연결 화면 번호 — 'L-' + 숫자 2자리 이상(백엔드 L-01). ASCII 숫자만 */
const LINK_NUMBER = /^L-\d{2,}$/;

/** 연결 결과 상태 */
const LINK_STATUSES = ['confirmed', 'check'] as const;

/**
 * result.links[] → 문서 간 연결(서버 순서 그대로). 예외 없이 읽는다 — 모양이 틀린 연결은 건너뛴다.
 * - links 가 배열이 아니면 []. 앞 MAX_LINKS 개만 본다. 연결: 객체 · id(식별자) · number(식별자 · LINK_NUMBER) ·
 *   status(confirmed · check) · docs(1~MAX_LINK_DOCS 개 — 모든 서류가 객체이고 document_index 가 보이는 서류)일 때만.
 *   같은 id · 같은 number 는 처음 받아들인 것만.
 * - 화면 글(title · 서류 fields · basis(앞 MAX_LINK_BASIS 줄 중 문자열) · missing · check)은 safeText 를 지난다 — 자르지 않은
 *   원래 글 전체에 **원문 값 바꾸기**(이 결과의 탐지 항목 원문 값 → masked)를 먼저 하고, 그 결과에 최종 규칙(서로게이트 → U+FFFD,
 *   MAX_TEXT 를 넘으면 통째로 버림)을 적용한다. 버린 근거 줄은 목록에서 뺀다. 연결 글은 마스킹 값만 담는 계약이라 정상 결과에서는
 *   바뀌지 않고, 원문 값이 섞인 응답이 와도 상세 연결 카드 · 보고서 · 내보내기에 원문(조각 포함)이 나가지 않는다.
 *   mask 는 부르는 쪽이 분석 하나를 읽을 때 한 번 만들어 넘긴다(없으면 여기서 findings 로 만든다).
 *   탐지 항목의 value · id · 위치는 건드리지 않는다.
 * - 판단(decision 등)은 늘 빈 값(읽기 전용).
 * - 서류: { docId, page: 서류 안 쪽(범위 밖 · 정수 아님은 1쪽), fields, anchors: finding_ids(앞 MAX_LINK_FINDING_IDS 개)의 탐지 항목
 *   위치 ID(검토사항 근거와 같은 규칙) }. 탐지 항목 찾기는 Map 이라 연결 · 서류 수에 선형이다.
 */
export function toLiveLinks(links: unknown, sources: readonly DocSource[], findings: readonly Finding[], mask?: Masker): DocLink[] {
  const list = head(links, MAX_LINKS);
  if (!list || list.length === 0) return [];
  const byIndex = sourceMap(sources);
  const findingOf = findingFinder(findings);
  const masker = mask ?? rawValueMasker(findings);
  const shown = (v: unknown): string => safeText(v, masker);

  const seenIds = new Set<string>();
  const seenNumbers = new Set<string>();
  const out: DocLink[] = [];
  for (const l of list) {
    if (!isObj(l)) continue;
    const id = identifier(l.id);
    const number = identifier(l.number);
    const { status } = l;
    if (id === null || seenIds.has(id)) continue;
    if (number === null || !LINK_NUMBER.test(number) || seenNumbers.has(number)) continue;
    if (status !== 'confirmed' && status !== 'check') continue;
    if (!Array.isArray(l.docs) || l.docs.length === 0 || l.docs.length > MAX_LINK_DOCS) continue;

    const docs: LinkDocRef[] = [];
    let ok = true;
    for (const d of l.docs) {
      const src = isObj(d) && isInt(d.document_index) ? byIndex.get(d.document_index) : undefined;
      if (!src || !isObj(d)) {
        // 객체가 아니거나 보이지 않는 서류 — 연결 전체를 버린다
        ok = false;
        break;
      }
      const docId = docIdFor(src.index);
      const page = pageInDoc(d.page, src);
      docs.push({ docId, page, fields: shown(d.fields), anchors: anchorsOf(d.finding_ids, docId, page, findingOf, MAX_LINK_FINDING_IDS) });
    }
    if (!ok) continue;
    seenIds.add(id);
    seenNumbers.add(number);

    const basis: string[] = [];
    for (const b of head(l.basis, MAX_LINK_BASIS) ?? []) {
      const s = shown(b);
      if (s) basis.push(s);
    }
    out.push({
      id: number,
      status: pick(LINK_STATUSES, status, 'check'),
      title: shown(l.title),
      docs,
      basis,
      missing: shown(l.missing),
      check: shown(l.check),
      decision: null,
      decisionNote: '',
      decidedAt: '',
      decidedBy: '',
      live: { id },
    });
  }
  return out;
}

/**
 * 검토사항들에 해결 기록(review.items — 계약 id → 저장 값)을 덧씌운 새 목록.
 * - 그 항목의 계약 id(live.id)가 saved 의 **자기 속성**이고 값이 객체일 때만 본다(__proto__ · constructor 등 상속 키는 없는 것).
 * - resolved 는 값이 정확히 true 일 때만 true('true' · 1 은 false), note · resolved_by 는 문자열만(아니면 ''),
 *   resolved_at 은 서울 시각으로(toTime — 읽지 못하면 '').
 * - 그 밖은 미해결 기본값 그대로. saved 가 객체가 아니면(null · 배열 · 문자열) 그대로 복사한다.
 */
export function overlayItemReviews(items: readonly ReviewItem[], saved: unknown, toTime: (value: unknown) => string): ReviewItem[] {
  const table = isObj(saved) ? saved : null;
  return items.map((it) => {
    const key = it.live?.id;
    const v = table && typeof key === 'string' && own(table, key) ? table[key] : undefined;
    if (!isObj(v)) return it;
    return {
      ...it,
      resolved: v.resolved === true,
      note: str(v.note),
      resolvedAt: toTime(v.resolved_at),
      resolvedBy: str(v.resolved_by),
    };
  });
}

/* ---------- 새 형식 판단 ---------- */

/** 완료 + documents 배열(유효한 서류 1개 이상) + findings 배열이면 공통 계약 결과로 본다 */
export function isDetailReady(status: string, result: unknown, sources: readonly DocSource[]): boolean {
  return status === 'done' && isObj(result) && Array.isArray(result.documents) && sources.length > 0 && Array.isArray(result.findings);
}
