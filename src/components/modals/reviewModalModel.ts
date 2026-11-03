/* ==========================================================================
   상세 검토 모달 9종 — 화면 모델 · 입력 검사 · 서비스 호출(순수 함수 + 서비스).
   원본: Main.dc.html modalVM(2377–2496, 상세 화면에서 여는 9종) · submitModal(1864–1903) · 마크업 703–755.

   - 모달 값(DetailModal)은 상세 화면 상태(detailState.ts)의 모달 자리 그대로다.
   - 정보 종류 · 정보주체 · 노출 상태 · 오탐 사유 목록과 라벨은 ② 표시 규칙에서만 가져온다.
   - 위험등급 · 최초 탐지 결과는 바꾸지 않는다 — 서비스가 지키고, 화면은 서비스가 준 값을 그대로 보인다.
   - 'error'(분석 오류 내용) 모달은 목록 화면에서만 연다(원본 1935) — 목록의 ErrorModal 이 그린다.
   - 검토 완료 토스트의 '보고서 보기'는 보고서가 있는 분석(데모)에만 붙인다(hasReport) — 실제 분석은 보고서가 아직 없다.
   - 검토 완료 모달은 남은 항목(서비스 pending)을 받은 뒤 연다(pendingGate). 첫 조회가 실패하면 열지 않고
     기존 SAVE_FAILED 를 오류 토스트로 한 번 보인 뒤 모달 자리를 비운다 — 다음 클릭이 새로 조회한다.
     실패를 빈 pending 으로 보지 않는다(남은 항목을 모른 채 완료하지 않게).
   ========================================================================== */

import { CATS, EXPOSURES, FP_REASONS, RTYPE, SUBJECTS, byRisk, riskView, type Exposure, type FpReason, type InfoCategory, type InfoSubject } from '@/display/rules';
import type { ModalWidth } from '@/components/ui';
import type { AnalysisService, Pending } from '@/services/analysis-service';
import type { Analysis, Finding } from '@/services/types';
import { docName } from '@/components/detail/detailModel';
import type { DetailModal } from '@/components/detail/detailState';

/** 메모 · 사유 최대 글자 수(원본 textarea maxLength) */
export const NOTE_MAX = 500;

/** 서비스가 실패했을 때(실제 API) — 원본에는 없는 경우라 새로 둔 문구 */
export const SAVE_FAILED = '저장하지 못했습니다. 잠시 후 다시 시도해 주세요.';

/** 대상 카드(원본 md.tg) — 위험 · 제목 · ID · 마스킹 값 · 설명 줄 */
export interface ModalTargetModel {
  /** 위험등급(서비스 값). 없으면 위험 표시 없음 */
  risk: string | null;
  title: string;
  id: string;
  /** 마스킹 값 — 없으면 줄 없음 */
  value: string | null;
  meta: string;
}

/** 바닥 버튼 동작 */
export type ModalButtonAct = 'close' | 'submit' | 'goPending';

export interface ModalButtonModel {
  label: string;
  act: ModalButtonAct;
  variant: 'primary' | 'secondary';
}

/** 메모 · 사유 입력칸 */
export interface ModalNoteModel {
  label: string;
  /** 라벨 옆 '(필수 · …)' · '(선택)' */
  req: string;
  placeholder: string;
  rows: number;
}

/** 분류 수정 드롭다운 하나 */
export interface EditFieldModel<K extends EditKey = EditKey> {
  key: K;
  title: string;
  value: EditValue[K];
  options: { value: EditValue[K]; label: string; ai: boolean }[];
  /** 지금 값(서비스 값)과 다르게 골랐음 — 옅은 초록 + 강조 테두리 */
  changed: boolean;
}

export interface EditValue {
  cat: InfoCategory;
  subject: InfoSubject;
  exposure: Exposure;
}
export type EditKey = keyof EditValue;

/** 검토 완료 모달 — 남은 항목으로 가는 줄 */
export type PendingGo = { kind: 'item'; id: string } | { kind: 'finding'; id: string } | { kind: 'link'; id: string };

export interface PendingLine {
  id: string;
  label: string;
  go: PendingGo;
}

export interface CompleteModel {
  /** 남은 항목이 있음 */
  any: boolean;
  /** 요약 줄('미확인 탐지 항목 3건 (위험등급 높음 1건 포함)' …) */
  lines: string[];
  /** 남은 항목 바로가기(최대 5개) */
  items: PendingLine[];
  /** 분석 건 위험등급 라벨 */
  riskLabel: string;
}

export interface ReviewModalModel {
  type: DetailModal['type'];
  width: ModalWidth;
  title: string;
  sub: string;
  target: ModalTargetModel | null;
  /** fp: 오탐 사유 목록(② FP_REASONS) */
  reasons: readonly FpReason[] | null;
  /** edit: 드롭다운 3개 + 최초 AI 결과 */
  edit: { fields: [EditFieldModel<'cat'>, EditFieldModel<'subject'>, EditFieldModel<'exposure'>]; aiText: string } | null;
  /** complete: 남은 항목 요약 */
  complete: CompleteModel | null;
  note: ModalNoteModel;
  info: string | null;
  buttons: ModalButtonModel[];
}

const btn = (label: string, act: ModalButtonAct, variant: ModalButtonModel['variant']): ModalButtonModel => ({ label, act, variant });
const CANCEL = btn('취소', 'close', 'secondary');

/** 탐지 항목 대상 카드(원본 fTarget) */
function findingTarget(a: Analysis, f: Finding): ModalTargetModel {
  const d = a.docs.find((x) => x.id === f.docId);
  return { risk: f.risk, title: f.cat + ' · ' + f.label, id: f.id, value: f.masked, meta: f.subject + ' · ' + docName(d) + ' ' + f.page + '쪽 · ' + f.exposure };
}

/** 고른 값이 목록에 없으면 앞에 붙인다(원본 mkMD 의 list) */
function withValue<V extends string>(opts: readonly V[], v: V): readonly V[] {
  return opts.indexOf(v) >= 0 ? opts : [v, ...opts];
}

function editField<K extends EditKey>(key: K, title: string, opts: readonly EditValue[K][], value: EditValue[K], current: EditValue[K], ai: EditValue[K]): EditFieldModel<K> {
  return {
    key,
    title,
    value,
    options: withValue(opts, value).map((o) => ({ value: o, label: o, ai: o === ai })),
    changed: value !== current,
  };
}

/** 검토 완료 모달의 남은 항목 요약(원본 modalVM complete) */
export function completeModel(a: Analysis, p: Pending): CompleteModel {
  const lines: string[] = [];
  const openHigh = p.openF.filter((x) => x.risk === 'high').length;
  if (p.openF.length) lines.push('미확인 탐지 항목 ' + p.openF.length + '건' + (openHigh ? ' (위험등급 높음 ' + openHigh + '건 포함)' : ''));
  if (p.openI.length) lines.push('해결되지 않은 검토사항 ' + p.openI.length + '건');
  if (p.openL.length) lines.push('확인이 필요한 문서 간 연결 ' + p.openL.length + '건');
  const items: PendingLine[] = [
    ...p.openI.map((i) => ({ id: i.id, label: RTYPE[i.type].label + ' · ' + i.title, go: { kind: 'item', id: i.id } as const })),
    ...p.openF
      .slice()
      .sort(byRisk)
      .map((x) => ({ id: x.id, label: riskView(x.risk).label + ' · ' + x.cat + ' · ' + x.label, go: { kind: 'finding', id: x.id } as const })),
    ...p.openL.map((l) => ({ id: l.id, label: '연결 확인 필요 · ' + l.title, go: { kind: 'link', id: l.id } as const })),
  ].slice(0, 5);
  return { any: p.any, lines, items, riskLabel: riskView(a.risk).label };
}

/**
 * 모달 화면 모델(원본 modalVM). 대상(탐지 항목 · 검토사항 · 연결)이 없으면 null(모달을 그리지 않음).
 * complete 는 pending(서비스 조회 결과)이 있어야 한다 — 없으면 null.
 */
export function reviewModalModel(a: Analysis, m: DetailModal, pending: Pending | null): ReviewModalModel | null {
  const base = { type: m.type, width: 'sm' as ModalWidth, target: null, reasons: null, edit: null, complete: null, info: null };
  const note = (label: string, req: string, placeholder: string, rows = 3): ModalNoteModel => ({ label, req, placeholder, rows });
  const getF = (id: string) => a.findings.find((x) => x.id === id) ?? null;
  switch (m.type) {
    case 'fp': {
      const f = getF(m.fid);
      if (!f) return null;
      return {
        ...base,
        title: '오탐으로 표시',
        sub: '이 탐지 결과가 개인정보 · 중요정보가 아니라고 판단한 이유를 남깁니다.',
        target: findingTarget(a, f),
        reasons: FP_REASONS,
        note: note('상세 사유', '(필수 · 검토 이력에 남습니다)', '예: 은행 양식 관리번호로 개인 계좌번호가 아님'),
        info: '오탐으로 표시해도 최초 AI 결과와 위험등급은 기록에 그대로 남습니다.',
        buttons: [CANCEL, btn('오탐으로 표시', 'submit', 'primary')],
      };
    }
    case 'edit': {
      const f = getF(m.fid);
      if (!f) return null;
      return {
        ...base,
        width: 'lg',
        title: '정보 분류 수정',
        sub: '잘못 분류된 정보 종류 · 정보주체 · 노출 상태를 바로잡습니다.',
        target: findingTarget(a, f),
        edit: {
          fields: [
            editField('cat', '정보 종류', CATS, m.cat, f.cat, f.ai.cat),
            editField('subject', '정보주체', SUBJECTS, m.subject, f.subject, f.ai.subject),
            editField('exposure', '노출 상태', EXPOSURES, m.exposure, f.exposure, f.ai.exposure),
          ],
          aiText: f.ai.cat + ' · ' + f.ai.subject + ' · ' + f.ai.exposure,
        },
        note: note('수정 사유', '(필수 · 검토 이력에 남습니다)', '예: 상담 직원 서명란에 적힌 직원 성명'),
        info: '분류를 바꿔도 위험등급은 다시 계산하지 않습니다. 위험등급 재검토가 필요하면 사유에 함께 남겨 주세요.',
        buttons: [CANCEL, btn('수정 저장', 'submit', 'primary')],
      };
    }
    case 'fmemo': {
      const f = getF(m.fid);
      if (!f) return null;
      return {
        ...base,
        title: '항목 메모',
        sub: '이 탐지 항목에 대해 다른 담당자가 알아야 할 내용을 남깁니다.',
        target: findingTarget(a, f),
        note: note('메모', '(선택)', '예: 원본 보관 전 마스킹 사본으로 교체 필요', 4),
        info: '메모는 시각과 함께 검토 이력에 남습니다.',
        buttons: [CANCEL, btn('메모 저장', 'submit', 'primary')],
      };
    }
    case 'memo':
      return {
        ...base,
        width: 'md',
        title: '검토 메모',
        sub: '분석 건 전체에 대한 검토 의견을 남깁니다. 보고서의 ‘검토자 메모’에 표시됩니다.',
        note: note('검토 메모', '(선택)', '검토 의견, 후속 조치, 고객 확인 결과 등을 적습니다.', 6),
        info: '메모는 시각과 함께 검토 이력에 남습니다.',
        buttons: [CANCEL, btn('메모 저장', 'submit', 'primary')],
      };
    case 'restore': {
      const f = getF(m.fid);
      if (!f) return null;
      return {
        ...base,
        title: '오탐 표시 취소',
        sub: '오탐 표시를 취소하고 다시 확인할 항목으로 되돌립니다.',
        target: findingTarget(a, f),
        note: note('취소 사유', '(필수)', '예: 원본 확인 결과 실제 계좌번호로 확인됨'),
        buttons: [btn('닫기', 'close', 'secondary'), btn('오탐 표시 취소', 'submit', 'primary')],
      };
    }
    case 'resolve': {
      const it = a.items.find((x) => x.id === m.rid);
      if (!it) return null;
      const d = a.docs.find((x) => x.id === it.docId);
      return {
        ...base,
        title: '검토사항 해결로 표시',
        sub: '확인한 내용과 처리 결과를 남깁니다.',
        target: { risk: null, title: it.title, id: it.id, value: null, meta: RTYPE[it.type].label + ' · ' + docName(d) + ' ' + it.page + '쪽' },
        note: note('처리 내용', '(필수 · 보고서에 남습니다)', '예: 원본을 확인한 결과 해당 영역에 개인정보 없음'),
        info: '해결로 표시해도 최초 탐지 결과와 위험등급은 바뀌지 않습니다.',
        buttons: [CANCEL, btn('해결로 표시', 'submit', 'primary')],
      };
    }
    case 'link': {
      const l = a.links.find((x) => x.id === m.lid);
      if (!l) return null;
      const yes = m.decision === 'linked';
      return {
        ...base,
        title: yes ? '같은 사람 · 같은 건으로 판단' : '연결 아님으로 판단',
        sub: '판단 근거는 검토 이력과 보고서에 남습니다.',
        target: { risk: null, title: l.title, id: l.id, value: null, meta: '부족한 근거: ' + (l.missing || '없음') },
        note: note('판단 근거', '(필수)', yes ? '예: 고객 통화로 본인 급여계좌임을 확인함' : '예: 이름 외 근거가 없어 연결하지 않음'),
        info: yes
          ? '연결 맞음으로 판단하면 관련 검토사항도 해결로 표시됩니다.'
          : '연결 아님으로 판단하면 두 문서의 정보를 같은 사람의 정보로 보지 않습니다. 관련 검토사항은 해결로 표시됩니다.',
        buttons: [CANCEL, btn('판단 기록', 'submit', 'primary')],
      };
    }
    case 'complete': {
      if (!pending) return null;
      const c = completeModel(a, pending);
      return {
        ...base,
        width: 'md',
        title: '검토 완료',
        sub: a.name,
        complete: c,
        note: c.any
          ? note('검토 완료 메모', '(필수 · 남은 항목이 있습니다)', '예: 판독 불가 영역은 원본 확인 후 보완 예정')
          : note('검토 완료 메모', '(선택)', '보고서에 남길 내용을 적습니다.'),
        buttons: c.any
          ? [btn('남은 항목 확인하기', 'goPending', 'secondary'), btn('남은 항목과 함께 검토 완료', 'submit', 'primary')]
          : [CANCEL, btn('검토 완료', 'submit', 'primary')],
      };
    }
    case 'reopen':
      return {
        ...base,
        title: '검토 다시 열기',
        sub: '검토 상태가 ‘검토 필요’로 바뀝니다. 지금까지의 기록은 그대로 남습니다.',
        note: note('다시 여는 이유', '(필수)', '예: 고객이 추가 서류를 제출해 다시 확인 필요'),
        buttons: [CANCEL, btn('검토 다시 열기', 'submit', 'primary')],
      };
    default: {
      const unknown: never = m;
      void unknown;
      return null;
    }
  }
}

/**
 * 입력 검사(원본 submitModal 의 검사 부분) — 통과하면 ''.
 * complete 는 저장 직전에 다시 받은 pending 으로 검사한다.
 */
export function reviewModalError(a: Analysis, m: DetailModal, pending: Pending | null): string {
  const note = (m.note || '').trim();
  switch (m.type) {
    case 'fp':
      return note.length < 2 ? '오탐으로 판단한 사유를 적어 주세요.' : '';
    case 'edit': {
      const f = a.findings.find((x) => x.id === m.fid);
      if (f && m.cat === f.cat && m.subject === f.subject && m.exposure === f.exposure) return '바꿀 분류를 하나 이상 선택해 주세요.';
      return note.length < 2 ? '수정 사유를 적어 주세요.' : '';
    }
    case 'restore':
      return note.length < 2 ? '오탐 표시를 취소하는 이유를 적어 주세요.' : '';
    case 'resolve':
      return note.length < 2 ? '확인한 내용이나 처리 결과를 적어 주세요.' : '';
    case 'link':
      return note.length < 2 ? '판단 근거를 적어 주세요.' : '';
    case 'complete':
      return pending?.any && note.length < 2 ? '남은 항목이 있어 완료 사유가 필요합니다.' : '';
    case 'reopen':
      return note.length < 2 ? '다시 여는 이유를 적어 주세요.' : '';
    case 'fmemo':
    case 'memo':
      return '';
    default: {
      const unknown: never = m;
      void unknown;
      return '';
    }
  }
}

/** 검토 완료 모달을 열기 전 남은 항목 조회 — open 열기 / wait 기다림 / fail 열지 않음(오류 토스트 한 번 + 모달 닫기) */
export type PendingGate = 'open' | 'wait' | 'fail';

/** 남은 항목 조회 결과(usePending 의 data · error) → 검토 완료 모달을 열지. 받은 값이 있으면(다시 불러오다 실패해도) 연다 */
export function pendingGate(data: Pending | undefined, error: unknown): PendingGate {
  if (data) return 'open';
  return error === undefined ? 'wait' : 'fail';
}

/** 보고서를 열 수 있는 분석인지 — 데모만(실제 분석 Analysis.raw 는 보고서가 아직 없다) */
export function hasReport(a: Analysis): boolean {
  return !a.raw;
}

/** 저장 뒤 토스트 — 원본 문구 그대로. openReport 면 '보고서 보기' 행동을 붙인다 */
export interface ReviewToast {
  text: string;
  openReport?: boolean;
}

/** 서비스 호출 + 토스트 문구(원본 submitModal 의 저장 부분). 검사를 통과한 뒤 부른다. */
export async function applyReviewModal(svc: AnalysisService, a: Analysis, m: DetailModal): Promise<ReviewToast> {
  const note = (m.note || '').trim();
  switch (m.type) {
    case 'fp':
      await svc.markFalsePositive(a.id, m.fid, m.reason, note);
      return { text: '오탐으로 표시했습니다 · ' + m.fid + ' (최초 결과는 이력에 남습니다)' };
    case 'edit':
      await svc.reclassify(a.id, m.fid, { cat: m.cat, subject: m.subject, exposure: m.exposure }, note);
      return { text: '분류를 수정했습니다 · ' + m.fid };
    case 'fmemo':
      await svc.saveFindingMemo(a.id, m.fid, note);
      return { text: '메모를 저장했습니다 · ' + m.fid };
    case 'memo':
      await svc.saveMemo(a.id, note);
      return { text: '검토 메모를 저장했습니다.' };
    case 'restore':
      await svc.restore(a.id, m.fid, note);
      return { text: '오탐 표시를 취소했습니다 · ' + m.fid };
    case 'resolve':
      await svc.resolveItem(a.id, m.rid, note);
      return { text: '검토사항을 해결로 표시했습니다 · ' + m.rid };
    case 'link':
      await svc.decideLink(a.id, m.lid, m.decision, note);
      return { text: '연결 판단을 기록했습니다 · ' + m.lid };
    case 'complete':
      await svc.completeReview(a.id, note);
      return { text: '검토를 완료했습니다 · 목록의 검토 상태와 요약 숫자에 반영했습니다.', openReport: hasReport(a) };
    case 'reopen':
      await svc.reopenReview(a.id, note);
      return { text: '검토를 다시 열었습니다 · 검토 상태가 ‘검토 필요’로 바뀌었습니다.' };
    default: {
      const unknown: never = m;
      void unknown;
      return { text: '' };
    }
  }
}

/* ---------- 바로 바꾸는 동작(모달 없음)의 토스트 — 원본 1803–1807 ---------- */

export const confirmedText = (fid: string) => '탐지 내용을 확인했습니다 · ' + fid;
export const unconfirmedText = (fid: string) => '확인을 취소했습니다 · ' + fid;
export const itemReopenedText = (rid: string) => '검토사항을 다시 열었습니다 · ' + rid;
export const retryFailedText = (message: string) => '다시 분석했지만 실패했습니다 · ' + message;
