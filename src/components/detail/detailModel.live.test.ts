/* 실제 분석 상세 화면 모델 — 고정 자료(fixtures/done-result.json) + 검토 기록(review) → toAnalysis → 모델 순서로 확인한다. */
import { describe, expect, it } from 'vitest';
import { LOW_CONFIDENCE_NOTE, MAPPING_NOTES, RISK, findingNotes } from '@/display/rules';
import { createService } from '@/services';
import { toAnalysis } from '@/services/api/mapping';
import { analysisOut, contractResult } from '@/services/api/testing';
import type { Analysis } from '@/services/types';
import { READ_ONLY_ACTIONS } from './detailActions';
import {
  MASK_NOTICE_TEXT,
  REVIEW_UNAVAILABLE_TITLE,
  bannerModel,
  detailFacts,
  docModels,
  filePlaceholder,
  findingModel,
  headerModel,
  liveFilePlaceholder,
  resultsModel,
  viewerModel,
  type ViewerMetrics,
} from './detailModel';
import { DETAIL_TABS, createDetailState, planPickFinding, type DetailUiState } from './detailState';
import { FILE_FAILED, fileKind, filePageOf, guideText, isKnownFileMessage, liveDocMeta, pageMissingText, PDF_OPEN_FAILED } from './liveViewerModel';

const M: ViewerMetrics = { width: 760 + 48 + 6, padX: 24, paperW: 760 };

/** 검토 기록이 없는 분석의 review 블록(백엔드 기본값) */
const NEW_REVIEW = { status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, history: [], version: 0 };

/** 완료 + 공통 계약 결과(고정 자료) + 검토 기록(기본: 새 기록, null = 불러오지 못함) — 필요하면 result 를 고친다 */
function liveAnalysis(edit?: (result: Record<string, unknown>) => void, review: unknown = NEW_REVIEW): Analysis {
  const result = contractResult();
  edit?.(result);
  return toAnalysis(analysisOut({ status: 'done', result, upstage_job_id: 'job_test', upstage_status: 'completed', review: structuredClone(review) }));
}

function stateOf(a: Analysis, patch: Partial<DetailUiState> = {}): DetailUiState {
  return { ...createDetailState(a).state, ...patch };
}

function viewer(a: Analysis, patch: Partial<DetailUiState> = {}) {
  const s = stateOf(a, patch);
  return viewerModel(a, s, detailFacts(a, s), M);
}

async function demoAnalysis(id: string): Promise<Analysis> {
  const a = await createService().get(id);
  if (!a) throw new Error('분석 건 없음: ' + id);
  return a;
}

describe('실제 분석 상세 — 고정 자료 → toAnalysis → 화면 모델', () => {
  const a = liveAnalysis();

  it('고정 자료 + 검토 기록은 상세 검토 화면 대상(detailReady) · 검토 가능(live, readOnly 아님)', () => {
    expect(a.raw?.detailReady).toBe(true);
    expect(a.raw?.reviewable).toBe(true);
    expect(a.review).toBe('needed');
    const x = detailFacts(a, stateOf(a));
    expect(x.live).toBe(true);
    expect(x.readOnly).toBe(false);
    expect(x.locked).toBe(false);
  });

  it('처음 상태 — 고위험 미확인 항목(D1-02)을 골라 대출신청서 1쪽(파일 1쪽)', () => {
    const s = stateOf(a);
    expect(s.focus).toEqual({ kind: 'finding', id: 'D1-02' });
    expect(s.docId).toBe('doc-0');
    const v = viewer(a);
    expect(v.hasPage).toBe(true);
    expect(v.blocks).toEqual([]);
    expect(v.live?.filePage).toBe(1);
    expect(v.pageLabel).toBe('1 / 1');
    expect(v.tag.text).toBe('D1-02 · 고유식별정보 · 높음');
  });

  it('파일 기준 쪽 = pageStart + (뷰어 쪽 − 1) — 서류마다', () => {
    a.docs.forEach((d, i) => {
      expect(viewer(a, { docId: d.id, page: 1, focus: null }).live?.filePage).toBe(i + 1);
    });
  });

  it('2쪽짜리 서류 — 뷰어 2쪽은 파일 pageStart + 1, 쪽 이동 라벨은 서류 안 쪽', () => {
    const b = liveAnalysis((r) => {
      const docs = r.documents as { index: number; page_end: number }[];
      docs[0].page_end = 2;
      (r.documents as unknown[]).splice(1, 1); // 동의서(2쪽)를 대출신청서 2쪽으로
      (r.findings as { document_index: number }[]).forEach((f) => {
        if (f.document_index === 1) f.document_index = 0;
      });
    });
    const v2 = viewer(b, { docId: 'doc-0', page: 2, focus: null });
    expect(v2.live?.filePage).toBe(2);
    expect(v2.pageLabel).toBe('2 / 2');
    expect(v2.noNext).toBe(true);
    expect(v2.noPrev).toBe(false);
    // 2쪽 상자 = 동의서 항목(성명 1 + 생년월일 3)
    expect(v2.live?.boxes.map((x) => x.anchor)).toEqual(['D1-10#1', 'D1-11#1', 'D1-11#2', 'D1-11#3']);
    expect(docModels(b, detailFacts(b, stateOf(b)))[0].meta).toBe('2페이지 · 파일 1–2쪽');
  });

  it('지금 쪽 상자 — 이 서류 · 이 쪽 항목만, 항목 순서 · 상자 순서, 위치 ID 는 항목 anchors 와 같다', () => {
    const v = viewer(a, { docId: 'doc-0', page: 1, focus: null });
    const boxes = v.live!.boxes;
    expect(boxes).toHaveLength(14); // 항목 9 — 주소는 단어별 상자 6개
    expect(boxes.every((x) => x.findingId.startsWith('D1-'))).toBe(true);
    expect(boxes.filter((x) => x.findingId === 'D1-05').map((x) => x.anchor)).toEqual(['D1-05#1', 'D1-05#2', 'D1-05#3', 'D1-05#4', 'D1-05#5', 'D1-05#6']);
    const f5 = a.findings.find((f) => f.id === 'D1-05')!;
    expect(boxes.filter((x) => x.findingId === 'D1-05').map((x) => x.points)).toEqual(f5.boxes!.map((b) => b.points));
    expect(boxes.some((x) => x.on || x.tag || x.masked)).toBe(false);
    // 다른 서류에는 다른 상자
    expect(viewer(a, { docId: 'doc-1', page: 1, focus: null }).live!.boxes.map((x) => x.findingId)).toEqual(['D2-01', 'D2-02', 'D2-02', 'D2-02']);
  });

  it('상자 색 — 위험등급 soft · solid(미평가는 회색), 이름은 기존 하이라이트와 같은 꼴', () => {
    const v = viewer(a, { docId: 'doc-0', page: 1, focus: null });
    const name = v.live!.boxes.find((x) => x.anchor === 'D1-01#1')!;
    const rrn = v.live!.boxes.find((x) => x.anchor === 'D1-02#1')!;
    expect(name.vars.soft).toBe(RISK.unrated.soft);
    expect(name.vars.solid).toBe(RISK.unrated.solid);
    expect(rrn.vars.soft).toBe(RISK.high.soft);
    expect(rrn.vars.solid).toBe(RISK.high.solid);
    expect(name.aria).toBe('D1-01 이름 미평가 — 탐지 항목 보기');
    expect(rrn.aria).toBe('D1-02 고유식별정보 높음 — 탐지 항목 보기');
  });

  it('고른 항목 — 그 상자들만 on, 이름표는 첫 상자에만, 고른 색은 그 항목 위험 색', () => {
    const v = viewer(a, { docId: 'doc-0', page: 1, focus: { kind: 'finding', id: 'D1-05' } });
    const on = v.live!.boxes.filter((x) => x.on);
    expect(on.map((x) => x.anchor)).toEqual(['D1-05#1', 'D1-05#2', 'D1-05#3', 'D1-05#4', 'D1-05#5', 'D1-05#6']);
    expect(v.live!.boxes.filter((x) => x.tag).map((x) => x.anchor)).toEqual(['D1-05#1']);
    expect(v.tag.text).toBe('D1-05 · 주소 · 미평가');
    expect(on[0].vars.pc).toBe(RISK.unrated.solid);
    expect(on[0].vars.onBg).toBe(RISK.unrated.focus);
  });

  it('마스킹 미리보기 — 켜면 이 쪽 상자 모두 가림(masked) + 공지, 끄면 원래대로', () => {
    const on = viewer(a, { docId: 'doc-0', page: 1, mask: true });
    expect(on.live!.boxes.every((x) => x.masked)).toBe(true);
    expect(on.notices.map((n) => n.title)).toContain('마스킹 미리보기');
    expect(on.noMask).toBe(false);
    const off = viewer(a, { docId: 'doc-0', page: 1, mask: false });
    expect(off.live!.boxes.some((x) => x.masked)).toBe(false);
    expect(off.notices.map((n) => n.title)).not.toContain('마스킹 미리보기');
  });

  it('마스킹 미리보기 — 항목별 가림: 보이게 고른 항목의 상자만 빠지고, 상자는 가림을 켜고 끄는 버튼(누름 상태 · 이름)', () => {
    const v = viewer(a, { docId: 'doc-0', page: 1, focus: null, mask: true, maskPick: { 'D1-05': false } });
    expect(v.maskPicking).toBe(true);
    const boxes = v.live!.boxes;
    expect(boxes.filter((x) => !x.masked).map((x) => x.anchor)).toEqual(['D1-05#1', 'D1-05#2', 'D1-05#3', 'D1-05#4', 'D1-05#5', 'D1-05#6']);
    expect(boxes.every((x) => x.pressed === x.masked)).toBe(true);
    expect(boxes.find((x) => x.anchor === 'D1-02#1')!.aria).toBe('D1-02 고유식별정보 높음 — 가리기');
    expect(v.notices.find((n) => n.title === '마스킹 미리보기')?.text).toBe(MASK_NOTICE_TEXT);
    // 실제 분석 서류의 공지에는 '가린 PDF 내려받기' 버튼
    expect(v.notices.find((n) => n.title === '마스킹 미리보기')?.action).toBe('maskPdf');
    // 미리보기를 끄면 고른 값과 관계없이 가리지 않고 누름 상태도 없다(누르면 항목 고르기)
    const off = viewer(a, { docId: 'doc-0', page: 1, focus: null, mask: false, maskPick: { 'D1-01': true } });
    expect(off.maskPicking).toBe(false);
    expect(off.live!.boxes.some((x) => x.masked || 'pressed' in x)).toBe(false);
    expect(off.live!.boxes.find((x) => x.anchor === 'D1-02#1')!.aria).toBe('D1-02 고유식별정보 높음 — 탐지 항목 보기');
  });

  it('마스킹 미리보기 — 결과 패널: 보이는 행 기준 가림 수와 모두 가림 · 모두 해제, 행마다 가림 여부', () => {
    const s = stateOf(a, { mask: true, maskPick: { 'D1-02': false } });
    const rs = resultsModel(a, s, detailFacts(a, s));
    const n = rs.findings.length;
    expect(rs.maskPick).toEqual({ ids: rs.findings.map((f) => f.id), picked: n - 1, text: '가림 ' + (n - 1) + '/' + n, allOn: false, allOff: false });
    expect(rs.findings.filter((f) => !f.maskPicked).map((f) => f.id)).toEqual(['D1-02']);
    // 현재 문서만 보기 — 그 서류 행만 세고 바꾼다
    const one = stateOf(a, { mask: true, onlyDoc: true, docId: 'doc-1', maskPick: { 'D1-02': false } });
    const rsOne = resultsModel(a, one, detailFacts(a, one));
    const doc1 = a.findings.filter((f) => f.docId === 'doc-1').map((f) => f.id);
    expect(rsOne.maskPick?.ids.slice().sort()).toEqual(doc1.slice().sort());
    expect(rsOne.maskPick).toMatchObject({ picked: doc1.length, allOn: true, allOff: false });
    // 모두 보임이면 '모두 해제'를 막는다
    const none = stateOf(a, { mask: true, maskPick: Object.fromEntries(a.findings.map((f) => [f.id, false])) });
    expect(resultsModel(a, none, detailFacts(a, none)).maskPick).toMatchObject({ picked: 0, allOn: false, allOff: true });
    // 미리보기가 꺼져 있으면 없다
    expect(resultsModel(a, stateOf(a), detailFacts(a, stateOf(a))).maskPick).toBeNull();
  });

  it("위치 없는 항목은 상자에서 빠지고, 고르면 '위치 확인 필요' 공지 — page null(D3-02) · boxes [](D5-03)", () => {
    const d3 = viewer(a, { docId: 'doc-2', page: 1, focus: { kind: 'finding', id: 'D3-02' } });
    expect(d3.live!.boxes.map((x) => x.findingId)).toEqual(['D3-01']);
    const notice = d3.notices.find((n) => n.title.startsWith('위치 확인 필요'))!;
    expect(notice.title).toBe('위치 확인 필요 · D3-02 소득·거래정보');
    expect(notice.text).toContain('1쪽에서 근거 문구 “소득금액: 48,000,000원; 결정세액: 2,150,000원”');
    expect(d3.tag.text).toBe('D3-02 · 소득·거래정보 · 미평가');
    expect(d3.live!.boxes.some((x) => x.tag)).toBe(false);
    const d5 = viewer(a, { docId: 'doc-4', page: 1, focus: { kind: 'finding', id: 'D5-03' } });
    expect(d5.live!.boxes.map((x) => x.findingId)).toEqual(['D5-01', 'D5-02', 'D5-02']);
    expect(d5.notices[0].title).toBe('위치 확인 필요 · D5-03 소득·거래정보');
    // 행 표시
    const rs = resultsModel(a, stateOf(a), detailFacts(a, stateOf(a)));
    expect(rs.findings.find((f) => f.id === 'D3-02')?.noLoc).toBe(true);
    expect(rs.findings.find((f) => f.id === 'D5-03')?.noLoc).toBe(true);
    expect(rs.findings.filter((f) => f.noLoc)).toHaveLength(2);
  });

  it("기타 서류 — '기타 서류 안내' 공지(여러 줄 글자 그대로, 인용 표시만 지움), 상자 없음", () => {
    const v = viewer(a, { docId: 'doc-5', page: 1, focus: null });
    expect(v.live?.other).toBe(true);
    expect(v.live?.filePage).toBe(6);
    expect(v.live?.boxes).toEqual([]);
    const n = v.notices.find((x) => x.title === '기타 서류 안내')!;
    expect(n.pre).toBe(true);
    expect(n.text).not.toContain('【');
    expect(n.text.split('\n')).toEqual([
      '## 기타 서류 안내',
      '- **예상 서류 종류**: 고객 안내문',
      '- **검토 사유**: 지점 주소·영업시간·방문 안내로 구성되어 있어 대출 서류 5종에 해당하지 않습니다.',
      '- **담당자 조치**: 기타/안내문서로 분류하고 필요하면 별도로 보관합니다.',
    ]);
    // 추출 서류에는 없다
    expect(viewer(a, { docId: 'doc-0', page: 1 }).notices.some((x) => x.title === '기타 서류 안내')).toBe(false);
    // 안내가 비면 대체 문구
    const b = liveAnalysis((r) => {
      (r.documents as { other_guide: unknown }[])[5].other_guide = null;
    });
    expect(viewer(b, { docId: 'doc-5', page: 1 }).notices.find((x) => x.title === '기타 서류 안내')?.text).toContain('기타 서류로 분류했습니다');
  });

  it("문서 목록 메타 — '1페이지 · 파일 n쪽'(묶음 파일 크기를 서류마다 보이지 않음)", () => {
    const docs = docModels(a, detailFacts(a, stateOf(a)));
    expect(docs.map((d) => d.title)).toEqual(['대출신청서', '동의서', '소득 증빙', '위임장', '채무내역', '기타']);
    expect(docs.map((d) => d.meta)).toEqual(['1페이지 · 파일 1쪽', '1페이지 · 파일 2쪽', '1페이지 · 파일 3쪽', '1페이지 · 파일 4쪽', '1페이지 · 파일 5쪽', '1페이지 · 파일 6쪽']);
    expect(docs.every((d) => !d.meta.includes('KB'))).toBe(true);
    expect(docs.map((d) => d.nFind)).toEqual([9, 2, 2, 3, 3, 0]);
  });

  it('머리글 — 위험등급 높음(분석 위험도) · 문서 6개 · 6페이지 · 검토 필요, 검토 완료 버튼 켜짐', () => {
    const h = headerModel(a, detailFacts(a, stateOf(a)));
    expect(h.risk).toBe('high');
    expect(h.docCount).toBe(6);
    expect(h.pageTotalText).toBe('6페이지');
    expect(h.review).toBe('needed');
    expect(h.readOnly).toBe(false);
    expect(h.showComplete).toBe(true);
    expect(h.showReopen).toBe(false);
    expect(h.noComplete).toBe(false);
    expect(h.completeTitle).toBe('검토를 마치고 결과를 기록합니다');
    expect(h.noReport).toBe(false);
  });

  it('상태 띠 — 검토 완료 전에는 띠가 없다(읽기 전용 띠 없음)', () => {
    expect(bannerModel(a, detailFacts(a, stateOf(a)))).toBeNull();
  });

  it("결과 패널 — 탭은 탐지 항목 · 검토 필요 · 분석 요약(옛 결과는 검토사항 0개), 검토 메모 버튼 켜짐, 등급은 받은 값(미평가 17 · 높음 2)", () => {
    const s = stateOf(a);
    const rs = resultsModel(a, s, detailFacts(a, s));
    expect(rs.tabs.map((t) => [t.value, t.label, t.count])).toEqual([
      ['findings', '탐지 항목', 19],
      ['review', '검토 필요', 0],
      ['summary', '분석 요약', undefined],
    ]);
    expect(rs.items).toEqual([]);
    expect(rs.readOnly).toBe(false);
    expect(rs.locked).toBe(false);
    expect(rs.memoPreview).toBe('아직 작성한 메모가 없습니다.');
    expect(rs.memoBtn).toBe('작성');
    expect(rs.findings).toHaveLength(19);
    expect(rs.findings.filter((f) => f.risk.key === 'unrated')).toHaveLength(17);
    expect(rs.findings.filter((f) => f.risk.key === 'high').map((f) => f.id)).toEqual(['D1-02', 'D4-02']);
    expect(rs.chips.find((c) => c.value === 'high')?.count).toBe(2);
  });

  it("펼친 행 — 적용 규칙이 없으면 줄을 빼고(hasRule false), 근거 문구 = 원문 값, 분류 확인 필요 · 인식 신뢰도 낮음 안내", () => {
    const f = (id: string) => findingModel(a, a.findings.find((x) => x.id === id)!, null);
    const d6 = f('D1-06'); // needs_review · low
    expect(d6.hasRule).toBe(false);
    expect(d6.rule).toBe('');
    expect(d6.evidence).toBe('직장명: (주)한빛테크; 부서: 개발팀; 직위: 대리; 입사일: 2019년 3월 4일');
    expect(d6.notes).toEqual([MAPPING_NOTES.needs_review, LOW_CONFIDENCE_NOTE]);
    expect(f('D1-09').notes).toEqual([MAPPING_NOTES.unknown, LOW_CONFIDENCE_NOTE]); // unknown · low
    expect(f('D1-08').notes).toEqual([LOW_CONFIDENCE_NOTE]); // ok · low
    expect(f('D1-01').notes).toEqual([]); // ok · high
    expect(f('D5-03').notes).toEqual([MAPPING_NOTES.unknown]); // unknown · null
    expect(f('D1-02').reason).toContain('주민등록번호 13자리');
    expect(f('D1-01').where).toBe('대출신청서 · 1쪽');
  });

  it('READ_ONLY_ACTIONS(검토 기록을 불러오지 못했을 때) — 모두 아무것도 하지 않는다', () => {
    for (const fn of Object.values(READ_ONLY_ACTIONS)) expect((fn as (x?: string) => unknown)('D1-01')).toBeUndefined();
  });

  it('원문 자리 화면 — 받는 중 · 실패(다시 시도) · 쪽이 파일에 없음 · 그릴 수 있음', () => {
    expect(liveFilePlaceholder({ status: 'loading' }, 1)).toMatchObject({ tone: 'run', spin: true, skeleton: true, action: null });
    const err = liveFilePlaceholder({ status: 'error', message: '원본 파일을 받지 못했습니다. 잠시 후 다시 시도해 주세요.' }, 1)!;
    expect(err.tone).toBe('err');
    expect(err.text).toBe('원본 파일을 받지 못했습니다. 잠시 후 다시 시도해 주세요.');
    expect(err.action).toMatchObject({ key: 'retryFile', label: '다시 시도', disabled: false });
    expect(filePlaceholder({ status: 'error', message: '' }).text).toBe(FILE_FAILED);
    expect(liveFilePlaceholder({ status: 'ready', pageCount: 6 }, 6)).toBeNull();
    const missing = liveFilePlaceholder({ status: 'ready', pageCount: 6 }, 7)!;
    expect(missing.text).toBe(pageMissingText(7, 6));
    expect(missing.action).toBeNull();
  });
});

describe('그릴 수 없는 상자(쪽과 전혀 겹치지 않음) — 이름표 · 스크롤 · 위치 확인 필요가 그린 상자와 같은 기준', () => {
  type RawFinding = { field: string; boxes: unknown[] };
  const OFF = [{ x: 2, y: 2 }, { x: 3, y: 2 }, { x: 3, y: 3 }, { x: 2, y: 3 }];
  const findingOf = (r: Record<string, unknown>, field: string) => (r.findings as RawFinding[]).find((f) => f.field === field)!;

  it('첫 상자는 쪽 밖, 나머지 정상 — 첫 번째로 그릴 수 있는 상자가 #1 · 이름표 · 스크롤 대상', () => {
    const original = (contractResult().findings as RawFinding[]).find((f) => f.field === 'applicant_address')!.boxes;
    const a = liveAnalysis((r) => findingOf(r, 'applicant_address').boxes.unshift(OFF));
    const f5 = a.findings.find((f) => f.id === 'D1-05')!;
    expect(f5.anchors).toEqual(['D1-05#1', 'D1-05#2', 'D1-05#3', 'D1-05#4', 'D1-05#5', 'D1-05#6']);
    expect(f5.boxes!.map((b) => b.points)).toEqual(original);
    const focus = { kind: 'finding' as const, id: 'D1-05' };
    const v = viewer(a, { docId: 'doc-0', page: 1, focus });
    const mine = v.live!.boxes.filter((x) => x.findingId === 'D1-05');
    expect(mine).toHaveLength(6);
    expect(mine.every((x) => x.on)).toBe(true);
    expect(mine.filter((x) => x.tag).map((x) => x.anchor)).toEqual(['D1-05#1']);
    expect(mine[0].points).toEqual(original[0]);
    // 스크롤 대상 — 처음 열기 · 행 고르기 모두 첫 번째로 그릴 수 있는 상자
    expect(createDetailState(a, { focus }).plan.viewer).toBe('D1-05#1');
    expect(planPickFinding(stateOf(a), a, 'D1-05', {}, false)?.viewer).toBe('D1-05#1');
    expect(findingModel(a, f5, null).noLoc).toBe(false);
  });

  it("모든 상자가 쪽 밖 — 위치 없음(anchors []): 행 '위치 확인 필요' · 뷰어 공지 · 상자 · 이름표 없음", () => {
    const a = liveAnalysis((r) => {
      findingOf(r, 'applicant_name').boxes = [OFF, [{ x: -0.5, y: 0.1 }, { x: -0.2, y: 0.2 }]];
    });
    const f1 = a.findings.find((f) => f.id === 'D1-01')!;
    expect(f1.anchors).toEqual([]);
    expect(f1.boxes).toEqual([]);
    expect(findingModel(a, f1, null).noLoc).toBe(true);
    const v = viewer(a, { docId: 'doc-0', page: 1, focus: { kind: 'finding', id: 'D1-01' } });
    expect(v.live!.boxes.some((x) => x.findingId === 'D1-01')).toBe(false);
    expect(v.live!.boxes.some((x) => x.tag)).toBe(false);
    expect(v.notices[0].title).toBe('위치 확인 필요 · D1-01 이름');
    expect(planPickFinding(stateOf(a), a, 'D1-01', {}, false)?.viewer).toBe('__top');
  });
});

describe('실제 분석 — 검토 완료 뒤 · 검토 기록을 불러오지 못함', () => {
  const DONE_REVIEW = {
    ...NEW_REVIEW,
    status: 'done',
    reviewer: '김민지',
    reviewed_at: '2026-11-03T01:20:00+00:00',
    completion_note: '남은 항목 없음',
    memo: '검토 메모\n둘째 줄',
    memo_at: '2026-11-03T01:10:00+00:00',
    version: 3,
  };

  it("검토 완료 — 잠김, '검토 다시 열기', 검토 완료 띠(검토자 · 서울 시각)에 데모와 같은 '보고서 보기'", () => {
    const a = liveAnalysis(undefined, DONE_REVIEW);
    const s = stateOf(a);
    const x = detailFacts(a, s);
    expect(a.review).toBe('done');
    expect(x.locked).toBe(true);
    expect(x.readOnly).toBe(false);
    const h = headerModel(a, x);
    expect(h.showComplete).toBe(false);
    expect(h.showReopen).toBe(true);
    const b = bannerModel(a, x);
    expect(b?.variant).toBe('done');
    expect(b?.title).toBe('검토 완료 · 김민지 · 2026.11.03 10:20');
    expect(b?.actions).toEqual([{ key: 'openReport', label: '보고서 보기', disabled: false }]);
    const rs = resultsModel(a, s, x);
    expect(rs.locked).toBe(true);
    expect(rs.memoPreview).toBe('검토 메모 둘째 줄');
    expect(rs.memoBtn).toBe('수정');
  });

  it("검토 기록을 불러오지 못함(review null) — readOnly: 검토 완료 버튼 막힘 · title 만 '검토 기록을 불러오지 못했습니다', 띠 없음", () => {
    const a = liveAnalysis(undefined, null);
    expect(a.raw?.detailReady).toBe(true);
    expect(a.raw?.reviewable).toBe(false);
    expect(a.review).toBe('none');
    const s = stateOf(a);
    const x = detailFacts(a, s);
    expect(x.live).toBe(true);
    expect(x.readOnly).toBe(true);
    const h = headerModel(a, x);
    expect(h.readOnly).toBe(true);
    expect(h.showComplete).toBe(true);
    expect(h.noComplete).toBe(true);
    expect(h.completeTitle).toBe(REVIEW_UNAVAILABLE_TITLE);
    expect(REVIEW_UNAVAILABLE_TITLE).toBe('검토 기록을 불러오지 못했습니다');
    expect(bannerModel(a, x)).toBeNull();
    const rs = resultsModel(a, s, x);
    expect(rs.readOnly).toBe(true);
    expect(rs.tabs.map((t) => t.value)).toEqual(['findings', 'review', 'summary']);
    expect(rs.itemsLocked).toBe(true);
    expect(rs.memoPreview).toBe('아직 작성한 메모가 없습니다.');
  });

  it('review 키가 없는 옛 응답도 불러오지 못함과 같다', () => {
    const a = toAnalysis(analysisOut({ status: 'done', result: contractResult() }));
    expect(a.raw?.reviewable).toBe(false);
    expect(detailFacts(a, stateOf(a)).readOnly).toBe(true);
  });
});

describe('데모 분석은 그대로 — 읽기 전용 · 원본 파일 갈래를 타지 않는다', () => {
  it('데모 A1 — readOnly false, 뷰어 live null, 결과 탭 3개, 메모 · 띠 · 머리글 그대로', async () => {
    const a = await demoAnalysis('A1');
    const s = stateOf(a);
    const x = detailFacts(a, s);
    expect(x.live).toBe(false);
    expect(x.readOnly).toBe(false);
    expect(viewerModel(a, s, x, M).live).toBeNull();
    expect(resultsModel(a, s, x).tabs.map((t) => t.value)).toEqual([...DETAIL_TABS]);
    expect(resultsModel(a, s, x).readOnly).toBe(false);
    expect(headerModel(a, x).readOnly).toBe(false);
    expect(headerModel(a, x).completeTitle).toBe('검토를 마치고 결과를 기록합니다');
    expect(bannerModel(a, x)).toBeNull();
    expect(docModels(a, x)[0].meta).toBe('2페이지 · 1.2MB');
    const f = findingModel(a, a.findings[0], null);
    expect(f.hasRule).toBe(true);
    expect(f.notes).toEqual([]);
  });

  it("데모 A5(검토 완료) — 검토 완료 띠에 '보고서 보기'가 그대로 있다", async () => {
    const a = await demoAnalysis('A5');
    const x = detailFacts(a, stateOf(a));
    expect(x.live).toBe(false);
    expect(x.locked).toBe(true);
    const b = bannerModel(a, x);
    expect(b?.variant).toBe('done');
    expect(b?.actions).toEqual([{ key: 'openReport', label: '보고서 보기', disabled: false }]);
  });
});

describe('실제 분석 원문 도우미(liveViewerModel)', () => {
  it('fileKind — MIME 우선, 없으면 확장자', () => {
    expect(fileKind('application/pdf', 'x.png')).toBe('pdf');
    expect(fileKind('image/png', '')).toBe('image');
    expect(fileKind('IMAGE/JPEG', '')).toBe('image');
    expect(fileKind('text/html', 'a.pdf')).toBe('unknown');
    expect(fileKind('', 'a.PDF')).toBe('pdf');
    expect(fileKind('', 'a.jpeg')).toBe('image');
    expect(fileKind('', 'a.gif')).toBe('unknown');
    expect(fileKind('', '')).toBe('unknown');
  });

  it('filePageOf — 서류 범위 안으로', () => {
    expect(filePageOf({ pageStart: 3, pageEnd: 4 }, 1)).toBe(3);
    expect(filePageOf({ pageStart: 3, pageEnd: 4 }, 2)).toBe(4);
    expect(filePageOf({ pageStart: 3, pageEnd: 4 }, 9)).toBe(4);
    expect(filePageOf({ pageStart: 3, pageEnd: 4 }, 0)).toBe(3);
    expect(filePageOf({ pageStart: 3, pageEnd: 4 }, NaN)).toBe(3);
  });

  it('liveDocMeta — 한 쪽 · 여러 쪽', () => {
    expect(liveDocMeta({ pageStart: 3, pageEnd: 3 })).toBe('1페이지 · 파일 3쪽');
    expect(liveDocMeta({ pageStart: 3, pageEnd: 5 })).toBe('3페이지 · 파일 3–5쪽');
  });

  it('guideText — 줄바꿈 유지(CRLF · CR), 인용 표시 지움, 줄 끝 공백 · 빈 줄 정리, 문자열 아니면 ""', () => {
    expect(guideText('## 제목\r\n- 가【†1】  \r\n\r\n\r\n\r- 나【3†source】')).toBe('## 제목\n- 가\n\n- 나');
    expect(guideText('<b>그대로</b>')).toBe('<b>그대로</b>');
    expect(guideText(null)).toBe('');
    expect(guideText(3)).toBe('');
  });

  it('isKnownFileMessage — 고정 문구만', () => {
    expect(isKnownFileMessage(PDF_OPEN_FAILED)).toBe(true);
    expect(isKnownFileMessage(FILE_FAILED)).toBe(true);
    expect(isKnownFileMessage('https://storage.example.test/x?token=1')).toBe(false);
  });

  it('findingNotes — 데모(live 없음)는 []', () => {
    expect(findingNotes(undefined)).toEqual([]);
    expect(findingNotes({ mappingStatus: 'ok', confidence: 'high' })).toEqual([]);
    expect(findingNotes({ mappingStatus: 'needs_review', confidence: null })).toEqual([MAPPING_NOTES.needs_review]);
  });
});
