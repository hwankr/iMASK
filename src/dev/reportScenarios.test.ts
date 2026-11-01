import { describe, expect, it } from 'vitest';
import { createService, getDemoControls } from '@/services';
import { REPORT_FAILED_MESSAGE, reportScenario } from './reportScenarios';
import { DEV_STATES } from './states';

describe('/dev/states 보고서 상태 — 원본 initScenario report*', () => {
  it('보고서 묶음은 report · report-saved · report-failed', () => {
    expect(DEV_STATES.filter((s) => s.group === 'report').map((s) => s.id)).toEqual(['report', 'report-saved', 'report-failed']);
  });

  it('prepare 는 A1 을 돌려주고, report 는 모달 없이 연다', async () => {
    const svc = createService();
    const { analysisId } = (await getDemoControls(svc)?.prepare('report')) ?? {};
    expect(analysisId).toBe('A1');
    expect(await reportScenario('report', svc, 'A1')).toEqual({});
  });

  it('report-saved — CSV · saved · 파일은 buildExport(A1, csv) 결과 그대로 · 시각 있음', async () => {
    const svc = createService();
    await getDemoControls(svc)?.prepare('report-saved');
    const init = await reportScenario('report-saved', svc, 'A1');
    const file = await svc.buildExport('A1', 'csv');
    expect(init.exportModal).toMatchObject({ format: 'csv', state: 'saved', msg: '' });
    expect(init.exportModal?.file).toEqual(file);
    expect(init.exportModal?.at).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
  });

  it('report-failed — CSV · failed · 파일 없음 · 원본 문구', async () => {
    const svc = createService();
    const init = await reportScenario('report-failed', svc, 'A1');
    expect(init.exportModal).toEqual({ format: 'csv', state: 'failed', file: null, msg: REPORT_FAILED_MESSAGE, at: '' });
    expect(REPORT_FAILED_MESSAGE).toBe('저장 위치에 파일을 쓰지 못했습니다. 잠시 후 다시 시도하거나 다른 형식을 선택하세요.');
  });
});
