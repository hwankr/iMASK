import { describe, expect, it } from 'vitest';
import { CATS, EXPOSURES, FP_REASONS, RTYPE, SUBJECTS, byRisk, riskView } from '@/display/rules';
import { createService } from '@/services';
import type { AnalysisService } from '@/services/analysis-service';
import type { Analysis } from '@/services/types';
import type { DetailModal } from '@/components/detail/detailState';
import { toAnalysis } from '@/services/api/mapping';
import { analysisOut, contractResult } from '@/services/api/testing';
import { applyReviewModal, completeModel, hasReport, pendingGate, reviewModalError, reviewModalModel } from './reviewModalModel';

async function get(svc: AnalysisService, id: string): Promise<Analysis> {
  const a = await svc.get(id);
  if (!a) throw new Error('분석 건 없음: ' + id);
  return a;
}

describe('모달 화면 모델 — 원본 modalVM', () => {
  it('fp — 제목 · 부제 · 대상 카드 · 사유 목록(②) · 필수 사유 · 안내 · 버튼', async () => {
    const svc = createService();
    const a = await get(svc, 'A1');
    const f = a.findings.find((x) => x.id === 'F-01');
    if (!f) throw new Error('F-01 없음');
    const d = a.docs.find((x) => x.id === f.docId);
    const m = reviewModalModel(a, { type: 'fp', fid: 'F-01', reason: FP_REASONS[0], note: '', error: '' }, null);
    expect(m).not.toBeNull();
    expect(m?.title).toBe('오탐으로 표시');
    expect(m?.sub).toBe('이 탐지 결과가 개인정보 · 중요정보가 아니라고 판단한 이유를 남깁니다.');
    expect(m?.width).toBe('sm');
    expect(m?.reasons).toBe(FP_REASONS);
    expect(m?.target).toEqual({
      risk: f.risk,
      title: f.cat + ' · ' + f.label,
      id: 'F-01',
      value: f.masked,
      meta: f.subject + ' · ' + (d?.title || d?.name) + ' ' + f.page + '쪽 · ' + f.exposure,
    });
    expect(m?.note).toEqual({ label: '상세 사유', req: '(필수 · 검토 이력에 남습니다)', placeholder: '예: 은행 양식 관리번호로 개인 계좌번호가 아님', rows: 3 });
    expect(m?.info).toBe('오탐으로 표시해도 최초 AI 결과와 위험등급은 기록에 그대로 남습니다.');
    expect(m?.buttons.map((b) => [b.label, b.act, b.variant])).toEqual([
      ['취소', 'close', 'secondary'],
      ['오탐으로 표시', 'submit', 'primary'],
    ]);
  });

  it('edit — 드롭다운 3개는 ② 목록, 최초 AI 값 표시, 바꾼 칸 표시, 폭 640', async () => {
    const svc = createService();
    const a = await get(svc, 'A1');
    const f = a.findings.find((x) => x.id === 'F-20');
    if (!f) throw new Error('F-20 없음');
    const m = reviewModalModel(a, { type: 'edit', fid: 'F-20', cat: f.cat, subject: '기타', exposure: f.exposure, note: '', error: '' }, null);
    expect(m?.width).toBe('lg');
    expect(m?.title).toBe('정보 분류 수정');
    if (!m?.edit) throw new Error('분류 수정 모델 없음');
    const [cat, subject, exposure] = m.edit.fields;
    expect(cat.options.map((o) => o.value)).toEqual([...CATS]);
    expect(subject.options.map((o) => o.value)).toEqual([...SUBJECTS]);
    expect(exposure.options.map((o) => o.value)).toEqual([...EXPOSURES]);
    expect(cat.options.filter((o) => o.ai).map((o) => o.value)).toEqual([f.ai.cat]);
    expect(subject.options.filter((o) => o.ai).map((o) => o.value)).toEqual([f.ai.subject]);
    expect([cat.title, subject.title, exposure.title]).toEqual(['정보 종류', '정보주체', '노출 상태']);
    expect([cat.changed, subject.changed, exposure.changed]).toEqual([false, f.subject !== '기타', false]);
    expect(m?.edit?.aiText).toBe(f.ai.cat + ' · ' + f.ai.subject + ' · ' + f.ai.exposure);
    expect(m?.note).toMatchObject({ label: '수정 사유', req: '(선택)' }); // 사유는 선택(2026-11-04)
    expect(m?.buttons.map((b) => b.label)).toEqual(['취소', '수정 저장']);
  });

  it('resolve · link · memo · fmemo · restore · reopen — 제목 · 대상 · 버튼', async () => {
    const svc = createService();
    const a = await get(svc, 'A1');
    const it = a.items[0];
    const d = a.docs.find((x) => x.id === it.docId);
    const r = reviewModalModel(a, { type: 'resolve', rid: it.id, note: '', error: '' }, null);
    expect(r?.title).toBe('검토사항 해결로 표시');
    expect(r?.target).toEqual({ risk: null, title: it.title, id: it.id, value: null, meta: RTYPE[it.type].label + ' · ' + (d?.title || d?.name) + ' ' + it.page + '쪽' });
    expect(r?.buttons.map((b) => b.label)).toEqual(['취소', '해결로 표시']);

    const l = a.links[0];
    const yes = reviewModalModel(a, { type: 'link', lid: l.id, decision: 'linked', note: '', error: '' }, null);
    const no = reviewModalModel(a, { type: 'link', lid: l.id, decision: 'unlinked', note: '', error: '' }, null);
    expect(yes?.title).toBe('같은 사람 · 같은 건으로 판단');
    expect(no?.title).toBe('연결 아님으로 판단');
    expect(yes?.target?.meta).toBe('부족한 근거: ' + (l.missing || '없음'));
    expect(yes?.buttons.map((b) => b.label)).toEqual(['취소', '판단 기록']);

    expect(reviewModalModel(a, { type: 'memo', note: '', error: '' }, null)).toMatchObject({ title: '검토 메모', width: 'md', target: null, note: { rows: 6, req: '(선택)' }, info: '메모는 검토 이력에 남습니다.' });
    expect(reviewModalModel(a, { type: 'fmemo', fid: 'F-01', note: '', error: '' }, null)).toMatchObject({ title: '항목 메모', note: { rows: 4, label: '메모' }, info: '메모는 검토 이력에 남습니다.' });
    expect(reviewModalModel(a, { type: 'restore', fid: 'F-01', note: '', error: '' }, null)?.buttons.map((b) => b.label)).toEqual(['닫기', '오탐 표시 취소']);
    expect(reviewModalModel(a, { type: 'reopen', note: '', error: '' }, null)).toMatchObject({ title: '검토 다시 열기', info: null });
  });

  it('대상이 없으면 그리지 않는다 · complete 는 pending 이 있어야 한다', async () => {
    const svc = createService();
    const a = await get(svc, 'A1');
    expect(reviewModalModel(a, { type: 'fp', fid: 'NOPE', reason: FP_REASONS[0], note: '', error: '' }, null)).toBeNull();
    expect(reviewModalModel(a, { type: 'resolve', rid: 'NOPE', note: '', error: '' }, null)).toBeNull();
    expect(reviewModalModel(a, { type: 'complete', note: '', error: '' }, null)).toBeNull();
  });

  it('complete — 남은 항목 요약 줄 · 바로가기(검토사항 → 위험 순 탐지 항목 → 연결, 최대 5개) · 버튼', async () => {
    const svc = createService();
    const a = await get(svc, 'A1');
    const p = await svc.pending('A1');
    expect(p.any).toBe(true);
    const c = completeModel(a, p);
    const high = p.openF.filter((x) => x.risk === 'high').length;
    expect(c.lines[0]).toBe('미확인 탐지 항목 ' + p.openF.length + '건' + (high ? ' (위험등급 높음 ' + high + '건 포함)' : ''));
    if (p.openI.length) expect(c.lines).toContain('해결되지 않은 검토사항 ' + p.openI.length + '건');
    if (p.openL.length) expect(c.lines).toContain('확인이 필요한 문서 간 연결 ' + p.openL.length + '건');
    const expected = [
      ...p.openI.map((i) => i.id),
      ...p.openF
        .slice()
        .sort(byRisk)
        .map((f) => f.id),
      ...p.openL.map((l) => l.id),
    ].slice(0, 5);
    expect(c.items.map((i) => i.id)).toEqual(expected);
    expect(c.items.length).toBeLessThanOrEqual(5);
    expect(c.riskLabel).toBe(riskView(a.risk).label);
    const m = reviewModalModel(a, { type: 'complete', note: '', error: '' }, p);
    expect(m?.sub).toBe(a.name);
    expect(m?.note.req).toBe('(필수 · 남은 항목이 있습니다)');
    expect(m?.buttons.map((b) => [b.label, b.act])).toEqual([
      ['남은 항목 확인하기', 'goPending'],
      ['남은 항목과 함께 검토 완료', 'submit'],
    ]);
    const none = reviewModalModel(a, { type: 'complete', note: '', error: '' }, { openF: [], openI: [], openL: [], any: false });
    expect(none?.note.req).toBe('(선택)');
    expect(none?.buttons.map((b) => b.label)).toEqual(['취소', '검토 완료']);
  });
});

describe('입력 검사 — 원본 submitModal', () => {
  it('필수 사유가 2자 미만이면 원본 문구, 분류 수정은 바뀐 것이 없으면 먼저 오류', async () => {
    const svc = createService();
    const a = await get(svc, 'A1');
    const f = a.findings.find((x) => x.id === 'F-20');
    if (!f) throw new Error('F-20 없음');
    const err = (m: DetailModal, p = null as Parameters<typeof reviewModalError>[2]) => reviewModalError(a, m, p);
    expect(err({ type: 'fp', fid: 'F-01', reason: FP_REASONS[0], note: ' 가 ', error: '' })).toBe('오탐으로 판단한 사유를 적어 주세요.');
    expect(err({ type: 'fp', fid: 'F-01', reason: FP_REASONS[0], note: '관리번호', error: '' })).toBe('');
    expect(err({ type: 'edit', fid: 'F-20', cat: f.cat, subject: f.subject, exposure: f.exposure, note: '충분한 사유', error: '' })).toBe('바꿀 분류를 하나 이상 선택해 주세요.');
    // 분류 수정 사유는 선택 — 바꾼 분류가 있으면 사유가 비어도 통과
    expect(err({ type: 'edit', fid: 'F-20', cat: f.cat, subject: '기타', exposure: f.exposure, note: '', error: '' })).toBe('');
    expect(err({ type: 'edit', fid: 'F-20', cat: f.cat, subject: '기타', exposure: f.exposure, note: ' 가 ', error: '' })).toBe('');
    expect(err({ type: 'restore', fid: 'F-01', note: '', error: '' })).toBe('오탐 표시를 취소하는 이유를 적어 주세요.');
    expect(err({ type: 'resolve', rid: 'R-01', note: 'x', error: '' })).toBe('확인한 내용이나 처리 결과를 적어 주세요.');
    expect(err({ type: 'link', lid: 'L-01', decision: 'linked', note: '', error: '' })).toBe('판단 근거를 적어 주세요.');
    expect(err({ type: 'reopen', note: '', error: '' })).toBe('다시 여는 이유를 적어 주세요.');
    expect(err({ type: 'memo', note: '', error: '' })).toBe('');
    expect(err({ type: 'fmemo', fid: 'F-01', note: '', error: '' })).toBe('');
    const p = await svc.pending('A1');
    expect(err({ type: 'complete', note: '', error: '' }, p)).toBe('남은 항목이 있어 완료 사유가 필요합니다.');
    expect(err({ type: 'complete', note: '', error: '' }, { openF: [], openI: [], openL: [], any: false })).toBe('');
  });
});

describe('저장 — 서비스 호출과 토스트 문구(원본 그대로)', () => {
  it('오탐 표시 → 취소 → 분류 수정 → 메모 · 해결 · 연결 판단 · 검토 메모 · 완료 · 다시 열기', async () => {
    const svc = createService();
    const run = async (m: DetailModal) => applyReviewModal(svc, await get(svc, 'A1'), m);
    const before = await get(svc, 'A1');
    const f20 = before.findings.find((x) => x.id === 'F-20');
    if (!f20) throw new Error('F-20 없음');

    expect(await run({ type: 'fp', fid: 'F-01', reason: FP_REASONS[1], note: ' 관리번호 ', error: '' })).toEqual({ text: '오탐으로 표시했습니다 · F-01 (최초 결과는 이력에 남습니다)' });
    let a = await get(svc, 'A1');
    let f = a.findings.find((x) => x.id === 'F-01');
    expect(f?.status).toBe('false_positive');
    expect(f?.fpType).toBe(FP_REASONS[1]);
    expect(f?.fpNote).toBe('관리번호');
    expect(f?.risk).toBe(before.findings.find((x) => x.id === 'F-01')?.risk);

    expect(await run({ type: 'restore', fid: 'F-01', note: '실제 번호', error: '' })).toEqual({ text: '오탐 표시를 취소했습니다 · F-01' });
    a = await get(svc, 'A1');
    expect(a.findings.find((x) => x.id === 'F-01')?.status).toBe('open');

    expect(await run({ type: 'edit', fid: 'F-20', cat: f20.cat, subject: '기타', exposure: f20.exposure, note: '단정할 수 없음', error: '' })).toEqual({ text: '분류를 수정했습니다 · F-20' });
    a = await get(svc, 'A1');
    f = a.findings.find((x) => x.id === 'F-20');
    expect(f?.status).toBe('reclassified');
    expect(f?.subject).toBe('기타');
    expect(f?.ai).toEqual(f20.ai);
    expect(f?.risk).toBe(f20.risk);

    expect(await run({ type: 'fmemo', fid: 'F-20', note: '사본 교체', error: '' })).toEqual({ text: '메모를 저장했습니다 · F-20' });
    expect((await get(svc, 'A1')).findings.find((x) => x.id === 'F-20')?.memo).toBe('사본 교체');

    const item = (await get(svc, 'A1')).items.find((x) => !x.resolved && !x.linkId);
    if (!item) throw new Error('미해결 검토사항 없음');
    expect(await run({ type: 'resolve', rid: item.id, note: '원본 확인', error: '' })).toEqual({ text: '검토사항을 해결로 표시했습니다 · ' + item.id });
    expect((await get(svc, 'A1')).items.find((x) => x.id === item.id)?.resolved).toBe(true);

    const link = (await get(svc, 'A1')).links.find((l) => l.status === 'check');
    if (!link) throw new Error('확인 필요 연결 없음');
    const linkedItems = (await get(svc, 'A1')).items.filter((x) => x.linkId === link.id).map((x) => x.id);
    expect(await run({ type: 'link', lid: link.id, decision: 'linked', note: '고객 통화', error: '' })).toEqual({ text: '연결 판단을 기록했습니다 · ' + link.id });
    a = await get(svc, 'A1');
    expect(a.links.find((l) => l.id === link.id)?.decision).toBe('linked');
    for (const id of linkedItems) expect(a.items.find((x) => x.id === id)?.resolved).toBe(true);

    expect(await run({ type: 'memo', note: '전체 의견', error: '' })).toEqual({ text: '검토 메모를 저장했습니다.' });
    expect((await get(svc, 'A1')).memo).toBe('전체 의견');

    const riskBefore = (await get(svc, 'A1')).risk;
    expect(await run({ type: 'complete', note: '남은 이유', error: '' })).toEqual({ text: '검토를 완료했습니다 · 목록의 검토 상태와 요약 숫자에 반영했습니다.', openReport: true });
    a = await get(svc, 'A1');
    expect(a.review).toBe('done');
    expect(a.risk).toBe(riskBefore);

    expect(await run({ type: 'reopen', note: '추가 서류', error: '' })).toEqual({ text: '검토를 다시 열었습니다 · 검토 상태가 ‘검토 필요’로 바뀌었습니다.' });
    expect((await get(svc, 'A1')).review).toBe('needed');
  });
});

describe("검토 완료 토스트의 '보고서 보기' — 보고서가 있는 분석(데모)만", () => {
  const liveDone = () =>
    toAnalysis(
      analysisOut({
        status: 'done',
        result: contractResult(),
        review: { status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, history: [], version: 0 },
      }),
    );

  it('hasReport — 데모 true · 실제 분석 false', async () => {
    expect(hasReport(await get(createService(), 'A1'))).toBe(true);
    expect(hasReport(liveDone())).toBe(false);
  });

  it("실제 분석의 검토 완료 — 같은 문구, '보고서 보기' 없음(openReport false)", async () => {
    const a = liveDone();
    const calls: string[] = [];
    const svc = { completeReview: async (id: string, note: string) => void calls.push(id + '|' + note) } as unknown as AnalysisService;
    const done = await applyReviewModal(svc, a, { type: 'complete', note: '  남은 이유 ', error: '' });
    expect(done).toEqual({ text: '검토를 완료했습니다 · 목록의 검토 상태와 요약 숫자에 반영했습니다.', openReport: false });
    expect(calls).toEqual([a.id + '|남은 이유']);
  });
});

describe('검토 완료 모달 열기 — 남은 항목 조회 결과(pendingGate)', () => {
  const pending = { openF: [], openI: [], openL: [], any: false };

  it('받기 전 · 오류 없음 → 기다림(모달 없음)', () => {
    expect(pendingGate(undefined, undefined)).toBe('wait');
  });

  it('받음 → 열기(남은 항목이 없어도)', () => {
    expect(pendingGate(pending, undefined)).toBe('open');
  });

  it('첫 조회 실패(값 없음 + 오류) → fail: 빈 pending 으로 보지 않는다(완료를 허용하지 않음)', () => {
    expect(pendingGate(undefined, new Error('서버 오류'))).toBe('fail');
    expect(pendingGate(undefined, 'x')).toBe('fail');
  });

  it('받은 뒤 다시 불러오다 실패(전 값 유지) → 그대로 열어 둔다', () => {
    expect(pendingGate(pending, new Error('서버 오류'))).toBe('open');
  });
});
