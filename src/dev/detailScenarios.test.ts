import { describe, expect, it } from 'vitest';
import { createService, getDemoControls } from '@/services';
import type { StateId } from '@/services/analysis-service';
import { DETAIL_EDIT_NOTE, detailScenario, type DetailStateId } from './detailScenarios';
import { DEV_STATES, LISTED_STATES } from './states';

const DETAIL_IDS = DEV_STATES.filter((s) => s.group === 'detail').map((s) => s.id) as DetailStateId[];

async function prepared(id: StateId) {
  const svc = createService();
  const r = await getDemoControls(svc)?.prepare(id);
  return { svc, analysisId: r?.analysisId };
}

describe('/dev/states 상세 상태 — 원본 initScenario 1553–1570', () => {
  it('상세 묶음은 13개, 목록에는 휴대폰 전용 2개를 뺀 11개', () => {
    expect(DETAIL_IDS).toHaveLength(13);
    expect(LISTED_STATES.filter((s) => s.group === 'detail').map((s) => s.id)).toEqual([
      'detail',
      'detail-queued',
      'detail-running',
      'detail-partial',
      'detail-failed',
      'detail-completed',
      'detail-nolocation',
      'detail-review',
      'detail-links',
      'detail-edit',
      'detail-complete',
    ]);
  });

  it('모든 상세 상태는 prepare 가 분석 ID 를 돌려주고 시작 조건을 만든다', async () => {
    for (const id of DETAIL_IDS) {
      const { svc, analysisId } = await prepared(id);
      expect(analysisId, id).toBeTruthy();
      await expect(detailScenario(id, svc, analysisId as string)).resolves.toBeTypeOf('object');
    }
  });

  it('시작 조건 — 탭 · 고른 항목 · 문서 · 휴대폰 탭 · 모달', async () => {
    const svc = createService();
    const s = (id: DetailStateId) => detailScenario(id, svc, 'A1');
    expect(await s('detail')).toEqual({ focus: { kind: 'finding', id: 'F-01' } });
    expect(await s('detail-results')).toEqual({ focus: { kind: 'finding', id: 'F-01' }, mTab: 'results' });
    expect(await s('detail-docs')).toEqual({ mTab: 'docs' });
    expect(await s('detail-partial')).toEqual({ docId: 't2', tab: 'review' });
    expect(await s('detail-completed')).toEqual({ focus: { kind: 'finding', id: 'P-03' } });
    expect(await s('detail-nolocation')).toEqual({ focus: { kind: 'finding', id: 'F-23' } });
    expect(await s('detail-review')).toEqual({ tab: 'review', focus: { kind: 'item', id: 'R-01', idx: 0 } });
    expect(await s('detail-links')).toEqual({ tab: 'links', focus: { kind: 'link', id: 'L-01', idx: 1 } });
    expect(await s('detail-complete')).toEqual({ modal: { type: 'complete', note: '', error: '' } });
    for (const id of ['detail-queued', 'detail-running', 'detail-failed'] as const) expect(await s(id)).toEqual({});
  });

  it('detail-edit — F-20 선택 + 분류 수정 모달(정보 종류 · 노출 상태는 서비스 값, 정보주체 기타, 원본 사유)', async () => {
    const { svc, analysisId } = await prepared('detail-edit');
    expect(analysisId).toBe('A1');
    const f = (await svc.get('A1'))?.findings.find((x) => x.id === 'F-20');
    const init = await detailScenario('detail-edit', svc, 'A1');
    expect(init.focus).toEqual({ kind: 'finding', id: 'F-20' });
    expect(init.modal).toEqual({ type: 'edit', fid: 'F-20', cat: f?.cat, subject: '기타', exposure: f?.exposure, note: DETAIL_EDIT_NOTE, error: '' });
    expect(DETAIL_EDIT_NOTE).toBe('거래내역서 연락처가 신청서 번호와 달라 신청인 번호로 단정할 수 없음');
  });
});
