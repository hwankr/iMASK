import { describe, expect, it } from 'vitest';
import { CONFIG } from '@/config/app';
import { createService } from '@/services';
import {
  SAMPLE_ANALYSIS_NAME,
  acceptAttr,
  addFiles,
  alertLimit,
  alertType,
  applySampleFiles,
  checkStart,
  dismissAlert,
  emptyUpload,
  finishRetry,
  formatLabels,
  initUpload,
  markReady,
  removeFile,
  retryFile,
  sampleToast,
  uploadView,
  userFile,
  type UploadState,
} from './uploadModel';

const MB = 1048576;
const S = (patch: Partial<UploadState> = {}): UploadState => initUpload(patch);

describe('형식 · 제한 문구는 ① 설정값에서', () => {
  it('허용 형식 표기와 <input accept> 가 원본과 같다', () => {
    expect(formatLabels()).toEqual(['PDF', 'PNG', 'JPG']);
    expect(acceptAttr()).toBe('.pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg');
  });

  it('제한 안내 · 경고 힌트에 설정값을 쓴다', () => {
    const v = uploadView(emptyUpload());
    expect(v.limitsText).toBe('PDF · PNG · JPG · 파일당 최대 ' + CONFIG.upload.maxFileMB + 'MB · 최대 ' + CONFIG.upload.maxFiles + '개');
    expect(v.hintText).toBe('지원 형식 PDF, PNG, JPG');
    expect(alertType(['a']).hint).toBe('PDF, PNG, JPG 파일만 올릴 수 있습니다. 문서 파일은 PDF로 저장해 올려 주세요.');
    expect(alertLimit(['a'], 1, 10, 20).hint).toBe('파일당 최대 20MB, 한 분석에 최대 10개까지 올릴 수 있습니다. 제한은 설정에서 바꿀 수 있습니다.');
  });
});

describe('addFiles — 파일 선택 검사', () => {
  it('PDF · PNG · JPG(JPEG) 는 올리는 중으로 더하고, 형식 표기는 대문자(jpeg → JPG)', () => {
    const { next, added } = addFiles(S(), [
      { name: '신청서.pdf', size: 1000 },
      { name: '사진.PNG', size: 2000 },
      { name: '통장.jpeg', size: 3000 },
      { name: '영수증.jpg', size: 4000 },
    ]);
    expect(added).toHaveLength(4);
    expect(next.files.map((f) => [f.name, f.ext, f.state, f.kind])).toEqual([
      ['신청서.pdf', 'PDF', 'uploading', 'user'],
      ['사진.PNG', 'PNG', 'uploading', 'user'],
      ['통장.jpeg', 'JPG', 'uploading', 'user'],
      ['영수증.jpg', 'JPG', 'uploading', 'user'],
    ]);
    expect(next.alerts).toEqual([]);
    expect(next.enter).toEqual(Object.fromEntries(added.map((id, i) => [id, i])));
  });

  it('DOCX · HEIC · 확장자 없음은 거부하고 지원하지 않는 형식 경고', () => {
    const { next, added } = addFiles(S(), [
      { name: '계약서_최종.docx', size: 1 },
      { name: 'IMG_2041.heic', size: 1 },
      { name: 'README', size: 1 },
    ]);
    expect(added).toEqual([]);
    expect(next.files).toEqual([]);
    expect(next.alerts).toHaveLength(1);
    expect(next.alerts[0]).toMatchObject({
      id: 'type',
      icon: 'dg-i-x-circle',
      title: '지원하지 않는 형식의 파일 3개를 추가하지 않았습니다',
      items: ['계약서_최종.docx — 지원하지 않는 형식 (DOCX)', 'IMG_2041.heic — 지원하지 않는 형식 (HEIC)', 'README — 지원하지 않는 형식 (확장자 없음)'],
    });
  });

  it('파일당 최대 MB 를 넘으면 업로드 제한 경고(크기 포함)', () => {
    const { next } = addFiles(S(), [{ name: '스캔_전체.pdf', size: 21 * MB }]);
    expect(next.files).toEqual([]);
    expect(next.alerts[0]).toMatchObject({
      id: 'limit',
      icon: 'dg-i-alert',
      title: '업로드 제한을 넘은 파일 1개를 추가하지 않았습니다',
      items: ['스캔_전체.pdf (21.0MB) — 파일당 최대 20MB를 넘습니다'],
    });
    // 경계: 정확히 20MB 는 통과
    expect(addFiles(S(), [{ name: 'a.pdf', size: 20 * MB }]).added).toHaveLength(1);
  });

  it('11번째 파일부터 개수 제한 — 넘친 이름 3개까지 + 외 n개', () => {
    const picked = Array.from({ length: 15 }, (_, i) => ({ name: 'p' + (i + 1) + '.jpg', size: 1000 }));
    const { next, added } = addFiles(S(), picked);
    expect(added).toHaveLength(CONFIG.upload.maxFiles);
    expect(next.files).toHaveLength(CONFIG.upload.maxFiles);
    expect(next.alerts[0].title).toBe('업로드 제한을 넘은 파일 5개를 추가하지 않았습니다');
    expect(next.alerts[0].items).toEqual(['파일은 한 분석에 최대 10개까지 올릴 수 있습니다 — p11.jpg, p12.jpg, p13.jpg 외 2개 제외']);
  });

  it('형식 · 개수 · 크기가 함께 걸리면 형식 경고와 제한 경고(개수 먼저, 크기 다음)', () => {
    const nine = Array.from({ length: 9 }, (_, i) => userFile('f' + i + '.pdf', 'PDF', 1));
    const { next } = addFiles(S({ files: nine }), [
      { name: 'x.docx', size: 1 },
      { name: 'big.png', size: 40 * MB },
      { name: 'ok.png', size: 1 },
      { name: 'over.png', size: 1 },
    ]);
    expect(next.files).toHaveLength(10);
    expect(next.alerts.map((a) => a.id)).toEqual(['type', 'limit']);
    expect(next.alerts[1].title).toBe('업로드 제한을 넘은 파일 2개를 추가하지 않았습니다');
    expect(next.alerts[1].items).toEqual(['파일은 한 분석에 최대 10개까지 올릴 수 있습니다 — over.png 제외', 'big.png (40.0MB) — 파일당 최대 20MB를 넘습니다']);
  });

  it('새 검사 결과가 이전 경고를 바꾸고, 문제가 없으면 경고를 지운다', () => {
    const first = addFiles(S(), [{ name: 'a.docx', size: 1 }]).next;
    expect(first.alerts).toHaveLength(1);
    const second = addFiles(first, [{ name: 'b.pdf', size: 1 }]).next;
    expect(second.alerts).toEqual([]);
  });

  it('ids 를 주면 그 ID 를 쓴다(상태 갱신 함수가 두 번 불려도 같은 결과)', () => {
    const picked = [
      { name: 'a.pdf', size: 1 },
      { name: 'b.docx', size: 1 },
      { name: 'c.png', size: 1 },
    ];
    const ids = ['i1', 'i2', 'i3'];
    const a = addFiles(S(), picked, undefined, ids);
    const b = addFiles(S(), picked, undefined, ids);
    expect(a.added).toEqual(['i1', 'i3']);
    expect(a.next.files.map((f) => f.id)).toEqual(b.next.files.map((f) => f.id));
  });

  it('빈 목록이면 끌어다 놓기 표시만 끈다', () => {
    const { next, added } = addFiles(S({ drag: true }), []);
    expect(added).toEqual([]);
    expect(next.drag).toBe(false);
  });

  it('놓으면 drag 를 끈다', () => {
    expect(addFiles(S({ drag: true }), [{ name: 'a.pdf', size: 1 }]).next.drag).toBe(false);
  });
});

describe('목록 동작', () => {
  it('markReady — 올리는 중이던 것만 준비됨', () => {
    const { next, added } = addFiles(S(), [{ name: 'a.pdf', size: 1 }]);
    const ready = markReady(next, added);
    expect(ready.files[0].state).toBe('ready');
    expect(markReady(ready, added)).toBe(ready);
  });

  it('removeFile · retryFile → finishRetry · dismissAlert', () => {
    const failed = userFile('b.pdf', 'PDF', 1, { state: 'failed', error: '끊김' });
    const s = S({ files: [userFile('a.pdf', 'PDF', 1), failed], alerts: [alertType(['x'])] });
    const retrying = retryFile(s, failed.id);
    expect(retrying.files[1]).toMatchObject({ state: 'uploading', error: '' });
    expect(finishRetry(retrying, failed.id).files[1].state).toBe('ready');
    expect(removeFile(s, failed.id).files).toHaveLength(1);
    expect(dismissAlert(s, 'type').alerts).toEqual([]);
  });

  it('applySampleFiles — 파일을 샘플로 바꾸고 경고를 지우며, 분석명이 비었을 때만 샘플 이름', async () => {
    const samples = await createService().sampleFiles();
    expect(samples).toHaveLength(3);
    const blank = applySampleFiles(S({ name: '  ', files: [userFile('a.pdf', 'PDF', 1)], alerts: [alertType(['x'])] }), samples);
    expect(blank.name).toBe(SAMPLE_ANALYSIS_NAME);
    expect(blank.files.map((f) => f.kind)).toEqual(['sample', 'sample', 'sample']);
    expect(blank.alerts).toEqual([]);
    expect(applySampleFiles(S({ name: '내 서류' }), samples).name).toBe('내 서류');
    expect(sampleToast(3, true)).toBe('선택한 파일을 샘플 문서 3개로 바꿨습니다.');
    expect(sampleToast(3, false)).toBe('샘플 문서 3개를 불러왔습니다.');
  });
});

describe('checkStart · uploadView — 시작 조건과 안내 문구(uploadVM)', () => {
  const ready = () => userFile('a.pdf', 'PDF', 352256);

  it('분석명 · 파일이 없으면 시작하지 않는다', () => {
    expect(checkStart(S())).toEqual({ ok: false, reason: 'invalid' });
    expect(checkStart(S({ name: '이름' }))).toEqual({ ok: false, reason: 'invalid' });
    expect(checkStart(S({ files: [ready()] }))).toEqual({ ok: false, reason: 'invalid' });
    expect(checkStart(S({ name: '이름', files: [ready(), userFile('b.pdf', 'PDF', 1, { state: 'uploading' })] }))).toMatchObject({ ok: false });
    expect(checkStart(S({ name: '이름', files: [ready(), userFile('b.pdf', 'PDF', 1, { state: 'failed' })] }))).toMatchObject({ ok: false });
    expect(checkStart(S({ name: '이름', files: [ready()], requesting: true }))).toEqual({ ok: false, reason: 'busy' });
    const ok = checkStart(S({ name: '  이름 ', files: [ready()] }));
    expect(ok).toMatchObject({ ok: true, name: '이름' });
  });

  it('하단 안내 문구와 오류 색', () => {
    expect(uploadView(S())).toMatchObject({ footText: '분석명을 입력하고 파일을 1개 이상 선택하세요.', footError: false, nameInvalid: false, fileError: false });
    expect(uploadView(S({ touched: true }))).toMatchObject({
      footError: true,
      nameInvalid: true,
      nameHelp: '분석명을 입력해 주세요.',
      fileError: true,
    });
    expect(uploadView(S({ files: [ready()] })).footText).toBe('분석명을 입력하세요.');
    expect(uploadView(S({ name: '이름' })).footText).toBe('분석할 파일을 1개 이상 선택하세요.');
    expect(uploadView(S({ name: '이름', files: [userFile('b.pdf', 'PDF', 1, { state: 'uploading' })] }))).toMatchObject({
      footText: '파일을 올리고 있습니다.',
      startDisabled: true,
      cantStart: true,
    });
    expect(uploadView(S({ name: '이름', files: [userFile('b.pdf', 'PDF', 1, { state: 'failed' })] }))).toMatchObject({
      footText: '업로드에 실패한 파일을 다시 올리거나 목록에서 빼 주세요.',
      footError: true,
    });
    expect(uploadView(S({ name: '이름', files: [ready(), ready()] })).footText).toBe('문서 2개를 하나의 분석 건으로 요청합니다.');
    expect(uploadView(S({ name: '이름', files: [ready()], requesting: true }))).toMatchObject({
      footText: '분석을 요청하고 있습니다. 잠시만 기다려 주세요.',
      busy: true,
      cantStart: true,
      startDisabled: false,
    });
  });

  it('파일 상자 제목 · 줄임 · 합계 · 행 선 · 데모 안내', () => {
    expect(uploadView(S()).dropTitle).toBe('파일을 여기로 끌어다 놓거나');
    expect(uploadView(S({ drag: true })).dropTitle).toBe('여기에 놓으면 파일이 추가됩니다');
    const files = [userFile('a.pdf', 'PDF', 352256), userFile('b.pdf', 'PDF', 1830000, { state: 'failed' }), userFile('c.pdf', 'PDF', 205824)];
    const v = uploadView(S({ files }));
    expect(v.dropTitle).toBe('파일을 더 추가하려면 여기로 끌어다 놓거나');
    expect(v.compact).toBe(true);
    expect(v.count).toBe(3);
    expect(v.total).toBe('2.3MB');
    expect(v.rows.map((r) => r.meta)).toEqual(['PDF · 344KB', 'PDF · 1.7MB', 'PDF · 201KB']);
    expect(v.rows.map((r) => r.separated)).toEqual([false, false, false]);
    expect(v.rows[0].removeLabel).toBe('a.pdf 목록에서 제거');
    expect(v.userNotice).toBe(true);
    expect(uploadView(S({ files: [userFile('a.pdf', 'PDF', 1), userFile('b.pdf', 'PDF', 1)] })).rows.map((r) => r.separated)).toEqual([false, true]);
  });
});
