import { describe, expect, it } from 'vitest';
import { createService } from '@/services';
import { EXPORT_FORMATS, LIVE_EXPORT_JSON_DESC } from '@/display/rules';
import { DEFAULT_FAILED_MESSAGE, FORMAT_OPTIONS, LIVE_FORMAT_OPTIONS, expectedExportName, exportView, freshExport } from './exportModel';

describe('내보내기 모달 화면 값 — 원본 modalVM export', () => {
  it('새 상태는 형식만 이어 받는다', () => {
    expect(freshExport()).toEqual({ format: 'csv', state: 'idle', file: null, msg: '', at: '' });
    expect(freshExport('json').format).toBe('json');
  });

  it('형식 선택지는 ② EXPORT_FORMATS 의 라벨·설명', () => {
    expect(FORMAT_OPTIONS.map((o) => o.value)).toEqual(['csv', 'json']);
    expect(FORMAT_OPTIONS[0].label).toBe('CSV · 탐지 항목 목록');
  });

  it('실제 분석 선택지 — JSON 설명만 실제 분석 문구, 데모 선택지 · ② EXPORT_FORMATS 는 그대로', () => {
    expect(LIVE_EXPORT_JSON_DESC).toBe('분석 정보, 탐지 항목, 검토 이력을 모두 담습니다.');
    expect(LIVE_FORMAT_OPTIONS).toEqual([FORMAT_OPTIONS[0], { ...FORMAT_OPTIONS[1], description: LIVE_EXPORT_JSON_DESC }]);
    expect(FORMAT_OPTIONS.map((o) => o.description)).toEqual([
      '엑셀 등에서 열 수 있는 표입니다. 탐지 항목, 판단 근거, 확인 상태를 담습니다.',
      '분석 정보, 탐지 항목, 검토사항, 문서 간 연결, 검토 이력을 모두 담습니다.',
    ]);
    expect(EXPORT_FORMATS.map((f) => [f.key, f.label])).toEqual([
      ['csv', 'CSV · 탐지 항목 목록'],
      ['json', 'JSON · 보고서 전체'],
    ]);
  });

  it('만들기 전 파일 이름은 서비스가 만들 이름과 같다', async () => {
    const svc = createService();
    for (const format of ['csv', 'json'] as const) {
      const file = await svc.buildExport('A1', format);
      expect(expectedExportName('DG-20261030-0007', format)).toBe(file.name);
    }
    expect(expectedExportName('DG-20261030-0007', 'csv')).toBe('iMASK_DG-20261030-0007_검토결과_탐지항목.csv');
  });

  it('주요 버튼 글자 — 만들기 · 만드는 중 · 다시 내보내기 · 다시 시도', async () => {
    const file = await createService().buildExport('A1', 'csv');
    const code = 'DG-20261030-0007';
    expect(exportView(freshExport(), code)).toMatchObject({ busy: false, primaryLabel: '파일 만들기 · 저장', doneText: '', preview: '' });
    expect(exportView({ ...freshExport(), state: 'working' }, code)).toMatchObject({ busy: true, primaryLabel: '만드는 중…' });
    const handed = exportView({ format: 'csv', state: 'handed', file, msg: '', at: '2026-11-01 10:05' }, code);
    expect(handed.primaryLabel).toBe('다시 내보내기');
    expect(handed.fileName).toBe(file.name);
    expect(handed.doneText).toMatch(new RegExp('^' + file.name.replace(/[.]/g, '\\.') + ' · \\d+KB · 2026\\.11\\.01 10:05$'));
    expect(handed.preview).toBe(file.preview);
    expect(exportView({ ...freshExport(), state: 'declined' }, code).primaryLabel).toBe('다시 내보내기');
    const failed = exportView({ ...freshExport(), state: 'failed' }, code);
    expect(failed.primaryLabel).toBe('다시 시도');
    expect(failed.failedText).toBe(DEFAULT_FAILED_MESSAGE);
  });
});
