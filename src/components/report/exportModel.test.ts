import { describe, expect, it } from 'vitest';
import { createService } from '@/services';
import { DEFAULT_FAILED_MESSAGE, FORMAT_OPTIONS, expectedExportName, exportView, freshExport } from './exportModel';

describe('내보내기 모달 화면 값 — 원본 modalVM export', () => {
  it('새 상태는 형식만 이어 받는다', () => {
    expect(freshExport()).toEqual({ format: 'csv', state: 'idle', file: null, msg: '', at: '' });
    expect(freshExport('json').format).toBe('json');
  });

  it('형식 선택지는 ② EXPORT_FORMATS 의 라벨·설명', () => {
    expect(FORMAT_OPTIONS.map((o) => o.value)).toEqual(['csv', 'json']);
    expect(FORMAT_OPTIONS[0].label).toBe('CSV · 탐지 항목 목록');
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
