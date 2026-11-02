import { describe, expect, it, vi } from 'vitest';
import type { AnalysisService } from '../analysis-service';
import type { UploadFile } from '../types';
import { ACCESS_CODE_KEY } from './access-code';
import { ApiError, apiErrorAnalysisId, createApiClient, type AnalysisOut, type ApiClient, type UploadTicket } from './client';
import { MSG_ONE_FILE, MSG_UNSUPPORTED, MSG_UNSUPPORTED_FORMAT, MSG_UPLOAD_FAILED, createApiService, mimeForName } from './service';
import { SESSION_LIST_KEY } from './session-list';
import { analysisOut, doneResult, fakeFetch, json, memoryStorage, type SeenRequest } from './testing';
import { MSG_UPLOAD_CONFIG_MISSING, UploadConfigError, withContentType } from './upload';

const ID = 'ab12cd34-0000-4000-8000-000000000000';
const TICKET: UploadTicket = { bucket: 'documents', path: `analyses/${ID}/iMASK_smoke_bundle.pdf`, token: 'tok', signed_url: 'https://x/sign?token=tok' };

function pdfUpload(name = 'iMASK_smoke_bundle.pdf', type = 'application/pdf'): UploadFile {
  const file = new File(['%PDF-1.7 합성'], name, { type });
  return { id: 'f1', name, ext: 'PDF', size: file.size, kind: 'user', state: 'ready', error: '', file };
}

type Route = (req: SeenRequest) => Response;

/** 서비스 + 가짜 백엔드 + 가짜 업로더 — order 에 일어난 순서를 남긴다 */
function setup(route?: Route, opts: { code?: string; ids?: string[] } = {}) {
  const order: string[] = [];
  const storage = memoryStorage();
  if (opts.code !== '') storage.setItem(ACCESS_CODE_KEY, opts.code ?? 'code-123');
  if (opts.ids) storage.setItem(SESSION_LIST_KEY, JSON.stringify(opts.ids));
  const defaultRoute: Route = (req) => {
    if (req.method === 'POST' && req.url.endsWith('/analyses')) return json(201, { analysis: analysisOut(), upload: TICKET });
    if (req.method === 'POST' && req.url.endsWith('/start')) return json(200, analysisOut({ status: 'running', upstage_job_id: 'job_1' }));
    return json(200, analysisOut());
  };
  const { fetch, seen } = fakeFetch((req) => {
    order.push(req.method + ' ' + req.url.replace('/api/py', ''));
    return (route ?? defaultRoute)(req);
  });
  const upload = vi.fn(async (ticket: UploadTicket, file: File, contentType: string) => {
    order.push(`upload ${ticket.bucket}/${ticket.path} ${file.name} ${contentType}`);
  });
  const client = createApiClient({ fetch, getAccessCode: () => (storage.getItem(ACCESS_CODE_KEY) ?? '').trim() });
  const service: AnalysisService = createApiService({ client, upload, storage });
  return { service, seen, order, upload, storage };
}

describe('requestAnalysis', () => {
  it('만들기 → 올리기 → 시작 순서, 단계마다 onProgress, id 를 이 탭 목록에 넣고 알린다', async () => {
    const { service, order, seen, storage } = setup();
    const steps: string[] = [];
    const notified = vi.fn();
    service.subscribe(notified);
    const id = await service.requestAnalysis({ name: '  합성 묶음  ', files: [pdfUpload()], onProgress: (s) => steps.push(s) });
    expect(id).toBe(ID);
    expect(steps).toEqual(['create', 'upload', 'start']);
    expect(order).toEqual(['POST /analyses', `upload documents/analyses/${ID}/iMASK_smoke_bundle.pdf iMASK_smoke_bundle.pdf application/pdf`, `POST /analyses/${ID}/start`]);
    expect(seen[0].body).toEqual({ name: '합성 묶음', filename: 'iMASK_smoke_bundle.pdf', size: pdfUpload().size, mime_type: 'application/pdf' });
    expect(JSON.parse(storage.getItem(SESSION_LIST_KEY) as string)).toEqual([ID]);
    expect(notified).toHaveBeenCalledTimes(1);
    expect(notified).toHaveBeenCalledWith(); // done 이벤트는 보내지 않는다
  });

  it('형식은 확장자로 정한다(jpeg → image/jpeg)', async () => {
    const { service, seen, upload } = setup();
    const f = pdfUpload('스캔.JPEG', '');
    await service.requestAnalysis({ name: '', files: [f] });
    expect(seen[0].body).toMatchObject({ filename: '스캔.JPEG', mime_type: 'image/jpeg', name: '' });
    expect(upload.mock.calls[0][2]).toBe('image/jpeg');
  });

  it('시작이 409(이미 시작)여도 id 를 돌려준다', async () => {
    const { service, storage } = setup((req) =>
      req.url.endsWith('/start') ? json(409, { detail: '이미 시작한 분석입니다.' }) : json(201, { analysis: analysisOut(), upload: TICKET }),
    );
    await expect(service.requestAnalysis({ name: 'x', files: [pdfUpload()] })).resolves.toBe(ID);
    expect(storage.getItem(SESSION_LIST_KEY)).toContain(ID);
  });

  it('시작이 failed 행을 돌려줘도 id 를 돌려준다(상세 화면이 오류를 보여 줌)', async () => {
    const { service } = setup((req) =>
      req.url.endsWith('/start')
        ? json(200, analysisOut({ status: 'failed', error: '파일 내용이 PDF·PNG·JPEG 형식이 아닙니다.' }))
        : json(201, { analysis: analysisOut(), upload: TICKET }),
    );
    await expect(service.requestAnalysis({ name: 'x', files: [pdfUpload()] })).resolves.toBe(ID);
  });

  it('파일 0개 · 2개 · File 없는 항목은 요청 없이 거절', async () => {
    const { service, seen } = setup();
    await expect(service.requestAnalysis({ name: 'x', files: [] })).rejects.toThrow(MSG_ONE_FILE);
    await expect(service.requestAnalysis({ name: 'x', files: [pdfUpload('a.pdf'), pdfUpload('b.pdf')] })).rejects.toThrow(MSG_ONE_FILE);
    const { file: _file, ...noFile } = pdfUpload();
    void _file;
    await expect(service.requestAnalysis({ name: 'x', files: [noFile] })).rejects.toThrow(MSG_ONE_FILE);
    await expect(service.requestAnalysis({ name: 'x', files: [pdfUpload('메모.txt', 'text/plain')] })).rejects.toThrow(MSG_UNSUPPORTED_FORMAT);
    expect(seen).toHaveLength(0);
  });

  it('만들기 401 → ApiError(unauthorized) 그대로, 업로드·시작 없음', async () => {
    const { service, order, upload } = setup(() => json(401, { detail: '접근 코드가 맞지 않습니다.' }));
    const err = await service.requestAnalysis({ name: 'x', files: [pdfUpload()] }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ code: 'unauthorized', message: '접근 코드가 맞지 않습니다.' });
    expect(order).toEqual(['POST /analyses']);
    expect(upload).not.toHaveBeenCalled();
  });

  it("업로드 실패 → '파일을 올리지 못했습니다. …', 시작하지 않고 목록에도 넣지 않는다", async () => {
    const { service, order, upload, storage } = setup();
    upload.mockRejectedValueOnce(new Error('StorageApiError: mime type not supported'));
    await expect(service.requestAnalysis({ name: 'x', files: [pdfUpload()] })).rejects.toThrow(MSG_UPLOAD_FAILED);
    expect(MSG_UPLOAD_FAILED.startsWith('파일을 올리지 못했습니다.')).toBe(true);
    expect(order.some((o) => o.endsWith('/start'))).toBe(false);
    expect(storage.getItem(SESSION_LIST_KEY)).toBeNull();
  });

  it('업로드 설정이 없으면 그 문구를 그대로', async () => {
    const { service, upload } = setup();
    upload.mockRejectedValueOnce(new UploadConfigError());
    await expect(service.requestAnalysis({ name: 'x', files: [pdfUpload()] })).rejects.toThrow(MSG_UPLOAD_CONFIG_MISSING);
  });

  it('업로드 뒤 시작이 502 면 — 거절하되 오류에 분석 id, 이 탭 목록에 id, 구독자에게 알림(성공으로 보지 않음)', async () => {
    const detail = '분석 시작 결과를 확인하지 못했습니다. 잠시 후 분석 건을 다시 조회해 주세요.';
    const { service, storage, order } = setup((req) =>
      req.url.endsWith('/start') ? json(502, { detail }) : json(201, { analysis: analysisOut(), upload: TICKET }),
    );
    const notified = vi.fn();
    service.subscribe(notified);
    const err = await service.requestAnalysis({ name: 'x', files: [pdfUpload()] }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 502, code: 'server', message: detail, analysisId: ID });
    expect(apiErrorAnalysisId(err)).toBe(ID);
    expect(JSON.parse(storage.getItem(SESSION_LIST_KEY) as string)).toEqual([ID]);
    expect(notified).toHaveBeenCalledTimes(1);
    expect(order.filter((o) => o.startsWith('GET'))).toEqual([]); // 결과를 지어내지 않는다(조회는 상세 화면이)
  });

  it('업로드 뒤 시작이 네트워크 오류 · 시간 초과면 — 같은 복구 길(code network)', async () => {
    const storage = memoryStorage({ [ACCESS_CODE_KEY]: 'code-123' });
    const base: ApiClient = {
      createAnalysis: async () => ({ analysis: analysisOut(), upload: TICKET }),
      startAnalysis: async () => {
        throw new ApiError(0, 'network', '서버 응답이 너무 늦습니다. 잠시 후 다시 시도해 주세요.');
      },
      getAnalysis: async () => analysisOut(),
    };
    const service = createApiService({ client: base, upload: async () => {}, storage });
    const err = await service.requestAnalysis({ name: 'x', files: [pdfUpload()] }).catch((e: unknown) => e);
    expect(err).toMatchObject({ status: 0, code: 'network', analysisId: ID });
    expect(JSON.parse(storage.getItem(SESSION_LIST_KEY) as string)).toEqual([ID]);

    // 실제 fetch 실패(연결 끊김)도 같은 길
    const { service: s2, storage: st2 } = setup((req) => {
      if (req.url.endsWith('/start')) throw new TypeError('Failed to fetch');
      return json(201, { analysis: analysisOut(), upload: TICKET });
    });
    await expect(s2.requestAnalysis({ name: 'x', files: [pdfUpload()] })).rejects.toMatchObject({ code: 'network', analysisId: ID });
    expect(st2.getItem(SESSION_LIST_KEY)).toContain(ID);
  });

  it('시작이 401 · 404 · 400 이면 id 를 남기지 않는다(시작되지 않음이 분명)', async () => {
    for (const [status, detail] of [
      [401, '접근 코드가 맞지 않습니다.'],
      [404, '분석 건을 찾을 수 없습니다.'],
      [400, '요청 형식이 올바르지 않습니다.'],
    ] as const) {
      const { service, storage } = setup((req) => (req.url.endsWith('/start') ? json(status, { detail }) : json(201, { analysis: analysisOut(), upload: TICKET })));
      const err = await service.requestAnalysis({ name: 'x', files: [pdfUpload()] }).catch((e: unknown) => e);
      expect(err).toMatchObject({ status, analysisId: null });
      expect(storage.getItem(SESSION_LIST_KEY)).toBeNull();
    }
  });

  it('만들기 502 · 업로드 실패는 id 를 남기지 않는다', async () => {
    const created = setup(() => json(502, { detail: '분석을 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.' }));
    await expect(created.service.requestAnalysis({ name: 'x', files: [pdfUpload()] })).rejects.toMatchObject({ code: 'server', analysisId: null });
    expect(created.storage.getItem(SESSION_LIST_KEY)).toBeNull();
    const uploaded = setup();
    uploaded.upload.mockRejectedValueOnce(new Error('업로드 실패'));
    const err = await uploaded.service.requestAnalysis({ name: 'x', files: [pdfUpload()] }).catch((e: unknown) => e);
    expect(apiErrorAnalysisId(err)).toBeNull();
    expect(uploaded.storage.getItem(SESSION_LIST_KEY)).toBeNull();
  });
});

describe('get', () => {
  it('GET → 매핑(알림 없음)', async () => {
    const { service } = setup(() => json(200, analysisOut({ status: 'done', result: doneResult() })));
    const notified = vi.fn();
    service.subscribe(notified);
    const a = await service.get(ID);
    expect(a).toMatchObject({ id: ID, status: 'done', risk: 'high', code: 'DG-20261102-AB12' });
    expect(notified).not.toHaveBeenCalled();
  });

  it('404 → null, 401 → ApiError', async () => {
    expect(await setup(() => json(404, { detail: '분석 건을 찾을 수 없습니다.' })).service.get('A1')).toBeNull();
    await expect(setup(() => json(401, { detail: '접근 코드가 맞지 않습니다.' })).service.get(ID)).rejects.toMatchObject({ code: 'unauthorized' });
  });

  it('접근 코드를 고친 뒤의 조회는 이전 코드의 진행 중 요청에 합치지 않는다(같은 코드는 계속 합침)', async () => {
    const storage = memoryStorage({ [ACCESS_CODE_KEY]: 'wrong-code' });
    const sent: string[] = [];
    const waits: { resolve: (v: AnalysisOut) => void; reject: (e: unknown) => void }[] = [];
    const client = createApiClient({
      getAccessCode: () => (storage.getItem(ACCESS_CODE_KEY) ?? '').trim(),
      fetch: (async (_input: RequestInfo | URL, init?: RequestInit) => {
        const code = new Headers(init?.headers).get('x-demo-code') ?? '';
        sent.push(code);
        return new Promise<Response>((resolve) => {
          waits.push({
            resolve: () => resolve(code === 'right-code' ? json(200, analysisOut({ status: 'done' })) : json(401, { detail: '접근 코드가 맞지 않습니다.' })),
            reject: () => {},
          });
        });
      }) as typeof globalThis.fetch,
    });
    const service = createApiService({ client, upload: async () => {}, storage });
    const old = service.get(ID).catch((e: unknown) => e);
    const oldAgain = service.get(ID).catch((e: unknown) => e); // 같은 코드 → 합침
    await new Promise((r) => setTimeout(r, 0));
    expect(sent).toEqual(['wrong-code']);
    storage.setItem(ACCESS_CODE_KEY, 'right-code'); // 이전 요청이 아직 끝나지 않았다
    const fixed = service.get(ID);
    await new Promise((r) => setTimeout(r, 0));
    expect(sent).toEqual(['wrong-code', 'right-code']); // 새 요청 1회 더
    for (const w of waits) w.resolve(analysisOut());
    expect(await old).toMatchObject({ code: 'unauthorized' });
    expect(await oldAgain).toMatchObject({ code: 'unauthorized' });
    expect(await fixed).toMatchObject({ id: ID, status: 'done' }); // 결과는 새 코드 기준
  });

  it('같은 id 를 동시에 조회하면 요청 하나를 나눠 쓴다(결과 객체는 따로)', async () => {
    const { service, seen } = setup();
    const [a, b] = await Promise.all([service.get(ID), service.get(ID)]);
    expect(seen).toHaveLength(1);
    expect(a).toEqual(b);
    expect(a).not.toBe(b);
    await service.get(ID);
    expect(seen).toHaveLength(2);
  });
});

describe('list', () => {
  it('접근 코드가 없으면 요청 없이 []', async () => {
    const { service, seen } = setup(undefined, { code: '', ids: [ID] });
    expect(await service.list()).toEqual([]);
    expect(seen).toHaveLength(0);
  });

  it('이 탭 목록의 id 를 조회해 요청 시각 최신순, 404 는 목록에서 뺀다', async () => {
    const older = 'old00000-0000-4000-8000-000000000000';
    const gone = 'gone0000-0000-4000-8000-000000000000';
    const newer = 'new00000-0000-4000-8000-000000000000';
    const { service, storage, seen } = setup(
      (req) => {
        if (req.url.includes(gone)) return json(404, { detail: '분석 건을 찾을 수 없습니다.' });
        if (req.url.includes(older)) return json(200, analysisOut({ id: older, created_at: '2026-11-01T01:00:00Z' }));
        return json(200, analysisOut({ id: newer, created_at: '2026-11-02T01:00:00Z', status: 'running' }));
      },
      { ids: [older, gone, newer] },
    );
    const list = await service.list();
    expect(list.map((a) => a.id)).toEqual([newer, older]);
    expect(seen).toHaveLength(3);
    for (const r of seen) expect(r.headers['x-demo-code']).toBe('code-123');
    expect(JSON.parse(storage.getItem(SESSION_LIST_KEY) as string)).toEqual([older, newer]);
  });

  it('401 등 그 밖 오류는 던진다', async () => {
    const { service } = setup(() => json(401, { detail: '접근 코드가 맞지 않습니다.' }), { ids: [ID] });
    await expect(service.list()).rejects.toMatchObject({ code: 'unauthorized' });
  });

  it('목록이 비었으면 []', async () => {
    const { service, seen } = setup();
    expect(await service.list()).toEqual([]);
    expect(seen).toHaveLength(0);
  });
});

describe('그 밖의 메서드', () => {
  it('pending 은 빈 값, sampleFiles 는 []', async () => {
    const { service } = setup();
    expect(await service.pending(ID)).toEqual({ openF: [], openI: [], openL: [], any: false });
    expect(await service.sampleFiles()).toEqual([]);
  });

  it('다시 분석은 거절하지 않고 실패 결과(지원하지 않음)로 끝낸다 — 목록의 재시도가 처리되지 않은 오류가 되지 않게', async () => {
    const { service, seen } = setup();
    await expect(service.retry(ID)).resolves.toEqual({ ok: false, message: MSG_UNSUPPORTED });
    await expect(service.retry(ID, 'd1')).resolves.toEqual({ ok: false, message: MSG_UNSUPPORTED });
    expect(seen).toHaveLength(0);
  });

  it('검토 · 내보내기는 지원하지 않는다고 거절', async () => {
    const { service, seen } = setup();
    const calls: Promise<unknown>[] = [
      service.setStatus(ID, 'f', 'confirmed'),
      service.confirmMany(ID, ['f']),
      service.markFalsePositive(ID, 'f', '기타', ''),
      service.restore(ID, 'f'),
      service.reclassify(ID, 'f', {}, ''),
      service.saveFindingMemo(ID, 'f', ''),
      service.resolveItem(ID, 'r', ''),
      service.reopenItem(ID, 'r'),
      service.decideLink(ID, 'l', 'linked', ''),
      service.saveMemo(ID, ''),
      service.completeReview(ID, ''),
      service.reopenReview(ID, ''),
      service.buildExport(ID, 'csv'),
      service.logExport(ID, { format: 'csv', name: '', mime: '', text: '', size: 0, preview: '' }, 'saved'),
    ];
    const results = await Promise.allSettled(calls);
    expect(results).toHaveLength(14);
    for (const r of results) {
      expect(r.status).toBe('rejected');
      expect((r as PromiseRejectedResult).reason.message).toBe(MSG_UNSUPPORTED);
    }
    expect(seen).toHaveLength(0);
  });

  it('구독 해제 뒤에는 알리지 않는다', async () => {
    const { service } = setup();
    const fn = vi.fn();
    const off = service.subscribe(fn);
    off();
    await service.requestAnalysis({ name: 'x', files: [pdfUpload()] });
    expect(fn).not.toHaveBeenCalled();
  });
});

describe('도우미', () => {
  it('mimeForName — 백엔드가 받는 셋만', () => {
    expect(mimeForName('a.PDF')).toBe('application/pdf');
    expect(mimeForName('a.png')).toBe('image/png');
    expect(mimeForName('a.jpg')).toBe('image/jpeg');
    expect(mimeForName('a.jpeg')).toBe('image/jpeg');
    expect(mimeForName('a.gif')).toBe('');
    expect(mimeForName('pdf')).toBe('');
  });

  it('withContentType — 형식이 다르면 같은 내용 · 이름으로 형식을 붙인 File', async () => {
    const f = new File(['abc'], '묶음.pdf', { type: '' });
    const g = withContentType(f, 'application/pdf');
    expect(g).not.toBe(f);
    expect(g.type).toBe('application/pdf');
    expect(g.name).toBe('묶음.pdf');
    expect(await g.text()).toBe('abc');
    const h = new File(['x'], 'a.pdf', { type: 'application/pdf' });
    expect(withContentType(h, 'application/pdf')).toBe(h);
  });
});
