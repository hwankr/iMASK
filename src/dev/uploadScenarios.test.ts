import { describe, expect, it } from 'vitest';
import { initUpload, uploadView } from '@/components/upload/uploadModel';
import { CONFIG } from '@/config/app';
import { createService } from '@/services';
import { UPLOAD_STATE_IDS, isUploadStateId, uploadScenario } from './uploadScenarios';
import { DEV_STATES } from './states';

const svc = createService();

describe('/dev/states 업로드 상태 — 프로토타입 initScenario 와 같은 값', () => {
  it('업로드 묶음의 상태 6개를 모두 다룬다', () => {
    expect(DEV_STATES.filter((s) => s.group === 'upload').map((s) => s.id)).toEqual([...UPLOAD_STATE_IDS]);
    expect(isUploadStateId('upload-limit')).toBe(true);
    expect(isUploadStateId('list')).toBe(false);
  });

  it('upload — 빈 화면', async () => {
    expect(await uploadScenario('upload', svc)).toEqual({});
  });

  it('upload-selected · upload-requesting — 샘플 파일 3개(서비스), 요청 중은 frozen', async () => {
    const sel = await uploadScenario('upload-selected', svc);
    expect(sel.name).toBe('김서연 대출상담 서류 (샘플)');
    expect(sel.files?.map((f) => [f.name, f.kind, f.state])).toEqual((await svc.sampleFiles()).map((f) => [f.name, 'sample', 'ready']));
    const req = await uploadScenario('upload-requesting', svc);
    expect(req).toMatchObject({ name: '김서연 대출상담 서류 (샘플)', requesting: true, touched: true, frozen: true });
    expect(req.files).toHaveLength(3);
  });

  it('upload-unsupported', async () => {
    const s = await uploadScenario('upload-unsupported', svc);
    expect(s.name).toBe('정○○ 전세대출 서류');
    expect(s.files?.map((f) => [f.name, f.ext, f.size, f.kind, f.state])).toEqual([
      ['대출신청서_스캔.pdf', 'PDF', 2411724, 'user', 'ready'],
      ['통장사본.jpg', 'JPG', 845824, 'user', 'ready'],
    ]);
    expect(s.alerts?.map(({ id, icon, title, items, hint }) => ({ id, icon, title, items, hint }))).toEqual([
      {
        id: 'type',
        icon: 'dg-i-x-circle',
        title: '지원하지 않는 형식의 파일 2개를 추가하지 않았습니다',
        items: ['계약서_최종.docx — 지원하지 않는 형식 (DOCX)', 'IMG_2041.heic — 지원하지 않는 형식 (HEIC)'],
        hint: 'PDF, PNG, JPG 파일만 올릴 수 있습니다. 문서 파일은 PDF로 저장해 올려 주세요.',
      },
    ]);
  });

  it('upload-limit — 파일 maxFiles 개 · 제한 경고(n = 3)', async () => {
    const s = await uploadScenario('upload-limit', svc);
    expect(s.name).toBe('거래내역 일괄 검토');
    expect(s.files).toHaveLength(CONFIG.upload.maxFiles);
    expect(s.files?.[0]).toMatchObject({ name: '거래내역_01.jpg', ext: 'JPG', size: 637000 });
    expect(s.files?.[9]).toMatchObject({ name: '거래내역_10.jpg', ext: 'JPG', size: 970000 });
    expect(s.alerts?.map(({ id, icon, title, items, hint }) => ({ id, icon, title, items, hint }))).toEqual([
      {
        id: 'limit',
        icon: 'dg-i-alert',
        title: '업로드 제한을 넘은 파일 3개를 추가하지 않았습니다',
        items: ['파일은 한 분석에 최대 10개까지 올릴 수 있습니다 — 거래내역_11.jpg, 거래내역_12.jpg 제외', '스캔_전체.pdf (34.2MB) — 파일당 최대 20MB를 넘습니다'],
        hint: '파일당 최대 20MB, 한 분석에 최대 10개까지 올릴 수 있습니다. 제한은 설정에서 바꿀 수 있습니다.',
      },
    ]);
    // 제한 값을 바꾸면 그대로 따른다
    const s3 = await uploadScenario('upload-limit', svc, { maxFiles: 3, maxFileMB: 5, accept: CONFIG.upload.accept });
    expect(s3.files).toHaveLength(3);
    expect(s3.alerts?.[0].items).toEqual(['파일은 한 분석에 최대 3개까지 올릴 수 있습니다 — 거래내역_04.jpg, 거래내역_05.jpg 제외', '스캔_전체.pdf (34.2MB) — 파일당 최대 5MB를 넘습니다']);
  });

  it('upload-failed — 가운데 파일 실패', async () => {
    const s = await uploadScenario('upload-failed', svc);
    expect(s.name).toBe('소득증빙 추가 서류');
    expect(s.files?.map((f) => [f.name, f.size, f.state, f.error])).toEqual([
      ['소득금액증명_2025.pdf', 352256, 'ready', ''],
      ['건강보험_자격득실확인서.pdf', 1830000, 'failed', '업로드 중 연결이 끊겼습니다. 다시 올려 주세요.'],
      ['재직증명서.pdf', 205824, 'ready', ''],
    ]);
    expect(uploadView(initUpload(s)).footText).toBe('업로드에 실패한 파일을 다시 올리거나 목록에서 빼 주세요.');
  });
});
