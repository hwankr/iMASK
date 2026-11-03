import http from 'node:http';
import type { AddressInfo } from 'node:net';
import { afterEach, describe, expect, it } from 'vitest';
import {
  ApiError,
  MSG_BAD_REQUEST,
  MSG_BAD_RESPONSE,
  MSG_NETWORK,
  MSG_SERVER,
  MSG_TIMEOUT,
  apiErrorAnalysisId,
  apiErrorCode,
  codeForStatus,
  createApiClient,
} from './client';
import { analysisOut, fakeFetch, json } from './testing';

const ID = 'ab12cd34-0000-4000-8000-000000000000';

describe('요청 모양', () => {
  it('같은 출처 /api/py, 사용자 지정 헤더 없음(접근 코드 헤더도 없다)', async () => {
    const { fetch, seen } = fakeFetch((req) => (req.method === 'GET' ? json(200, analysisOut()) : req.url.endsWith('/start') ? json(200, analysisOut({ status: 'running' })) : json(201, { analysis: analysisOut(), upload: {} })));
    const client = createApiClient({ fetch });
    await client.createAnalysis({ name: 'n', filename: 'a.pdf', size: 10, mime_type: 'application/pdf' });
    await client.startAnalysis(ID);
    await client.getAnalysis(ID);
    expect(seen.map((r) => [r.method, r.url])).toEqual([
      ['POST', '/api/py/analyses'],
      ['POST', `/api/py/analyses/${ID}/start`],
      ['GET', `/api/py/analyses/${ID}`],
    ]);
    for (const r of seen) expect(r.headers).not.toHaveProperty('x-demo-code');
    expect(seen[0].headers['content-type']).toBe('application/json');
    expect(seen[0].body).toEqual({ name: 'n', filename: 'a.pdf', size: 10, mime_type: 'application/pdf' });
    expect(seen[1].body).toBeUndefined();
  });

  it('getAnalysis(id, { includeStages: true }) 만 ?include=stages 를 붙인다', async () => {
    const { fetch, seen } = fakeFetch(() => json(200, analysisOut()));
    const client = createApiClient({ fetch });
    await client.getAnalysis(ID, { includeStages: true });
    await client.getAnalysis(ID, { includeStages: false });
    await client.getAnalysis(ID, {});
    await client.getAnalysis(ID);
    expect(seen.map((r) => [r.method, r.url])).toEqual([
      ['GET', `/api/py/analyses/${ID}?include=stages`],
      ['GET', `/api/py/analyses/${ID}`],
      ['GET', `/api/py/analyses/${ID}`],
      ['GET', `/api/py/analyses/${ID}`],
    ]);
  });

  it('getFile — GET /analyses/{id}/file · JSON 응답을 그대로', async () => {
    const body = { url: 'https://storage.example.test/object/sign/documents/a.pdf?token=fixture-token', mime_type: 'application/pdf', filename: 'a.pdf' };
    const { fetch, seen } = fakeFetch(() => json(200, body));
    const out = await createApiClient({ fetch }).getFile('a/b');
    expect(out).toEqual(body);
    expect(seen).toHaveLength(1);
    expect(seen[0]).toMatchObject({ method: 'GET', url: '/api/py/analyses/a%2Fb/file', body: undefined });
    expect(seen[0].headers.accept).toBe('application/json');
  });

  it('getFile 오류 — 404 는 백엔드 detail 그대로, 네트워크 · 시간 초과는 다른 요청과 같다', async () => {
    const cases: [number, string, string][] = [
      [404, 'not_found', '원본 파일을 찾을 수 없습니다.'],
      [500, 'server', '서버 설정이 빠졌습니다.'],
    ];
    for (const [status, code, detail] of cases) {
      const { fetch } = fakeFetch(() => json(status, { detail }));
      await expect(createApiClient({ fetch }).getFile(ID)).rejects.toMatchObject({ status, code, message: detail });
    }
    const down = (async () => {
      throw new TypeError('Failed to fetch');
    }) as typeof globalThis.fetch;
    await expect(createApiClient({ fetch: down }).getFile(ID)).rejects.toMatchObject({ status: 0, code: 'network', message: MSG_NETWORK });
    const hang = ((_: unknown, init?: RequestInit) =>
      new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
      })) as typeof globalThis.fetch;
    await expect(createApiClient({ fetch: hang, timeoutMs: 5 }).getFile(ID)).rejects.toMatchObject({ code: 'network', message: MSG_TIMEOUT });
  });

  it('id 는 주소 조각으로 감싼다 · baseUrl 끝 / 는 뗀다', async () => {
    const { fetch, seen } = fakeFetch(() => json(200, analysisOut()));
    await createApiClient({ fetch, baseUrl: 'http://x/api/py/' }).getAnalysis('a/b?c');
    expect(seen[0].url).toBe('http://x/api/py/analyses/a%2Fb%3Fc');
  });
});

describe('오류 → ApiError', () => {
  const cases: [number, string, string][] = [
    [401, 'bad_request', '권한이 없습니다.'],
    [404, 'not_found', '분석 건을 찾을 수 없습니다.'],
    [409, 'conflict', '이미 시작한 분석입니다.'],
    [400, 'bad_request', '파일 이름이 비었습니다.'],
    [500, 'server', '서버 설정이 빠졌습니다: UPSTAGE_CONFIG_ID'],
    [502, 'server', '분석을 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.'],
  ];
  for (const [status, code, detail] of cases) {
    it(`${status} → ${code} + 서버 detail`, async () => {
      const { fetch } = fakeFetch(() => json(status, { detail }));
      const err = await createApiClient({ fetch })
        .getAnalysis(ID)
        .catch((e: unknown) => e);
      expect(err).toBeInstanceOf(ApiError);
      expect(err).toMatchObject({ status, code, message: detail });
      expect(apiErrorCode(err)).toBe(code);
    });
  }

  it('detail 이 없거나 JSON 이 아니면 기본 문구', async () => {
    const { fetch } = fakeFetch(() => new Response('<html>Internal Server Error</html>', { status: 500 }));
    await expect(createApiClient({ fetch }).getAnalysis(ID)).rejects.toMatchObject({ status: 500, code: 'server', message: MSG_SERVER });
    const { fetch: f2 } = fakeFetch(() => json(401, { detail: 7 }));
    await expect(createApiClient({ fetch: f2 }).getAnalysis(ID)).rejects.toMatchObject({ code: 'bad_request', message: MSG_BAD_REQUEST });
    expect(codeForStatus(401)).toBe('bad_request');
    expect(codeForStatus(413)).toBe('bad_request');
    expect(codeForStatus(503)).toBe('server');
  });

  it('네트워크 오류 → network(status 0) + 한국어 문구', async () => {
    const fetch = (async () => {
      throw new TypeError('Failed to fetch');
    }) as typeof globalThis.fetch;
    const err = await createApiClient({ fetch })
      .getAnalysis(ID)
      .catch((e: unknown) => e);
    expect(err).toMatchObject({ status: 0, code: 'network', message: MSG_NETWORK });
  });

  it('시간 초과 → network + 시간 초과 문구', async () => {
    const fetch = ((_: unknown, init?: RequestInit) =>
      new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
      })) as typeof globalThis.fetch;
    await expect(createApiClient({ fetch, timeoutMs: 5 }).getAnalysis(ID)).rejects.toMatchObject({ code: 'network', message: MSG_TIMEOUT });
  });

  it('성공 응답이 JSON 이 아니면 server', async () => {
    const { fetch } = fakeFetch(() => new Response('ok', { status: 200 }));
    await expect(createApiClient({ fetch }).getAnalysis(ID)).rejects.toMatchObject({ code: 'server', message: MSG_BAD_RESPONSE });
  });

  it('apiErrorCode — ApiError 가 아니면 null', () => {
    expect(apiErrorCode(new Error('x'))).toBeNull();
    expect(apiErrorCode(undefined)).toBeNull();
  });

  it('apiErrorAnalysisId — 담긴 분석 id(없으면 null)', () => {
    expect(apiErrorAnalysisId(new ApiError(502, 'server', 'x', ID))).toBe(ID);
    expect(apiErrorAnalysisId(new ApiError(502, 'server', 'x'))).toBeNull();
    expect(apiErrorAnalysisId(new Error('x'))).toBeNull();
  });
});

describe('시간 제한은 본문을 다 읽을 때까지', () => {
  const servers: http.Server[] = [];
  afterEach(async () => {
    await Promise.all(servers.splice(0).map((s) => new Promise<void>((r) => s.close(() => r()))));
  });

  /** 실제 HTTP — 헤더는 바로 보내고 본문은 bodyDelayMs 뒤에(또는 끝내지 않음) */
  async function slowBodyServer(status: number, bodyDelayMs: number | null): Promise<string> {
    const server = http.createServer((_req, res) => {
      res.writeHead(status, { 'Content-Type': 'application/json' });
      res.flushHeaders();
      res.write('{"detail":');
      if (bodyDelayMs !== null) setTimeout(() => res.end(status === 200 ? '"x","id":"a"}' : '"늦은 오류"}'), bodyDelayMs);
    });
    servers.push(server);
    await new Promise<void>((r) => server.listen(0, '127.0.0.1', () => r()));
    server.on('connection', (socket) => server.once('close', () => socket.destroy()));
    return 'http://127.0.0.1:' + (server.address() as AddressInfo).port + '/api/py';
  }

  const cases: [string, number, number | null][] = [
    ['200 + 늦은 본문', 200, 400],
    ['200 + 멈춘 본문', 200, null],
    ['500 + 늦은 오류 본문', 500, 400],
    ['401 + 멈춘 오류 본문', 401, null],
  ];
  for (const [label, status, delay] of cases) {
    it(`${label} → 제한 시간에 network + 시간 초과 문구`, async () => {
      const baseUrl = await slowBodyServer(status, delay);
      const started = Date.now();
      const err = await createApiClient({ baseUrl, timeoutMs: 60 })
        .getAnalysis(ID)
        .catch((e: unknown) => e);
      const took = Date.now() - started;
      expect(err).toBeInstanceOf(ApiError);
      expect(err).toMatchObject({ status: 0, code: 'network', message: MSG_TIMEOUT });
      expect(took).toBeLessThan(350);
    });
  }

  it('signal 을 무시하는 fetch 의 멈춘 본문도 제한 시간에 끝난다', async () => {
    const stalled = () => new ReadableStream<Uint8Array>({ start() {} }); // 아무것도 보내지 않고 끝나지도 않음
    const fetch200 = (async () => new Response(stalled(), { status: 200 })) as typeof globalThis.fetch;
    const fetch502 = (async () => new Response(stalled(), { status: 502 })) as typeof globalThis.fetch;
    for (const fetch of [fetch200, fetch502]) {
      await expect(createApiClient({ fetch, timeoutMs: 20 }).getAnalysis(ID)).rejects.toMatchObject({ code: 'network', message: MSG_TIMEOUT });
    }
  });

  it('제한 안에 끝난 본문은 그대로(타이머가 다음 요청에 남지 않음)', async () => {
    const baseUrl = await slowBodyServer(200, 10);
    await expect(createApiClient({ baseUrl, timeoutMs: 2000 }).getAnalysis(ID)).resolves.toMatchObject({ detail: 'x', id: 'a' });
  });
});
