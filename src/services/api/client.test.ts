import http from 'node:http';
import type { AddressInfo } from 'node:net';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  MSG_BAD_REQUEST,
  MSG_BAD_RESPONSE,
  MSG_NETWORK,
  MSG_NOT_FOUND,
  MSG_SERVER,
  MSG_TIMEOUT,
  apiErrorAnalysisId,
  apiErrorCode,
  codeForStatus,
  createApiClient,
} from './client';
import { analysisOut, fakeFetch, json, listItemOut } from './testing';

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

describe('reviewAction — POST /analyses/{id}/review-actions', () => {
  it('JSON 본문(계약 id 는 본문에 — 짝 없는 서로게이트 · \u0000 · 따옴표 · / 그대로) · Content-Type · 200 응답 그대로', async () => {
    const reply = { analysis: analysisOut({ status: 'done', review: { status: 'needed' } }), changed: false };
    const { fetch, seen } = fakeFetch(() => json(200, reply));
    const client = createApiClient({ fetch });
    const fid = '0:a/b"c\ud800\u0000?#';
    const out = await client.reviewAction(ID, { type: 'set_status', actor: '김민지', finding_id: fid, status: 'confirmed', reason: '' });
    expect(out).toEqual(reply);
    expect(seen).toHaveLength(1);
    expect(seen[0].method).toBe('POST');
    expect(seen[0].url).toBe(`/api/py/analyses/${ID}/review-actions`);
    expect(seen[0].headers['content-type']).toBe('application/json');
    expect(seen[0].headers.accept).toBe('application/json');
    expect(seen[0].body).toEqual({ type: 'set_status', actor: '김민지', finding_id: fid, status: 'confirmed', reason: '' });
  });

  it('분석 id 는 주소 조각으로 감싼다', async () => {
    const { fetch, seen } = fakeFetch(() => json(200, { analysis: analysisOut(), changed: true }));
    await createApiClient({ fetch }).reviewAction('a b/c', { type: 'save_memo', actor: '김민지', text: '메모' });
    expect(seen[0].url).toBe('/api/py/analyses/a%20b%2Fc/review-actions');
    expect(seen[0].body).toEqual({ type: 'save_memo', actor: '김민지', text: '메모' });
  });

  const cases: [number, string, string][] = [
    [400, 'bad_request', '요청 형식이 올바르지 않습니다.'],
    [404, 'not_found', '탐지 항목을 찾을 수 없습니다.'],
    [409, 'conflict', '검토를 완료한 분석은 바꿀 수 없습니다.'],
    [413, 'bad_request', '요청 본문이 너무 큽니다.'],
    [502, 'server', '서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.'],
  ];
  for (const [status, code, detail] of cases) {
    it(`${status} → ApiError ${code} + 서버 detail`, async () => {
      const { fetch } = fakeFetch(() => json(status, { detail }));
      const err = await createApiClient({ fetch })
        .reviewAction(ID, { type: 'complete_review', actor: '김민지', note: '' })
        .catch((e: unknown) => e);
      expect(err).toBeInstanceOf(ApiError);
      expect(err).toMatchObject({ status, code, message: detail });
    });
  }

  it('detail 이 없으면 기본 문구, 네트워크 오류 → network', async () => {
    const { fetch } = fakeFetch(() => new Response('', { status: 413 }));
    await expect(createApiClient({ fetch }).reviewAction(ID, { type: 'save_memo', actor: 'x', text: '' })).rejects.toMatchObject({
      status: 413,
      code: 'bad_request',
      message: MSG_BAD_REQUEST,
    });
    const down = (async () => {
      throw new TypeError('Failed to fetch');
    }) as typeof globalThis.fetch;
    await expect(createApiClient({ fetch: down }).reviewAction(ID, { type: 'save_memo', actor: 'x', text: '' })).rejects.toMatchObject({
      status: 0,
      code: 'network',
      message: MSG_NETWORK,
    });
  });
});

describe('listAnalyses — GET /analyses', () => {
  it('GET /api/py/analyses(limit 없이) · 본문 없음 · Accept JSON · 응답 그대로', async () => {
    const body = { analyses: [listItemOut()] };
    const { fetch, seen } = fakeFetch(() => json(200, body));
    const out = await createApiClient({ fetch }).listAnalyses();
    expect(out).toEqual(body);
    expect(seen).toHaveLength(1);
    expect(seen[0]).toMatchObject({ method: 'GET', url: '/api/py/analyses', body: undefined });
    expect(seen[0].headers.accept).toBe('application/json');
    expect(seen[0].headers).not.toHaveProperty('content-type');
  });

  it('400 · 502 → ApiError(백엔드 detail)', async () => {
    const bad = fakeFetch(() => json(400, { detail: '요청 형식이 올바르지 않습니다.' }));
    await expect(createApiClient({ fetch: bad.fetch }).listAnalyses()).rejects.toMatchObject({ status: 400, code: 'bad_request', message: '요청 형식이 올바르지 않습니다.' });
    const down = fakeFetch(() => json(502, { detail: '데이터 저장소에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.' }));
    await expect(createApiClient({ fetch: down.fetch }).listAnalyses()).rejects.toMatchObject({ status: 502, code: 'server' });
  });
});

describe('deleteAnalysis — DELETE /analyses/{id}', () => {
  it('204 — 본문을 읽지 않고 undefined, DELETE · 주소 조각 · 본문 없음', async () => {
    const json204 = vi.fn(async () => {
      throw new SyntaxError('Unexpected end of JSON input');
    });
    const text204 = vi.fn(async () => '');
    const { fetch, seen } = fakeFetch(() => ({ ok: true, status: 204, json: json204, text: text204 }) as unknown as Response);
    await expect(createApiClient({ fetch }).deleteAnalysis('a/b')).resolves.toBeUndefined();
    expect(json204).not.toHaveBeenCalled();
    expect(text204).not.toHaveBeenCalled();
    expect(seen).toHaveLength(1);
    expect(seen[0]).toMatchObject({ method: 'DELETE', url: '/api/py/analyses/a%2Fb', body: undefined });
    expect(seen[0].headers).not.toHaveProperty('content-type');
  });

  it('실제 204 Response(본문 null)도 끝', async () => {
    const { fetch } = fakeFetch(() => new Response(null, { status: 204 }));
    await expect(createApiClient({ fetch }).deleteAnalysis(ID)).resolves.toBeUndefined();
  });

  it('404 · 502 · 네트워크 → 다른 요청과 같은 오류 모양', async () => {
    const gone = fakeFetch(() => json(404, { detail: '분석 건을 찾을 수 없습니다.' }));
    const e404 = await createApiClient({ fetch: gone.fetch }).deleteAnalysis(ID).catch((e: unknown) => e);
    expect(e404).toBeInstanceOf(ApiError);
    expect(e404).toMatchObject({ status: 404, code: 'not_found', message: '분석 건을 찾을 수 없습니다.' });
    const bare = fakeFetch(() => new Response('', { status: 404 }));
    await expect(createApiClient({ fetch: bare.fetch }).deleteAnalysis(ID)).rejects.toMatchObject({ status: 404, code: 'not_found', message: MSG_NOT_FOUND });
    const failed = fakeFetch(() => json(502, { detail: '원본 파일을 지우지 못했습니다. 잠시 후 다시 시도해 주세요.' }));
    await expect(createApiClient({ fetch: failed.fetch }).deleteAnalysis(ID)).rejects.toMatchObject({
      status: 502,
      code: 'server',
      message: '원본 파일을 지우지 못했습니다. 잠시 후 다시 시도해 주세요.',
    });
    const net = fakeFetch(() => {
      throw new TypeError('Failed to fetch');
    });
    await expect(createApiClient({ fetch: net.fetch }).deleteAnalysis(ID)).rejects.toMatchObject({ status: 0, code: 'network', message: MSG_NETWORK });
  });
});

describe('retryAnalysis — POST /analyses/{id}/retry', () => {
  it('본문 { actor } · POST · Content-Type JSON · 200 응답 그대로', async () => {
    const row = analysisOut({ status: 'running', started_at: '2026-11-04T01:00:00Z' });
    const { fetch, seen } = fakeFetch(() => json(200, row));
    const out = await createApiClient({ fetch }).retryAnalysis(ID, { actor: '이지은' });
    expect(out).toEqual(row);
    expect(seen).toHaveLength(1);
    expect(seen[0]).toMatchObject({ method: 'POST', url: `/api/py/analyses/${ID}/retry`, body: { actor: '이지은' } });
    expect(seen[0].headers['content-type']).toBe('application/json');
  });

  it('409 · 404 → ApiError(conflict · not_found, 백엔드 detail)', async () => {
    const busy = fakeFetch(() => json(409, { detail: '이미 분석하고 있습니다.' }));
    await expect(createApiClient({ fetch: busy.fetch }).retryAnalysis(ID, { actor: 'a' })).rejects.toMatchObject({ status: 409, code: 'conflict', message: '이미 분석하고 있습니다.' });
    const gone = fakeFetch(() => json(404, { detail: '분석 건을 찾을 수 없습니다.' }));
    await expect(createApiClient({ fetch: gone.fetch }).retryAnalysis(ID, { actor: 'a' })).rejects.toMatchObject({ status: 404, code: 'not_found' });
  });
});

describe('워크플로우 설정 — POST /settings/workflow…', () => {
  const out = { agent_id: 'agt_x', config_id: '60', agent_name: 'v2_full', config_name: '최종' };

  it('비밀번호는 본문에 담고, 주소·헤더에는 넣지 않는다', async () => {
    const { fetch, seen } = fakeFetch(() => json(200, out));
    const client = createApiClient({ fetch });
    await expect(client.openWorkflowSettings('pw-test')).resolves.toEqual({ ...out, presets: [] });
    await expect(client.saveWorkflowSettings({ password: 'pw-test', agent_id: 'agt_x', config_id: '60' })).resolves.toEqual(out);
    await client.addWorkflowPreset({ password: 'pw-test', name: '이름', agent_id: 'agt_x', config_id: '60' });
    await client.deleteWorkflowPreset({ password: 'pw-test', id: ID });
    expect(seen.map((r) => [r.method, r.url])).toEqual([
      ['POST', '/api/py/settings/workflow/open'],
      ['POST', '/api/py/settings/workflow'],
      ['POST', '/api/py/settings/workflow/presets'],
      ['POST', '/api/py/settings/workflow/presets/delete'],
    ]);
    expect(seen[0].body).toEqual({ password: 'pw-test' });
    expect(seen[1].body).toEqual({ password: 'pw-test', agent_id: 'agt_x', config_id: '60' });
    expect(seen[2].body).toEqual({ password: 'pw-test', name: '이름', agent_id: 'agt_x', config_id: '60' });
    expect(seen[3].body).toEqual({ password: 'pw-test', id: ID });
    for (const r of seen) {
      expect(JSON.stringify(r.headers)).not.toContain('pw-test');
      expect(r.url).not.toContain('pw-test');
    }
  });

  it('목록은 응답의 presets 를 그대로(등록한 순서 유지)', async () => {
    const presets = [
      { id: 'b', name: '둘째', agent_id: 'agt_b', config_id: '2' },
      { id: 'a', name: '첫째', agent_id: 'agt_a', config_id: '1' },
    ];
    const { fetch } = fakeFetch((req) => json(200, req.url.endsWith('/open') ? { ...out, presets } : { presets }));
    const client = createApiClient({ fetch });
    await expect(client.openWorkflowSettings('x')).resolves.toEqual({ ...out, presets });
    await expect(client.addWorkflowPreset({ password: 'x', name: 'n', agent_id: 'agt_x', config_id: '1' })).resolves.toEqual({ presets });
    await expect(client.deleteWorkflowPreset({ password: 'x', id: ID })).resolves.toEqual({ presets });
  });

  it.each([[undefined], [null], ['목록'], [{ id: 'a' }], [3]])('presets 가 배열이 아니면(%j) 빈 목록으로 읽는다', async (presets) => {
    const { fetch } = fakeFetch((req) => json(200, req.url.endsWith('/open') ? { ...out, presets } : { presets }));
    const client = createApiClient({ fetch });
    await expect(client.openWorkflowSettings('x')).resolves.toEqual({ ...out, presets: [] });
    await expect(client.addWorkflowPreset({ password: 'x', name: 'n', agent_id: 'agt_x', config_id: '1' })).resolves.toEqual({ presets: [] });
    await expect(client.deleteWorkflowPreset({ password: 'x', id: ID })).resolves.toEqual({ presets: [] });
  });

  it('모양이 틀린 항목은 뺀다', async () => {
    const good = { id: 'a', name: '첫째', agent_id: 'agt_a', config_id: '1' };
    const presets = [null, 'x', 1, { ...good, config_id: 60 }, { id: 'b', name: '이름만' }, good];
    const { fetch } = fakeFetch(() => json(200, { ...out, presets }));
    await expect(createApiClient({ fetch }).openWorkflowSettings('x')).resolves.toEqual({ ...out, presets: [good] });
  });

  it('등록 · 삭제 실패는 서버 문장 그대로(409 는 conflict)', async () => {
    const taken = fakeFetch(() => json(409, { detail: '같은 이름의 워크플로우가 이미 있습니다.' }));
    await expect(
      createApiClient({ fetch: taken.fetch }).addWorkflowPreset({ password: 'x', name: 'n', agent_id: 'agt_x', config_id: '1' }),
    ).rejects.toMatchObject({ status: 409, code: 'conflict', message: '같은 이름의 워크플로우가 이미 있습니다.' });
    const bad = fakeFetch(() => json(400, { detail: '요청 형식이 올바르지 않습니다.' }));
    await expect(createApiClient({ fetch: bad.fetch }).deleteWorkflowPreset({ password: 'x', id: 'nope' })).rejects.toMatchObject({
      status: 400,
      message: '요청 형식이 올바르지 않습니다.',
    });
  });

  it('틀린 비밀번호 · 없는 워크플로우는 서버 문장 그대로', async () => {
    const wrong = fakeFetch(() => json(401, { detail: '비밀번호가 맞지 않습니다.' }));
    await expect(createApiClient({ fetch: wrong.fetch }).openWorkflowSettings('x')).rejects.toMatchObject({
      status: 401,
      code: 'bad_request',
      message: '비밀번호가 맞지 않습니다.',
    });
    const missing = fakeFetch(() => json(400, { detail: 'Upstage 에 없는 에이전트 또는 설정 번호입니다.' }));
    await expect(
      createApiClient({ fetch: missing.fetch }).saveWorkflowSettings({ password: 'x', agent_id: 'agt_x', config_id: '1' }),
    ).rejects.toMatchObject({ status: 400, message: 'Upstage 에 없는 에이전트 또는 설정 번호입니다.' });
  });
});
