/* ==========================================================================
   내보내기 파일(CSV · JSON) — 공용 순수 모듈. 원본 buildExport(Main.dc.html 데모 서비스)의 계산을 옮겼다.
   - 데모 코어(src/services/demo/core.ts)와 실제 분석 서비스(src/services/api/service.ts)가 이 함수를 부른다.
     규칙(② display/rules) · 형식 도우미(lib/format) · 타입만 import 한다 — 샘플 · 데모 코어 · 실제 서비스를 import 하지 않는다.
   - 받은 분석의 값을 그대로 쓴다(마스킹된 표시값 masked 만 — 원문 값 evidence · live.value 는 넣지 않는다).
     실제 분석은 부르는 쪽이 원문 값을 지운 안전한 사본(report-safe.ts reportSafeAnalysis)을 넘긴다.
   - CSV: 열 17개(순서 고정 — 실제 분석은 탐지 0건에도 17열, 데모 0건은 원본처럼 '항목ID' 한 열) · BOM · CRLF · 끝 CRLF · 미리보기 = 앞 6줄. '"' ',' LF CR 이 든 칸은 따옴표로 감싸고 '"' 는 두 번.
     수식 막기(OWASP CSV Injection): 글 칸(숫자 칸 '페이지' 제외)이 앞 공백을 뗀 첫 글자가 = + - @ ＝ ＋ － ＠ 이거나
     칸의 첫 글자가 탭 · CR · LF 면 칸 앞에 ' 를 붙이고 따옴표로 감싼다.
   - JSON: 2칸 들여쓰기 · 미리보기 = 앞 16줄. 데모는 원본 최상위 키 10개 그대로.
   - 글 정리: 짝 없는 서로게이트를 U+FFFD 로 바꾼 뒤 크기(UTF-8 바이트)를 센다 — 브라우저 Blob 이 실제로 내려받는 바이트와
     text · size 가 같다(Blob 도 짝 없는 서로게이트를 U+FFFD 로 바꿔 인코딩한다). JSON 은 글 값을 먼저 정리한다
     (JSON.stringify 가 짝 없는 서로게이트를 \uXXXX 로 적지 않게 — CSV 와 같은 U+FFFD).
   - 실제 분석(live: true)만 다른 점: 보고서.데모데이터 false, 문서 간 연결이 없으면 최상위 키 '문서간연결' 을 넣지 않는다
     (옛 워크플로우 결과에는 서류 대조가 없다 — '없음'으로 읽히지 않게). 연결이 있으면(최종 흐름 워크플로우) 데모와 같은 자리 ·
     같은 모양으로 넣는다. '검토사항'(서버가 계산한 검토사항)은 데모와 같은 자리 · 같은 모양으로 넣는다.
     그 밖의 키 · 순서 · 하위 키는 데모와 같다.
   - 생성 시각은 부르는 쪽이 'YYYY-MM-DD HH:mm' 으로 준다(데모 = 데모 시계, 실제 = 서울 시각). 파일 이름 = '<brand>_<code>_검토결과…'.
   ========================================================================== */

import { FSTATUS, HKIND, LSTATUS, RTYPE, analysisStatusView, reviewStatusView, analysisRiskView, riskView, type ExportFormat } from '@/display/rules';
import { fmtDT, utf8Len } from '@/lib/format';
import type { Analysis, ExportFile } from './types';

export interface ExportFileOptions {
  /** 파일 이름 앞 · JSON 보고서.서비스 */
  brand: string;
  /** 생성 시각 'YYYY-MM-DD HH:mm' — JSON 보고서.생성시각(fmtDT) */
  generatedAt: string;
  /** 실제 분석 파일인지 */
  live: boolean;
}

/** 탐지 항목 한 줄(열 이름 = 키, 순서 그대로) */
type ExportRow = Record<string, string | number>;

/** CSV 열(탐지 항목이 없을 때도 이 순서) */
export const CSV_COLUMNS = [
  '항목ID',
  '정보종류',
  '세부항목',
  '표시값_마스킹',
  '정보주체',
  '문서',
  '페이지',
  '원문위치',
  '노출상태',
  '위험등급',
  '판단근거',
  '적용규칙',
  '확인상태',
  '담당자메모',
  '최초AI_정보종류',
  '최초AI_정보주체',
  '최초AI_노출상태',
] as const;

/** 짝 없는 서로게이트(u 플래그 — 짝이 맞는 서로게이트 쌍은 한 코드 포인트라 걸리지 않는다) */
const LONE_SURROGATE = /[\uD800-\uDFFF]/gu;

/** 짝 없는 서로게이트 → U+FFFD (브라우저 Blob · TextEncoder 와 같은 결과) */
export function wellFormed(s: string): string {
  return s.replace(LONE_SURROGATE, '�');
}

/** 앞 공백을 뗀 첫 글자가 이것이면 수식으로 읽힌다(전각 포함) */
const FORMULA_LEAD = /^[=+\-@＝＋－＠]/;
/** 칸의 첫 글자가 탭 · CR · LF */
const CONTROL_LEAD = /^[\t\r\n]/;

/** 수식으로 읽힐 수 있는 글 칸인지 */
export function isFormulaLike(s: string): boolean {
  return CONTROL_LEAD.test(s) || FORMULA_LEAD.test(s.trimStart());
}

/** CSV 칸 하나 — 숫자 칸은 그대로, 글 칸은 수식 막기 → 따옴표 규칙 */
export function csvCell(v: string | number | null | undefined): string {
  const s = wellFormed(String(v == null ? '' : v));
  if (typeof v !== 'number' && isFormulaLike(s)) return '"' + ("'" + s).replace(/"/g, '""') + '"';
  return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

/** 분석 → 내보내기 파일 */
export function buildExportFile(a: Analysis, format: ExportFormat, opts: ExportFileOptions): ExportFile {
  const { brand, generatedAt, live } = opts;
  const docT = (id: string) => {
    const d = a.docs.find((x) => x.id === id);
    return d ? d.title || d.name : '';
  };
  const rows: ExportRow[] = a.findings.map((f) => ({
    항목ID: f.id,
    정보종류: f.cat,
    세부항목: f.label,
    표시값_마스킹: f.masked,
    정보주체: f.subject,
    문서: docT(f.docId),
    페이지: f.page,
    원문위치: f.anchors.length ? '확인됨' : '위치 확인 필요',
    노출상태: f.exposure,
    위험등급: riskView(f.risk).label,
    판단근거: f.reason,
    적용규칙: f.rule,
    확인상태: FSTATUS[f.status].label,
    담당자메모: f.memo || '',
    최초AI_정보종류: f.ai.cat,
    최초AI_정보주체: f.ai.subject,
    최초AI_노출상태: f.ai.exposure,
  }));
  const base = brand + '_' + a.code + '_검토결과';

  if (format === 'csv') {
    /* 탐지 0건 — 실제 분석은 같은 17열 머리 줄, 데모는 원본 그대로 '항목ID' 한 열 */
    const cols: string[] = rows.length ? Object.keys(rows[0]) : live ? [...CSV_COLUMNS] : ['항목ID'];
    const lines = [cols.map(csvCell).join(',')].concat(rows.map((r) => cols.map((c) => csvCell(r[c])).join(',')));
    const text = wellFormed('﻿' + lines.join('\r\n') + '\r\n');
    return { format: 'csv', name: base + '_탐지항목.csv', mime: 'text/csv;charset=utf-8', text, size: utf8Len(text), preview: lines.slice(0, 6).join('\n') };
  }

  const obj: Record<string, unknown> = {
    보고서: { 서비스: brand, 생성시각: fmtDT(generatedAt), 데모데이터: !live, 마스킹: '민감한 값은 마스킹된 표시값만 포함' },
    분석: {
      분석ID: a.code,
      분석명: a.name,
      접수일시: fmtDT(a.submittedAt),
      분석상태: analysisStatusView(a.status).label,
      위험등급: analysisRiskView(a.risk).label,
      검토상태: reviewStatusView(a.review).label,
      검토자: a.reviewer || '',
      검토완료시각: a.reviewedAt ? fmtDT(a.reviewedAt) : '',
    },
    대상문서: a.docs.map((d) => ({
      문서: d.title || d.name,
      파일명: d.name,
      형식: d.ext,
      페이지: d.pageCount || (d.pages ? d.pages.length : null),
      처리상태: analysisStatusView(d.status).label,
      오류: d.error || '',
    })),
    주요위험사유: a.riskReasons,
    탐지항목: rows,
  };
  obj.검토사항 = a.items.map((i) => ({ ID: i.id, 유형: RTYPE[i.type].label, 내용: i.title, 상태: i.resolved ? '해결' : '미해결', 처리내용: i.note || '' }));
  if (!live || a.links.length > 0) {
    obj.문서간연결 = a.links.map((l) => ({
      ID: l.id,
      내용: l.title,
      판단: l.decision ? (l.decision === 'linked' ? '연결 맞음' : '연결 아님') : LSTATUS[l.status].label,
      근거: l.basis,
    }));
  }
  obj.권장조치 = a.recs;
  obj.검토메모 = a.memo || '';
  obj.검토이력 = a.history.map((h) => ({ 시각: fmtDT(h.at), 처리자: h.actor, 구분: HKIND[h.kind] || h.kind, 대상: h.target, 내용: h.change, 사유: h.reason || '' }));

  const text = wellFormed(JSON.stringify(obj, (_key, value: unknown) => (typeof value === 'string' ? wellFormed(value) : value), 2));
  return { format: 'json', name: base + '.json', mime: 'application/json', text, size: utf8Len(text), preview: text.split('\n').slice(0, 16).join('\n') };
}
