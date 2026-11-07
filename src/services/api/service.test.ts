/* 실제 분석 서비스 — 분석 요청 · 조회 · 서버 목록 · 완료 한 번 알림 · 쓰기 뒤 요청 떼기 · 다시 분석 · 삭제 · 브라우저 저장소 안 씀.
   가짜 백엔드(fakeFetch)로 요청 모양 · 순서 · 알림 수를 확인한다. 검토 동작은 review-service.test.ts. */
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CONFIG } from '@/config/app';
import type { AnalysisService } from '../analysis-service';
import type { UploadFile } from '../types';
import { ApiError, MSG_BAD_RESPONSE, MSG_NETWORK, apiErrorAnalysisId, createApiClient, type ApiClient, type UploadTicket } from './client';
import { MSG_NO_REASON, MSG_ONE_FILE, MSG_UNSUPPORTED, MSG_UNSUPPORTED_FORMAT, MSG_UPLOAD_FAILED, createApiService, mimeForName } from './service';
import { analysisOut, contractResult, doneResult, fakeFetch, json, listItemOut, type SeenRequest } from './testing';
import { MSG_UPLOAD_CONFIG_MISSING, UploadConfigError, withContentType } from './upload';

const ID = 'ab12cd34-0000-4000-8000-000000000000';
const OTHER = 'cd34ab12-0000-4000-8000-000000000000';
const TICKET: UploadTicket = { bucket: 'documents', path: `analyses/${ID}/iMASK_smoke_bundle.pdf`, token: 'tok', signed_url: 'https://x/sign?token=tok' };
const LIST_URL = '/api/py/analyses';

function pdfUpload(name = 'iMASK_smoke_bundle.pdf', type = 'application/pdf'): UploadFile {
  const file = new File(['%PDF-1.7 합성'], name, { type });
  return { id: 'f1', name, ext: 'PDF', size: file.size, kind: 'user', state: 'ready', error: '' };
}
function withFile(u: UploadFile): UploadFile {
  return { ...u, file: new File(['%PDF-1.7 합성'], u.name, { type: 'application/pdf' }) };
}
const pdf = (name?: string, type?: string) => withFile(pdfUpload(name, type));

type Route = (req: SeenRequest) => Response | Promise<Response>;

/** 204(본문 없음) */
const noContent = () => new Response(null, { status: 204 });

const isList = (req: SeenRequest) => req.method === 'GET' && req.url === LIST_URL;
const isGet = (req: SeenRequest) => req.method === 'GET' && req.url.startsWith(LIST_URL + '/');

/** 서비스 + 가짜 백엔드 + 가짜 업로더 — order 에 일어난 순서를 남긴다 */
function setup(route?: Route) {
  const order: string[] = [];
  const defaultRoute: Route = (req) => {
    if (req.method === 'POST' && req.url === LIST_URL) return json(201, { analysis: analysisOut(), upload: TICKET });
    if (req.method === 'POST' && req.url.endsWith('/start')) return json(200, analysisOut({ status: 'running', upstage_job_id: 'job_1' }));
    if (req.method === 'POST' && req.url.endsWith('/retry')) return json(200, analysisOut({ status: 'running', upstage_job_id: 'job_2' }));
    if (req.method === 'DELETE') return noContent();
    if (isList(req)) return json(200, { analyses: [] });
    return json(200, analysisOut());
  };
  const { fetch, seen } = fakeFetch((req) => {
    order.push(req.method + ' ' + req.url.replace('/api/py', ''));
    return (route ?? defaultRoute)(req);
  });
  const upload = vi.fn(async (ticket: UploadTicket, file: File, contentType: string) => {
    order.push(`upload ${ticket.bucket}/${ticket.path} ${file.name} ${contentType}`);
  });
  const client = createApiClient({ fetch });
  const service: AnalysisService = createApiService({ client, upload });
  const notified = vi.fn();
  service.subscribe(notified);
  const count = (pred: (r: SeenRequest) => boolean) => seen.filter(pred).length;
  return { service, seen, order, upload, notified, count };
}

/** 밖에서 푸는 약속 */
function deferred<T = void>(): { promise: Promise<T>; resolve: (v: T) => void } {
  let resolve: (v: T) => void = () => {};
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

describe('requestAnalysis', () => {
  it('만들기 → 올리기 → 시작 순서, 단계마다 onProgress, 알림 한 번(이벤트 없음)', async () => {
    const { service, order, seen, notified } = setup();
    const steps: string[] = [];
    const id = await service.requestAnalysis({ name: '  합성 묶음  ', files: [pdf()], onProgress: (s) => steps.push(s) });
    expect(id).toBe(ID);
    expect(steps).toEqual(['create', 'upload', 'start']);
    expect(order).toEqual(['POST /analyses', `upload documents/analyses/${ID}/iMASK_smoke_bundle.pdf iMASK_smoke_bundle.pdf application/pdf`, `POST /analyses/${ID}/start`]);
    expect(seen[0].body).toEqual({ name: '합성 묶음', filename: 'iMASK_smoke_bundle.pdf', size: pdf().file?.size, mime_type: 'application/pdf' });
    expect(notified).toHaveBeenCalledTimes(1);
    expect(notified).toHaveBeenCalledWith(); // done 이벤트는 보내지 않는다
  });

  it('형식은 확장자로 정한다(jpeg → image/jpeg)', async () => {
    const { service, seen, upload } = setup();
    await service.requestAnalysis({ name: '', files: [pdf('스캔.JPEG', '')] });
    expect(seen[0].body).toMatchObject({ filename: '스캔.JPEG', mime_type: 'image/jpeg', name: '' });
    expect(upload.mock.calls[0][2]).toBe('image/jpeg');
  });

  it('시작이 409(이미 시작)여도 id 를 돌려주고 알린다', async () => {
    const { service, notified } = setup((req) =>
      req.url.endsWith('/start') ? json(409, { detail: '이미 시작한 분석입니다.' }) : json(201, { analysis: analysisOut(), upload: TICKET }),
    );
    await expect(service.requestAnalysis({ name: 'x', files: [pdf()] })).resolves.toBe(ID);
    expect(notified).toHaveBeenCalledTimes(1);
  });

  it('시작이 failed 행을 돌려줘도 id 를 돌려준다(상세 화면이 오류를 보여 줌)', async () => {
    const { service } = setup((req) =>
      req.url.endsWith('/start')
        ? json(200, analysisOut({ status: 'failed', error: '파일 내용이 PDF·PNG·JPEG 형식이 아닙니다.' }))
        : json(201, { analysis: analysisOut(), upload: TICKET }),
    );
    await expect(service.requestAnalysis({ name: 'x', files: [pdf()] })).resolves.toBe(ID);
  });

  it('파일 0개 · 2개 · File 없는 항목 · 모르는 형식은 요청 없이 거절', async () => {
    const { service, seen } = setup();
    await expect(service.requestAnalysis({ name: 'x', files: [] })).rejects.toThrow(MSG_ONE_FILE);
    await expect(service.requestAnalysis({ name: 'x', files: [pdf('a.pdf'), pdf('b.pdf')] })).rejects.toThrow(MSG_ONE_FILE);
    await expect(service.requestAnalysis({ name: 'x', files: [pdfUpload()] })).rejects.toThrow(MSG_ONE_FILE);
    await expect(service.requestAnalysis({ name: 'x', files: [pdf('메모.txt', 'text/plain')] })).rejects.toThrow(MSG_UNSUPPORTED_FORMAT);
    expect(seen).toHaveLength(0);
  });

  it('만들기 400 → ApiError 그대로, 업로드·시작·알림 없음', async () => {
    const { service, order, upload, notified } = setup(() => json(400, { detail: '파일 이름이 비었습니다.' }));
    const err = await service.requestAnalysis({ name: 'x', files: [pdf()] }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ code: 'bad_request', message: '파일 이름이 비었습니다.' });
    expect(order).toEqual(['POST /analyses']);
    expect(upload).not.toHaveBeenCalled();
    expect(notified).not.toHaveBeenCalled();
  });

  it("업로드 실패 → '파일을 올리지 못했습니다. …', 시작하지 않고 알리지 않는다", async () => {
    const { service, order, upload, notified } = setup();
    upload.mockRejectedValueOnce(new Error('StorageApiError: mime type not supported'));
    await expect(service.requestAnalysis({ name: 'x', files: [pdf()] })).rejects.toThrow(MSG_UPLOAD_FAILED);
    expect(MSG_UPLOAD_FAILED.startsWith('파일을 올리지 못했습니다.')).toBe(true);
    expect(order.some((o) => o.endsWith('/start'))).toBe(false);
    expect(notified).not.toHaveBeenCalled();
  });

  it('업로드 설정이 없으면 그 문구를 그대로', async () => {
    const { service, upload } = setup();
    upload.mockRejectedValueOnce(new UploadConfigError());
    await expect(service.requestAnalysis({ name: 'x', files: [pdf()] })).rejects.toThrow(MSG_UPLOAD_CONFIG_MISSING);
  });

  it('업로드 뒤 시작이 502 면 — 거절하되 오류에 분석 id, 구독자에게 알림(성공으로 보지 않음)', async () => {
    const detail = '분석 시작 결과를 확인하지 못했습니다. 잠시 후 분석 건을 다시 조회해 주세요.';
    const { service, order, notified } = setup((req) =>
      req.url.endsWith('/start') ? json(502, { detail }) : json(201, { analysis: analysisOut(), upload: TICKET }),
    );
    const err = await service.requestAnalysis({ name: 'x', files: [pdf()] }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 502, code: 'server', message: detail, analysisId: ID });
    expect(apiErrorAnalysisId(err)).toBe(ID);
    expect(notified).toHaveBeenCalledTimes(1);
    expect(order.filter((o) => o.startsWith('GET'))).toEqual([]); // 결과를 지어내지 않는다(조회는 상세 화면이)
  });

  it('업로드 뒤 시작이 네트워크 오류 · 시간 초과면 — 같은 복구 길(code network)', async () => {
    const base: ApiClient = {
      createAnalysis: async () => ({ analysis: analysisOut(), upload: TICKET }),
      startAnalysis: async () => {
        throw new ApiError(0, 'network', '서버 응답이 너무 늦습니다. 잠시 후 다시 시도해 주세요.');
      },
      getAnalysis: async () => analysisOut(),
      getFile: async () => ({ url: '', mime_type: '', filename: '' }),
      reviewAction: async () => ({ analysis: analysisOut(), changed: true }),
      listAnalyses: async () => ({ analyses: [] }),
      deleteAnalysis: async () => {},
      retryAnalysis: async () => analysisOut(),
      openWorkflowSettings: async () => ({ agent_id: '', config_id: '', agent_name: null, config_name: null }),
      saveWorkflowSettings: async () => ({ agent_id: '', config_id: '', agent_name: null, config_name: null }),
    };
    const service = createApiService({ client: base, upload: async () => {} });
    const err = await service.requestAnalysis({ name: 'x', files: [pdf()] }).catch((e: unknown) => e);
    expect(err).toMatchObject({ status: 0, code: 'network', analysisId: ID });

    // 실제 fetch 실패(연결 끊김)도 같은 길
    const { service: s2 } = setup((req) => {
      if (req.url.endsWith('/start')) throw new TypeError('Failed to fetch');
      return json(201, { analysis: analysisOut(), upload: TICKET });
    });
    await expect(s2.requestAnalysis({ name: 'x', files: [pdf()] })).rejects.toMatchObject({ code: 'network', analysisId: ID });
  });

  it('시작이 404 · 400 이면 분석 id 를 담지 않고 알리지 않는다(시작되지 않음이 분명)', async () => {
    for (const [status, detail] of [
      [404, '분석 건을 찾을 수 없습니다.'],
      [400, '요청 형식이 올바르지 않습니다.'],
    ] as const) {
      const { service, notified } = setup((req) => (req.url.endsWith('/start') ? json(status, { detail }) : json(201, { analysis: analysisOut(), upload: TICKET })));
      const err = await service.requestAnalysis({ name: 'x', files: [pdf()] }).catch((e: unknown) => e);
      expect(err).toMatchObject({ status, analysisId: null });
      expect(notified).not.toHaveBeenCalled();
    }
  });

  it('만들기 502 · 업로드 실패는 분석 id 를 담지 않는다', async () => {
    const created = setup(() => json(502, { detail: '분석을 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.' }));
    await expect(created.service.requestAnalysis({ name: 'x', files: [pdf()] })).rejects.toMatchObject({ code: 'server', analysisId: null });
    const uploaded = setup();
    uploaded.upload.mockRejectedValueOnce(new Error('업로드 실패'));
    const err = await uploaded.service.requestAnalysis({ name: 'x', files: [pdf()] }).catch((e: unknown) => e);
    expect(apiErrorAnalysisId(err)).toBeNull();
  });
});

describe('get', () => {
  it('GET → 매핑(알림 없음)', async () => {
    const { service, notified } = setup(() => json(200, analysisOut({ status: 'done', result: doneResult(), started_at: '2026-11-02T05:10:01Z' })));
    const a = await service.get(ID);
    expect(a).toMatchObject({ id: ID, status: 'done', risk: 'high', code: 'DG-20261102-AB12' });
    expect(a?.raw?.startedAt).toBe('2026-11-02T05:10:01Z');
    expect(notified).not.toHaveBeenCalled();
  });

  it('404 → null, 그 밖 오류 → ApiError', async () => {
    expect(await setup(() => json(404, { detail: '분석 건을 찾을 수 없습니다.' })).service.get('A1')).toBeNull();
    await expect(setup(() => json(500, { detail: '서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.' })).service.get(ID)).rejects.toMatchObject({ code: 'server' });
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

describe('list — 서버 목록 GET /analyses 하나', () => {
  it('요청 하나(limit 없이 · 사용자 지정 헤더 없음) → 서버 순서 그대로, 항목 매핑', async () => {
    const { service, seen } = setup((req) =>
      isList(req)
        ? json(200, {
            analyses: [
              listItemOut({ id: OTHER, status: 'running', created_at: '2026-11-01T00:00:00Z' }),
              listItemOut({ id: ID, status: 'done', risk_level: '중', review: 'done', created_at: '2026-11-03T00:00:00Z' }),
            ],
          })
        : json(500, {}),
    );
    const list = await service.list();
    expect(seen.map((r) => [r.method, r.url])).toEqual([['GET', LIST_URL]]);
    expect(seen[0].headers).not.toHaveProperty('x-demo-code');
    expect(seen[0].headers.accept).toBe('application/json');
    expect(list.map((a) => [a.id, a.status, a.risk, a.review])).toEqual([
      [OTHER, 'running', 'unrated', 'none'],
      [ID, 'done', 'medium', 'done'],
    ]);
  });

  it('같은 때의 list() 둘(헤더 숫자 + 목록 화면) → 요청 하나, 결과 객체는 따로', async () => {
    const { service, count } = setup((req) => (isList(req) ? json(200, { analyses: [listItemOut()] }) : json(500, {})));
    const [a, b] = await Promise.all([service.list(), service.list()]);
    expect(count(isList)).toBe(1);
    expect(a).toEqual(b);
    expect(a).not.toBe(b);
    expect(a[0]).not.toBe(b[0]);
    await service.list();
    expect(count(isList)).toBe(2); // 끝난 뒤에는 새 요청
  });

  it('응답 모양이 틀리면(객체 아님 · analyses 가 배열 아님) ApiError(server, 응답을 읽지 못함)', async () => {
    for (const body of [[], { analyses: {} }, { analyses: null }, {}, '목록']) {
      const { service } = setup(() => json(200, body));
      const err = await service.list().catch((e: unknown) => e);
      expect(err).toBeInstanceOf(ApiError);
      expect(err).toMatchObject({ code: 'server', message: MSG_BAD_RESPONSE });
    }
  });

  it('항목 하나가 깨지면 그 항목만 빠진다', async () => {
    const { service } = setup(() => json(200, { analyses: [listItemOut({ id: ID }), { id: '' }, null, listItemOut({ id: OTHER })] }));
    expect((await service.list()).map((a) => a.id)).toEqual([ID, OTHER]);
  });

  it('5xx · 네트워크 오류는 그대로 던진다', async () => {
    await expect(setup(() => json(502, { detail: '데이터 저장소에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.' })).service.list()).rejects.toMatchObject({ code: 'server' });
    await expect(
      setup(() => {
        throw new TypeError('Failed to fetch');
      }).service.list(),
    ).rejects.toMatchObject({ code: 'network' });
  });

  it('빈 목록 → [](요청은 보낸다)', async () => {
    const { service, count } = setup();
    expect(await service.list()).toEqual([]);
    expect(count(isList)).toBe(1);
  });
});

/** 차례로 다른 상태를 돌려주는 가짜 백엔드(id 별 GET) — 끝나면 마지막 상태 그대로 */
function statusRoute(byId: Record<string, string[]>, lists: string[][] = []): Route {
  const seenCount: Record<string, number> = {};
  let listN = 0;
  return (req) => {
    if (isList(req)) {
      const statuses = lists[Math.min(listN++, lists.length - 1)] ?? [];
      return json(200, { analyses: statuses.map((s, i) => listItemOut({ id: [ID, OTHER][i], status: s })) });
    }
    const id = Object.keys(byId).find((k) => req.url.includes(k)) ?? ID;
    const list = byId[id];
    const n = (seenCount[id] = (seenCount[id] ?? 0) + 1);
    const status = list[Math.min(n, list.length) - 1];
    const done = status === 'done';
    return json(200, analysisOut({ id, status, result: done ? doneResult() : null, upstage_job_id: status === 'queued' ? null : 'job_1' }));
  };
}

describe('완료 한 번 알림(헤더 검토 필요 숫자 · 목록이 다시 불러오게)', () => {
  it('get — 진행 중으로 본 분석이 완료되면 한 번, 이벤트 없는 알림, 다시 조회해도 더 알리지 않는다', async () => {
    const { service, notified } = setup(statusRoute({ [ID]: ['running', 'running', 'done', 'done'] }));
    await service.get(ID);
    await service.get(ID);
    expect(notified).not.toHaveBeenCalled();
    const done = await service.get(ID);
    expect(done).toMatchObject({ status: 'done', review: 'none' }); // review 블록 없는 응답 — 알림은 상태 기준
    expect(notified).toHaveBeenCalledTimes(1);
    expect(notified.mock.calls[0]).toEqual([]);
    await service.get(ID);
    expect(notified).toHaveBeenCalledTimes(1);
  });

  it('대기 → 실패 · 분석 중 → 일부 실패도 끝난 것으로 알린다', async () => {
    const { service, notified } = setup(statusRoute({ [ID]: ['queued', 'failed'], [OTHER]: ['running', 'partial'] }));
    await service.get(ID);
    await service.get(OTHER);
    expect(notified).not.toHaveBeenCalled();
    await service.get(ID);
    expect(notified).toHaveBeenCalledTimes(1);
    await service.get(OTHER);
    expect(notified).toHaveBeenCalledTimes(2);
  });

  it('처음 본 분석이 이미 끝났으면 알리지 않는다(get · list 모두)', async () => {
    const { service, notified } = setup(statusRoute({ [ID]: ['done'] }, [['done', 'failed']]));
    await service.get(ID);
    await service.list();
    expect(notified).not.toHaveBeenCalled();
  });

  it('완료로 본 뒤의 다른 상태는 무시한다(완료는 되돌리지 않음 — 다시 알리지 않는다)', async () => {
    const { service, notified } = setup(statusRoute({ [ID]: ['running', 'done', 'running', 'done'] }));
    await service.get(ID); // running
    await service.get(ID); // done → 알림
    await service.get(ID); // running(무시)
    await service.get(ID); // done
    expect(notified).toHaveBeenCalledTimes(1);
  });

  it('늦게 온 옛 응답 — 먼저 보낸 조회의 늦은 "분석 중"은 나중에 보낸 조회가 본 "실패"를 되돌리지 않는다(순번)', async () => {
    const gate = deferred();
    let gets = 0;
    let lists = 0;
    const { service, notified } = setup(async (req) => {
      if (isList(req)) {
        lists++;
        return json(200, { analyses: [listItemOut({ id: ID, status: 'failed', error: '실패' })] });
      }
      const mine = ++gets;
      if (mine === 2) await gate.promise; // 실패 전에 보낸 조회 — 늦게 '분석 중'을 준다
      return json(200, analysisOut({ status: 'running' }));
    });
    await service.get(ID); // 1 running
    const late = service.get(ID); // 2(붙잡힘)
    await vi.waitFor(() => expect(gets).toBe(2));
    await service.list(); // 3 failed → 알림 1
    expect(notified).toHaveBeenCalledTimes(1);
    gate.resolve();
    expect((await late)?.status).toBe('running'); // 그 호출자에게는 받은 값 그대로
    await service.list(); // 4 failed — 옛 '분석 중'으로 되돌아가지 않았으므로 다시 알리지 않는다
    expect(notified).toHaveBeenCalledTimes(1);
    expect(lists).toBe(2);
  });

  it('목록 조회와 상세 조회가 같은 기록을 쓴다 — 목록에서 분석 중, 상세 조회에서 완료 → 한 번', async () => {
    const { service, notified } = setup(statusRoute({ [ID]: ['done'] }, [['running']]));
    expect((await service.list()).map((a) => a.status)).toEqual(['running']);
    await service.get(ID);
    expect(notified).toHaveBeenCalledTimes(1);
  });

  it('list 도 — 진행 중으로 본 분석이 목록에서 끝나면 응답 하나당 한 번(여러 분석이 함께 끝나도 한 번)', async () => {
    const { service, notified } = setup(statusRoute({}, [['running', 'queued'], ['done', 'failed'], ['done', 'failed']]));
    await service.list();
    expect(notified).not.toHaveBeenCalled();
    await service.list();
    expect(notified).toHaveBeenCalledTimes(1);
    await service.list();
    expect(notified).toHaveBeenCalledTimes(1);
  });

  it('나눠 쓴 list() 둘이 같은 응답에서 완료를 봐도 한 번', async () => {
    const { service, notified, count } = setup(statusRoute({}, [['running'], ['done']]));
    await service.list();
    await Promise.all([service.list(), service.list()]);
    expect(count(isList)).toBe(2);
    expect(notified).toHaveBeenCalledTimes(1);
  });

  it('알림을 받은 구독자가 목록을 다시 불러와도 알림이 되풀이되지 않는다(무한 다시 불러오기 없음)', async () => {
    const { service, seen, count } = setup(statusRoute({ [ID]: ['running', 'done'] }, [['done']]));
    const reloads: Promise<unknown>[] = [];
    const listener = vi.fn(() => {
      reloads.push(service.list()); // 헤더 useAnalyses 처럼
    });
    service.subscribe(listener);
    await service.get(ID);
    await service.get(ID);
    await Promise.all(reloads);
    await Promise.all(reloads);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(reloads).toHaveLength(1);
    expect(count(isList)).toBe(1);
    expect(seen).toHaveLength(3);
  });

  it('목록에서 끝난 것을 본 구독자가 목록을 다시 불러와도 되풀이되지 않는다', async () => {
    const { service, count } = setup(statusRoute({}, [['running'], ['done']]));
    await service.list();
    let reloads = 0;
    const pending: Promise<unknown>[] = [];
    service.subscribe(() => {
      reloads++;
      pending.push(service.list());
    });
    await service.list();
    await Promise.all(pending);
    await Promise.all(pending);
    expect(reloads).toBe(1);
    expect(count(isList)).toBe(3);
  });
});

describe('쓰기 뒤에는 알리기 전에 나눠 쓰던 목록 · 조회 요청을 뗀다(저장 전 값을 주지 않게)', () => {
  /** 첫 목록 요청만 붙잡는 가짜 백엔드 — 붙잡힌 목록은 쓰기 전 값(old), 그 뒤 요청은 쓰기 뒤 값(new) */
  function heldList() {
    const gate = deferred();
    let lists = 0;
    let gets = 0;
    const getGate = deferred();
    const route: Route = async (req) => {
      if (isList(req)) {
        const mine = ++lists;
        if (mine === 1) {
          await gate.promise;
          return json(200, { analyses: [listItemOut({ name: 'old' })] });
        }
        return json(200, { analyses: [listItemOut({ name: 'new' })] });
      }
      if (isGet(req) && !req.url.endsWith('/file')) {
        const mine = ++gets;
        if (mine === 1) {
          await getGate.promise;
          return json(200, analysisOut({ status: 'done', result: contractResult(), review: reviewBlock(), name: 'old' }));
        }
        return json(200, analysisOut({ status: 'done', result: contractResult(), review: reviewBlock(), name: 'new' }));
      }
      if (req.method === 'POST' && req.url === LIST_URL) return json(201, { analysis: analysisOut(), upload: TICKET });
      if (req.url.endsWith('/start')) return json(200, analysisOut({ status: 'running' }));
      if (req.url.endsWith('/retry')) return json(200, analysisOut({ status: 'running' }));
      if (req.url.endsWith('/review-actions')) return json(200, { analysis: analysisOut({ status: 'done' }), changed: true });
      if (req.method === 'DELETE') return noContent();
      return json(404, {});
    };
    return { route, release: () => gate.resolve(), releaseGet: () => getGate.resolve(), lists: () => lists, gets: () => gets };
  }

  function reviewBlock() {
    return { status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, history: [], version: 0 };
  }

  const writes: { name: string; run: (s: AnalysisService) => Promise<unknown> }[] = [
    { name: '분석 요청', run: (s) => s.requestAnalysis({ name: 'x', files: [pdf()] }) },
    { name: '삭제', run: (s) => s.deleteAnalysis(ID) },
    { name: '다시 분석', run: (s) => s.retry(ID) },
    { name: '검토 동작(메모 저장)', run: (s) => s.saveMemo(ID, '메모') },
  ];
  for (const w of writes) {
    it(`${w.name} 뒤 — 알림을 받은 list() 는 새 요청(쓰기 뒤 값), 쓰기 전 요청은 그 호출자에게만`, async () => {
      const h = heldList();
      const { service, notified } = setup(h.route);
      const before = service.list(); // 쓰기 전에 시작한 목록(붙잡힘)
      await vi.waitFor(() => expect(h.lists()).toBe(1));
      if (w.name.startsWith('검토')) h.releaseGet(); // 검토 동작 전 조회는 풀어 둔다
      const after: Promise<{ name: string }[]>[] = [];
      service.subscribe(() => after.push(service.list()));
      await w.run(service);
      expect(notified).toHaveBeenCalledTimes(1);
      h.release();
      const [old, fresh] = await Promise.all([before, after[0]]);
      expect(old.map((a) => a.name)).toEqual(['old']);
      expect(fresh.map((a) => a.name)).toEqual(['new']);
      expect(h.lists()).toBe(2);
    });
  }

  it('삭제 · 다시 분석 뒤 — 그 분석의 진행 중 조회도 떼어 알림 뒤 get 은 새 요청', async () => {
    for (const run of [(s: AnalysisService) => s.deleteAnalysis(ID), (s: AnalysisService) => s.retry(ID)]) {
      const h = heldList();
      const { service } = setup(h.route);
      const before = service.get(ID); // 진행 중 조회(붙잡힘)
      await vi.waitFor(() => expect(h.gets()).toBe(1));
      await run(service);
      const after = service.get(ID);
      h.releaseGet();
      const [old, fresh] = await Promise.all([before, after]);
      expect(old?.name).toBe('old');
      expect(fresh?.name).toBe('new');
      expect(h.gets()).toBe(2);
    }
  });
});

describe('retry — POST /analyses/{id}/retry', () => {
  it('본문 { actor: 처리자 } · 메서드 · 경로(docId 는 무시)', async () => {
    const { service, seen } = setup();
    await service.retry(ID, 'd1');
    expect(seen).toHaveLength(1);
    expect(seen[0]).toMatchObject({ method: 'POST', url: `${LIST_URL}/${ID}/retry`, body: { actor: CONFIG.user.name } });
    expect(seen[0].headers['content-type']).toBe('application/json');
  });

  it('200 · running · queued → { ok: true, started: true, message: "" } + 알림 한 번', async () => {
    for (const status of ['running', 'queued']) {
      const { service, notified } = setup(() => json(200, analysisOut({ status })));
      await expect(service.retry(ID)).resolves.toEqual({ ok: true, started: true, message: '' });
      expect(notified).toHaveBeenCalledTimes(1);
      expect(notified).toHaveBeenCalledWith();
    }
  });

  it('200 · failed · partial → { ok: false, started: false, message: 그 행의 error } (비면 기본 문구) + 알림 한 번', async () => {
    const reason = '업로드된 파일을 찾을 수 없습니다. 파일을 다시 올려 주세요.';
    const failed = setup(() => json(200, analysisOut({ status: 'failed', error: reason })));
    await expect(failed.service.retry(ID)).resolves.toEqual({ ok: false, started: false, message: reason });
    expect(failed.notified).toHaveBeenCalledTimes(1);
    const partial = setup(() => json(200, analysisOut({ status: 'partial', error: '일부 실패' })));
    await expect(partial.service.retry(ID)).resolves.toEqual({ ok: false, started: false, message: '일부 실패' });
    const empty = setup(() => json(200, analysisOut({ status: 'failed', error: null })));
    await expect(empty.service.retry(ID)).resolves.toEqual({ ok: false, started: false, message: MSG_NO_REASON });
    expect(MSG_NO_REASON).toBe('실패 이유를 받지 못했습니다.');
  });

  const failures: [number, string][] = [
    [409, '이미 분석하고 있습니다.'],
    [409, '실패한 분석만 다시 분석할 수 있습니다.'],
    [404, '분석 건을 찾을 수 없습니다.'],
    [400, '처리자 이름이 올바르지 않습니다.'],
    [502, '데이터 저장소에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.'],
    [500, '서버 설정이 빠졌습니다.'],
  ];
  for (const [status, detail] of failures) {
    it(`${status} — 거절하지 않고 { ok: false, started: false, message: "${detail}" }${status === 404 ? ' · gone' : ''} + 알림 한 번`, async () => {
      const { service, notified } = setup(() => json(status, { detail }));
      const r = await service.retry(ID);
      expect(r).toEqual(status === 404 ? { ok: false, started: false, gone: true, message: detail } : { ok: false, started: false, message: detail });
      expect(notified).toHaveBeenCalledTimes(1);
    });
  }

  /* 200 이지만 모양이 틀린 응답 — 시작한 것으로 보지 않는다(V-T2-1 m2) */
  const malformed: [string, unknown][] = [
    ['null', null],
    ['빈 배열', []],
    ['빈 객체', {}],
    ['false', false],
    ['숫자 42', 42],
    ['문자열', '시작함'],
    ['status 없음', { id: ID, name: '합성 묶음' }],
    ['모르는 status', { ...analysisOut({ status: 'running' }), status: 'started' }],
    ['status 가 문자열 아님', { ...analysisOut(), status: 1 }],
    ['다른 id 의 분석 중 행', analysisOut({ id: OTHER, status: 'running' })],
    ['id 없음', { ...analysisOut({ status: 'running' }), id: undefined }],
    ['분석 중 행이 배열에 싸임', [analysisOut({ status: 'running' })]],
  ];
  for (const [name, body] of malformed) {
    it(`200 · 모양이 틀림(${name}) → { ok: false, started: false, message: 응답을 읽지 못함 } · 알림 한 번 · 진행 중으로 적지 않음`, async () => {
      let phase = 'failed';
      const { service, notified, seen } = setup((req) => {
        if (req.url.endsWith('/retry')) return json(200, body);
        return json(200, analysisOut({ status: phase, result: phase === 'done' ? doneResult() : null }));
      });
      await service.get(ID); // 실패로 봄(끝난 것)
      await expect(service.retry(ID)).resolves.toEqual({ ok: false, started: false, message: MSG_BAD_RESPONSE });
      expect(notified).toHaveBeenCalledTimes(1); // 응답을 받았으므로 다시 불러오게 한 번
      // '진행 중으로 본 것'으로 적었다면 다음 완료 조회가 완료 알림을 낸다 — 적지 않았으므로 알림이 늘지 않는다
      phase = 'done';
      await service.get(ID);
      expect(notified).toHaveBeenCalledTimes(1);
      expect(seen.filter((r) => r.url.endsWith('/retry'))).toHaveLength(1);
    });
  }

  it('200 · 모양이 틀린 응답 뒤에도 나눠 쓰던 조회는 뗀다 — 알림 뒤 get 은 새 요청', async () => {
    const gate = deferred();
    let gets = 0;
    const { service } = setup(async (req) => {
      if (req.url.endsWith('/retry')) return json(200, null);
      const mine = ++gets;
      if (mine === 1) await gate.promise;
      return json(200, analysisOut({ status: 'failed', name: mine === 1 ? 'old' : 'new' }));
    });
    const before = service.get(ID);
    await vi.waitFor(() => expect(gets).toBe(1));
    await service.retry(ID);
    const after = service.get(ID);
    gate.resolve();
    expect((await before)?.name).toBe('old');
    expect((await after)?.name).toBe('new');
    expect(gets).toBe(2);
  });

  it('네트워크 오류 · 시간 초과 — 거절하지 않고 ok false · 알림 없음(응답을 받지 못함)', async () => {
    const { service, notified } = setup(() => {
      throw new TypeError('Failed to fetch');
    });
    await expect(service.retry(ID)).resolves.toEqual({ ok: false, started: false, message: MSG_NETWORK });
    expect(notified).not.toHaveBeenCalled();
  });

  it('다시 분석을 시작하면 완료 한 번 알림이 다시 걸린다(실패로 본 뒤에도)', async () => {
    let phase = 'failed';
    const { service, notified } = setup((req) => {
      if (req.url.endsWith('/retry')) {
        phase = 'running';
        return json(200, analysisOut({ status: 'running' }));
      }
      const out = json(200, analysisOut({ status: phase, result: phase === 'done' ? doneResult() : null }));
      return out;
    });
    await service.get(ID); // failed(끝난 것으로 봄)
    await service.retry(ID); // 알림 1(다시 분석)
    expect(notified).toHaveBeenCalledTimes(1);
    await service.get(ID); // running
    expect(notified).toHaveBeenCalledTimes(1);
    phase = 'done';
    await service.get(ID); // done → 알림 2
    expect(notified).toHaveBeenCalledTimes(2);
    await service.get(ID);
    expect(notified).toHaveBeenCalledTimes(2);
  });

  it('다시 분석 전에 보낸 조회의 늦은 "실패" 응답은 완료 알림을 망치지 않는다', async () => {
    const gate = deferred();
    let phase = 'failed';
    let gets = 0;
    const { service, notified } = setup(async (req) => {
      if (req.url.endsWith('/retry')) {
        phase = 'running';
        return json(200, analysisOut({ status: 'running' }));
      }
      const mine = ++gets;
      const status = phase; // 보낼 때의 서버 상태
      if (mine === 2) await gate.promise; // 다시 분석 전에 보낸 조회(실패 값)를 붙잡는다
      return json(200, analysisOut({ status, result: status === 'done' ? doneResult() : null }));
    });
    await service.get(ID); // 1 failed
    const late = service.get(ID); // 2 failed(붙잡힘)
    await vi.waitFor(() => expect(gets).toBe(2));
    await service.retry(ID); // started — 진행 중으로 다시 적음, 알림 1
    gate.resolve();
    expect((await late)?.status).toBe('failed'); // 그 호출자에게는 옛 값
    expect(notified).toHaveBeenCalledTimes(1); // 늦은 '실패'로 '끝남'을 알리지 않는다
    phase = 'done';
    await service.get(ID); // 3 done → 완료 알림
    expect(notified).toHaveBeenCalledTimes(2);
  });
});

describe('deleteAnalysis — DELETE /analyses/{id}', () => {
  it('204 → 끝(값 없음), 본문 없이 DELETE, 알림 한 번', async () => {
    const { service, seen, notified } = setup();
    await expect(service.deleteAnalysis(ID)).resolves.toBeUndefined();
    expect(seen).toHaveLength(1);
    expect(seen[0]).toMatchObject({ method: 'DELETE', url: `${LIST_URL}/${ID}`, body: undefined });
    expect(seen[0].headers).not.toHaveProperty('content-type');
    expect(notified).toHaveBeenCalledTimes(1);
    expect(notified).toHaveBeenCalledWith();
  });

  it('상태 기록을 지운다 — 지우기 전에 분석 중으로 본 분석이 그 뒤 완료로 보여도 알리지 않는다', async () => {
    let phase = 'running';
    const { service, notified } = setup((req) => (req.method === 'DELETE' ? noContent() : json(200, analysisOut({ status: phase, result: phase === 'done' ? doneResult() : null }))));
    await service.get(ID); // running
    await service.deleteAnalysis(ID); // 알림 1
    phase = 'done';
    await service.get(ID); // 처음 본 분석처럼 — 알리지 않는다
    expect(notified).toHaveBeenCalledTimes(1);
  });

  it('404 → ApiError(not_found) 로 거절하되 알린다(목록에서 빠지게)', async () => {
    const { service, notified } = setup(() => json(404, { detail: '분석 건을 찾을 수 없습니다.' }));
    const err = await service.deleteAnalysis(ID).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 404, code: 'not_found', message: '분석 건을 찾을 수 없습니다.' });
    expect(notified).toHaveBeenCalledTimes(1);
  });

  it('502 · 네트워크 → 그 ApiError 로 거절, 알림 없음', async () => {
    const detail = '원본 파일을 지우지 못했습니다. 잠시 후 다시 시도해 주세요.';
    const s = setup(() => json(502, { detail }));
    await expect(s.service.deleteAnalysis(ID)).rejects.toMatchObject({ status: 502, code: 'server', message: detail });
    expect(s.notified).not.toHaveBeenCalled();
    const n = setup(() => {
      throw new TypeError('Failed to fetch');
    });
    await expect(n.service.deleteAnalysis(ID)).rejects.toMatchObject({ code: 'network' });
    expect(n.notified).not.toHaveBeenCalled();
  });
});

describe('브라우저 저장소를 쓰지 않는다(목록은 서버가 준다)', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sessionStorage · localStorage 를 읽거나 쓰지 않는다(요청 · 목록 · 조회 · 다시 분석 · 삭제)', async () => {
    const storage = { getItem: vi.fn(() => null), setItem: vi.fn(), removeItem: vi.fn(), clear: vi.fn(), key: vi.fn(), length: 0 };
    vi.stubGlobal('sessionStorage', storage);
    vi.stubGlobal('localStorage', storage);
    vi.stubGlobal('window', { sessionStorage: storage, localStorage: storage });
    const { service } = setup();
    await service.requestAnalysis({ name: 'x', files: [pdf()] });
    await service.list();
    await service.get(ID);
    await service.retry(ID);
    await service.deleteAnalysis(ID);
    expect(storage.getItem).not.toHaveBeenCalled();
    expect(storage.setItem).not.toHaveBeenCalled();
    expect(storage.removeItem).not.toHaveBeenCalled();
  });

  it('실제 분석 서비스 앱 코드(src/services/api, 테스트 제외)에 sessionStorage · localStorage 가 없다', () => {
    const dir = fileURLToPath(new URL('.', import.meta.url));
    const files = readdirSync(dir).filter((f) => f.endsWith('.ts') && !f.endsWith('.test.ts'));
    expect(files).toContain('service.ts');
    expect(files).not.toContain('session-list.ts');
    expect(files).not.toContain('browser-storage.ts');
    for (const f of files) {
      const text = readFileSync(join(dir, f), 'utf8');
      expect(text, f).not.toMatch(/sessionStorage|localStorage/);
    }
  });
});

describe('그 밖의 메서드', () => {
  it('sampleFiles 는 []', async () => {
    const { service } = setup();
    expect(await service.sampleFiles()).toEqual([]);
  });

  it('연결 판단은 지원하지 않는다고 거절(요청 없음 — 검토사항은 item-service.test.ts · 내보내기는 export-service.test.ts)', async () => {
    const { service, seen } = setup();
    const err = await service.decideLink(ID, 'l', 'linked', '').catch((e: unknown) => e);
    expect((err as Error).message).toBe(MSG_UNSUPPORTED);
    expect(seen).toHaveLength(0);
  });

  it('구독 해제 뒤에는 알리지 않는다', async () => {
    const { service } = setup();
    const fn = vi.fn();
    const off = service.subscribe(fn);
    off();
    await service.requestAnalysis({ name: 'x', files: [pdf()] });
    await service.deleteAnalysis(ID);
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
