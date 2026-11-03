import { afterEach, describe, expect, it, vi } from 'vitest';
import { ACCESS_CODE_KEY } from './access-code';
import { ApiError, MSG_NETWORK, MSG_TIMEOUT, MSG_UNAUTHORIZED, createApiClient } from './client';
import { FILE_MAX_BYTES, MSG_FILE_BAD_URL, MSG_FILE_DOWNLOAD, MSG_FILE_EMPTY, MSG_FILE_NOT_FOUND, MSG_FILE_TIMEOUT, MSG_FILE_TOO_LARGE, isAllowedFileUrl } from './file-download';
import { createApiService } from './service';
import { analysisOut, contractResult, documentOut, fakeFetch, json, memoryStorage, type SeenRequest } from './testing';

const ID = 'ab12cd34-0000-4000-8000-000000000000';
/** 가짜 서명 토큰 — 키 모양이 아닌 뻔한 가짜 값(실행 중에 조립) */
const TOKEN = ['fixture', 'signed', 'token', 'value'].join('-');
const HOST = 'storage.example.test';
/** n 번째로 받은 가짜 서명 다운로드 주소 */
const signed = (n: number) => `https://${HOST}/storage/v1/object/sign/documents/analyses/${ID}/iMASK_smoke_bundle.pdf?token=${TOKEN}${n}`;
const PDF = new TextEncoder().encode('%PDF-1.7 합성 묶음');
const MiB = 1024 * 1024;

type Route = (req: SeenRequest, n: number) => Response | Promise<Response>;
type Download = (url: string, init: RequestInit | undefined) => Response | Promise<Response>;

interface SetupOptions {
  /** GET …/file 응답(n = 몇 번째 /file 요청인지, 1부터) */
  file?: Route;
  /** GET …/{id}(?include=stages) 응답 */
  analysis?: Route;
  /** 서명 주소 받기 응답 */
  download?: Download;
  fileTimeoutMs?: number;
  /** 백엔드 요청 시간 제한(밀리초) — 기본 60초 */
  clientTimeoutMs?: number;
}

/** 실제 분석 서비스 + 가짜 백엔드 + 가짜 Storage — order 에 일어난 순서를 남긴다 */
function setup(opts: SetupOptions = {}) {
  const order: string[] = [];
  const downloads: { url: string; init: RequestInit | undefined }[] = [];
  const storage = memoryStorage({ [ACCESS_CODE_KEY]: 'code-123' });
  let fileCalls = 0;
  const backend = fakeFetch((req) => {
    order.push('backend ' + req.method + ' ' + req.url.replace('/api/py', ''));
    if (req.url.endsWith('/file')) {
      fileCalls += 1;
      return opts.file ? opts.file(req, fileCalls) : json(200, { url: signed(fileCalls), mime_type: 'application/pdf', filename: 'iMASK_smoke_bundle.pdf' });
    }
    return opts.analysis ? opts.analysis(req, 0) : json(200, analysisOut({ status: 'done', result: { ...contractResult(), stages: [{ key: '서류-인식' }, { key: '민감정보_추출' }] } }));
  });
  const fileFetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    order.push('download ' + url);
    downloads.push({ url, init });
    return opts.download ? opts.download(url, init) : new Response(PDF, { status: 200, headers: { 'Content-Type': 'application/pdf' } });
  }) as typeof fetch;
  const client = createApiClient({ fetch: backend.fetch, getAccessCode: () => (storage.getItem(ACCESS_CODE_KEY) ?? '').trim(), timeoutMs: opts.clientTimeoutMs });
  const service = createApiService({ client, upload: async () => {}, storage, fileFetch, fileTimeoutMs: opts.fileTimeoutMs });
  return { service, order, downloads, seen: backend.seen };
}

/** 같은 조각을 times 번 보내는 본문 */
function chunked(chunk: Uint8Array, times: number): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (let i = 0; i < times; i++) controller.enqueue(chunk);
      controller.close();
    },
  });
}

/** 오류 어디에도(문구 · 문자열 · 스택 · JSON · cause) 서명 주소 · 토큰이 없다 */
function expectNoSecret(err: unknown) {
  expect(err).toBeInstanceOf(ApiError);
  const e = err as ApiError;
  const texts = [e.message, String(e), e.stack ?? '', JSON.stringify(e), JSON.stringify(Object.getOwnPropertyNames(e).map((k) => String((e as unknown as Record<string, unknown>)[k])))];
  for (const t of texts) {
    expect(t).not.toContain(HOST);
    expect(t).not.toContain(TOKEN);
    expect(t).not.toContain('token=');
  }
  expect(e.cause).toBeUndefined();
}

/**
 * 거절되는지, 오류 어디에도(expectNoSecret) · 콘솔에도 서명 주소 · 토큰이 없는지 확인하고 오류를 돌려준다.
 * 콘솔은 부른 적 자체가 없어야 한다(앱 코드는 이 경로에서 콘솔을 쓰지 않는다).
 */
async function expectSafeRejection(run: () => Promise<unknown>): Promise<ApiError> {
  const spies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) => vi.spyOn(console, m).mockImplementation(() => {}));
  let caught: unknown;
  try {
    await run();
  } catch (err) {
    caught = err;
  }
  try {
    expect(caught).toBeDefined();
    expectNoSecret(caught);
    for (const spy of spies) {
      const logged = spy.mock.calls.map((args) => args.map(String).join(' ')).join('\n');
      expect(logged).not.toContain(HOST);
      expect(logged).not.toContain(TOKEN);
      expect(spy).not.toHaveBeenCalled();
    }
  } finally {
    for (const spy of spies) spy.mockRestore();
  }
  return caught as ApiError;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('loadFile — 원본 파일 받기', () => {
  it('/file 로 서명 주소를 받은 다음 그 주소에서 받는다(내용 · 형식 · 이름)', async () => {
    const { service, order } = setup();
    const file = await service.loadFile(ID);
    expect(new Uint8Array(file.bytes)).toEqual(PDF);
    expect(file.bytes).toBeInstanceOf(ArrayBuffer);
    expect(file.mime).toBe('application/pdf');
    expect(file.filename).toBe('iMASK_smoke_bundle.pdf');
    expect(order).toEqual([`backend GET /analyses/${ID}/file`, `download ${signed(1)}`]);
  });

  it('부를 때마다 새 서명 주소를 받는다(캐시하지 않음 — 10분 만료 대비)', async () => {
    const { service, order, downloads } = setup();
    await service.loadFile(ID);
    await service.loadFile(ID);
    expect(order).toEqual([`backend GET /analyses/${ID}/file`, `download ${signed(1)}`, `backend GET /analyses/${ID}/file`, `download ${signed(2)}`]);
    expect(downloads.map((d) => d.url)).toEqual([signed(1), signed(2)]);
  });

  it('받기 요청 — X-Demo-Code 등 사용자 지정 헤더 없음 · credentials omit · cache no-store, /file 요청에만 접근 코드', async () => {
    const { service, downloads, seen } = setup();
    await service.loadFile(ID);
    const init = downloads[0].init;
    expect(init?.method).toBe('GET');
    expect(init?.credentials).toBe('omit');
    expect(init?.cache).toBe('no-store');
    expect(init?.referrerPolicy).toBe('no-referrer');
    expect(init?.body).toBeUndefined();
    const headers: string[] = [];
    new Headers(init?.headers).forEach((_v, k) => headers.push(k));
    expect(headers).toEqual([]);
    expect(seen[0].headers['x-demo-code']).toBe('code-123');
  });

  it('주소 검사 — https · http://localhost · http://127.0.0.1 만 받는다(그 밖은 요청하지 않고 오류)', async () => {
    const bad: unknown[] = [
      'javascript:alert(1)',
      'data:application/pdf;base64,JVBERi0xLjc=',
      `http://${HOST}/object/sign/a.pdf?token=${TOKEN}`,
      'http://localhost.evil.example/a.pdf',
      'http://127.0.0.1.evil.example/a.pdf',
      `ftp://${HOST}/a.pdf`,
      `/storage/v1/object/sign/a.pdf?token=${TOKEN}`,
      `https//${HOST}/a.pdf`,
      '',
      '   ',
      null,
      42,
    ];
    for (const url of bad) {
      const { service, downloads } = setup({ file: () => json(200, { url, mime_type: 'application/pdf', filename: 'a.pdf' }) });
      const err = await service.loadFile(ID).catch((e: unknown) => e);
      expect(err).toMatchObject({ code: 'server', message: MSG_FILE_BAD_URL });
      expectNoSecret(err);
      expect(downloads).toHaveLength(0);
    }
    for (const url of ['http://localhost:8787/files/a.pdf', 'http://127.0.0.1:8787/files/a.pdf', `https://${HOST}/a.pdf?token=${TOKEN}`]) {
      const { service, downloads } = setup({ file: () => json(200, { url, mime_type: 'application/pdf', filename: 'a.pdf' }) });
      await expect(service.loadFile(ID)).resolves.toMatchObject({ mime: 'application/pdf' });
      expect(downloads.map((d) => d.url)).toEqual([url]);
    }
    expect(isAllowedFileUrl(' https://x.example/a ')).toBe(true);
    expect(isAllowedFileUrl('HTTPS://x.example/a')).toBe(true);
    expect(isAllowedFileUrl('http://LOCALHOST:3000/a')).toBe(true);
  });

  it('/file 응답이 객체가 아니면 주소 오류', async () => {
    for (const body of [null, 'x', [], { mime_type: 'application/pdf' }]) {
      const { service, downloads } = setup({ file: () => json(200, body) });
      await expect(service.loadFile(ID)).rejects.toMatchObject({ code: 'server', message: MSG_FILE_BAD_URL });
      expect(downloads).toHaveLength(0);
    }
  });

  it('2xx 가 아니면 오류(받기 실패 문구) — Storage 404 도 분석 없음(not_found)으로 보이지 않는다', async () => {
    for (const status of [400, 403, 404, 500, 503]) {
      const { service } = setup({ download: () => json(status, { error: 'InvalidSignature', message: `bad ${TOKEN}` }) });
      const err = await service.loadFile(ID).catch((e: unknown) => e);
      expect(err).toMatchObject({ status, code: 'server', message: MSG_FILE_DOWNLOAD });
      expectNoSecret(err);
    }
  });

  it('빈 본문은 오류', async () => {
    for (const make of [() => new Response(new Uint8Array(0)), () => new Response(null), () => new Response('')]) {
      const { service } = setup({ download: make });
      const err = await service.loadFile(ID).catch((e: unknown) => e);
      expect(err).toMatchObject({ code: 'server', message: MSG_FILE_EMPTY });
      expectNoSecret(err);
    }
  });

  it('20MB(20,971,520 바이트)까지 받고, 넘으면 오류 — 본문 조각 · Content-Length 둘 다', async () => {
    const mib = new Uint8Array(MiB);
    const exact = setup({ download: () => new Response(chunked(mib, 20)) });
    const ok = await exact.service.loadFile(ID);
    expect(ok.bytes.byteLength).toBe(FILE_MAX_BYTES);
    expect(FILE_MAX_BYTES).toBe(20_971_520);

    const over = setup({ download: () => new Response(chunked(mib, 21)) });
    const err = await over.service.loadFile(ID).catch((e: unknown) => e);
    expect(err).toMatchObject({ code: 'server', message: MSG_FILE_TOO_LARGE });
    expectNoSecret(err);

    const oneMore = setup({
      download: () =>
        new Response(
          new ReadableStream<Uint8Array>({
            start(c) {
              for (let i = 0; i < 20; i++) c.enqueue(mib);
              c.enqueue(new Uint8Array(1));
              c.close();
            },
          }),
        ),
    });
    await expect(oneMore.service.loadFile(ID)).rejects.toMatchObject({ message: MSG_FILE_TOO_LARGE });

    const declared = setup({ download: () => new Response('작음', { headers: { 'Content-Length': String(FILE_MAX_BYTES + 1) } }) });
    await expect(declared.service.loadFile(ID)).rejects.toMatchObject({ code: 'server', message: MSG_FILE_TOO_LARGE });
  });

  it('연결 실패 · 시간 초과 — 바깥 오류 문구(주소가 섞일 수 있음)를 쓰지 않는다', async () => {
    const refused = setup({
      download: (url) => {
        throw new TypeError(`fetch failed: ${url}`);
      },
    });
    const err = await refused.service.loadFile(ID).catch((e: unknown) => e);
    expect(err).toMatchObject({ status: 0, code: 'network', message: MSG_FILE_DOWNLOAD });
    expectNoSecret(err);

    // 헤더 뒤 본문이 멈춤(signal 을 무시하는 fetch 에서도 끝난다)
    const stalled = setup({ fileTimeoutMs: 20, download: () => new Response(new ReadableStream<Uint8Array>({ start() {} })) });
    const late = await stalled.service.loadFile(ID).catch((e: unknown) => e);
    expect(late).toMatchObject({ status: 0, code: 'network', message: MSG_FILE_TIMEOUT });
    expectNoSecret(late);

    // 응답 자체가 오지 않음(signal 로 끊긴다)
    const hang = setup({
      fileTimeoutMs: 20,
      download: (_url, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => reject(new DOMException(`aborted ${signed(1)}`, 'AbortError')));
        }),
    });
    const never = await hang.service.loadFile(ID).catch((e: unknown) => e);
    expect(never).toMatchObject({ code: 'network', message: MSG_FILE_TIMEOUT });
    expectNoSecret(never);
  });

  it('콘솔에 아무것도 남기지 않는다(성공 · 실패 모두)', async () => {
    const spies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) => vi.spyOn(console, m).mockImplementation(() => {}));
    await setup().service.loadFile(ID);
    await setup({ download: () => json(403, {}) }).service.loadFile(ID).catch(() => {});
    await setup({ file: () => json(200, { url: 'javascript:alert(1)' }) }).service.loadFile(ID).catch(() => {});
    await setup({
      download: () => {
        throw new TypeError(signed(1));
      },
    })
      .service.loadFile(ID)
      .catch(() => {});
    for (const spy of spies) expect(spy).not.toHaveBeenCalled();
  });

  it('/file 의 401 · 404 는 백엔드 detail 그대로 전달하고 받지 않는다', async () => {
    for (const [status, code, detail] of [
      [401, 'unauthorized', '접근 코드가 맞지 않습니다.'],
      [404, 'not_found', '분석 건을 찾을 수 없습니다.'],
    ] as const) {
      const { service, downloads } = setup({ file: () => json(status, { detail }) });
      await expect(service.loadFile(ID)).rejects.toMatchObject({ status, code, message: detail });
      expect(downloads).toHaveLength(0);
    }
  });

  it('mime_type 이 비면 분석의 파일 형식, 그것도 못 받으면 파일 이름의 확장자', async () => {
    const fromAnalysis = setup({
      file: (_req, n) => json(200, { url: signed(n), mime_type: '', filename: 'scan.png' }),
      analysis: () => json(200, analysisOut({ status: 'done', documents: [documentOut({ mime_type: 'image/png', filename: 'scan.png' })] })),
    });
    await expect(fromAnalysis.service.loadFile(ID)).resolves.toMatchObject({ mime: 'image/png', filename: 'scan.png' });
    expect(fromAnalysis.order).toEqual([`backend GET /analyses/${ID}/file`, `download ${signed(1)}`, `backend GET /analyses/${ID}`]);

    const fromName = setup({
      file: (_req, n) => json(200, { url: signed(n), filename: 'scan.jpeg' }),
      analysis: () => json(500, { detail: '서버 오류' }),
    });
    await expect(fromName.service.loadFile(ID)).resolves.toMatchObject({ mime: 'image/jpeg', filename: 'scan.jpeg' });
  });
});

describe('loadFile — 오류에 서명 주소 · 토큰이 남지 않는다(V-T1-1 B-01 회귀)', () => {
  /** 검증 보고서의 재현과 같은 모양 — 서명 주소가 들어 있는 문구 */
  const sensitive = `다운로드 실패: ${signed(1)}`;
  const JWT_LIKE = ['ey' + 'JhbGciOiJub25lIn0', 'ey' + 'JzdWIiOiJ4In0', 'c2ln'].join('.');
  const SB_KEY = ['sb', 'secret', 'fixture'].join('_');

  it('/file 500 + 주소 담긴 detail → 고정 문구(받기는 하지 않음) — 다른 5xx · 4xx 도 같다', async () => {
    for (const [status, code] of [
      [500, 'server'],
      [502, 'server'],
      [503, 'server'],
      [400, 'bad_request'],
      [409, 'conflict'],
      [422, 'bad_request'],
    ] as const) {
      const { service, downloads } = setup({ file: () => json(status, { detail: sensitive }) });
      const err = await expectSafeRejection(() => service.loadFile(ID));
      expect(err).toMatchObject({ status, code, message: MSG_FILE_BAD_URL });
      expect(downloads).toHaveLength(0);
    }
  });

  it('/file 401 · 404 detail 에 주소 · 토큰 · JWT · sb_ 키가 섞이면 고정 문구', async () => {
    for (const detail of [sensitive, `토큰 ${TOKEN} 만료`, `인증 실패 ${JWT_LIKE}`, `키 ${SB_KEY}`, 'x'.repeat(30)]) {
      const unauthorized = setup({ file: () => json(401, { detail }) });
      expect(await expectSafeRejection(() => unauthorized.service.loadFile(ID))).toMatchObject({ status: 401, code: 'unauthorized', message: MSG_UNAUTHORIZED });
      const notFound = setup({ file: () => json(404, { detail }) });
      expect(await expectSafeRejection(() => notFound.service.loadFile(ID))).toMatchObject({ status: 404, code: 'not_found', message: MSG_FILE_NOT_FOUND });
      expect(unauthorized.downloads.length + notFound.downloads.length).toBe(0);
    }
  });

  it('/file 401 · 404 의 깨끗한 detail 은 그대로 보인다', async () => {
    for (const [status, code, detail] of [
      [401, 'unauthorized', '접근 코드가 맞지 않습니다.'],
      [404, 'not_found', '원본 파일을 찾을 수 없습니다.'],
      [404, 'not_found', '분석 건을 찾을 수 없습니다.'],
    ] as const) {
      const { service } = setup({ file: () => json(status, { detail }) });
      expect(await expectSafeRejection(() => service.loadFile(ID))).toMatchObject({ status, code, message: detail });
    }
  });

  it('/file 네트워크 오류(주소 담긴 TypeError) · 시간 초과 · 응답을 읽지 못함 → 고정 문구', async () => {
    const down = setup({
      file: () => {
        throw new TypeError(sensitive);
      },
    });
    expect(await expectSafeRejection(() => down.service.loadFile(ID))).toMatchObject({ status: 0, code: 'network', message: MSG_NETWORK });

    const slow = setup({ clientTimeoutMs: 20, file: () => new Promise<Response>(() => {}) });
    expect(await expectSafeRejection(() => slow.service.loadFile(ID))).toMatchObject({ status: 0, code: 'network', message: MSG_TIMEOUT });

    const garbled = setup({ file: () => new Response(`<html>${sensitive}</html>`, { status: 200 }) });
    expect(await expectSafeRejection(() => garbled.service.loadFile(ID))).toMatchObject({ code: 'server', message: MSG_FILE_BAD_URL });
    expect(down.downloads.length + slow.downloads.length + garbled.downloads.length).toBe(0);
  });

  it('받기 본문이 주소 담긴 ApiError · TypeError · 크기 초과 흉내 객체로 실패해도 고정 문구(바깥 오류를 다시 던지지 않음)', async () => {
    const failing = (error: unknown) => () =>
      new Response(
        new ReadableStream<Uint8Array>({
          start(c) {
            c.error(error);
          },
        }),
      );
    for (const error of [
      new ApiError(503, 'server', sensitive), // 검증 보고서의 두 번째 재현
      new ApiError(413, 'server', MSG_FILE_TOO_LARGE), // 크기 초과 문구를 흉내 낸 바깥 ApiError
      new TypeError(sensitive),
      { status: 413, code: 'server', message: `${MSG_FILE_TOO_LARGE} ${sensitive}` },
      sensitive,
    ]) {
      const { service } = setup({ download: failing(error) });
      const err = await expectSafeRejection(() => service.loadFile(ID));
      expect(err).toMatchObject({ status: 0, code: 'network', message: MSG_FILE_DOWNLOAD });
      expect(err).not.toBe(error);
    }
  });

  it('받기 fetch 가 주소 담긴 ApiError 로 거절하거나 응답 객체가 이상해도 고정 문구', async () => {
    const rejected = setup({
      download: () => {
        throw new ApiError(502, 'server', sensitive);
      },
    });
    expect(await expectSafeRejection(() => rejected.service.loadFile(ID))).toMatchObject({ status: 0, code: 'network', message: MSG_FILE_DOWNLOAD });

    const weird = setup({
      download: () =>
        ({
          get ok(): boolean {
            throw new ApiError(500, 'server', sensitive);
          },
        }) as unknown as Response,
    });
    expect(await expectSafeRejection(() => weird.service.loadFile(ID))).toMatchObject({ status: 0, code: 'network', message: MSG_FILE_DOWNLOAD });

    const noHeaders = setup({ download: () => ({ ok: true, status: 200 }) as unknown as Response });
    expect(await expectSafeRejection(() => noHeaders.service.loadFile(ID))).toMatchObject({ code: 'network', message: MSG_FILE_DOWNLOAD });
  });

  it('내부 크기 초과는 그대로 크기 초과 문구(표식으로 구분)', async () => {
    const { service } = setup({ download: () => new Response(chunked(new Uint8Array(MiB), 21)) });
    expect(await expectSafeRejection(() => service.loadFile(ID))).toMatchObject({ code: 'server', message: MSG_FILE_TOO_LARGE });
  });
});

describe('loadStages — 단계별 JSON', () => {
  it('GET …?include=stages(접근 코드 포함)의 result.stages', async () => {
    const { service, seen } = setup();
    await expect(service.loadStages(ID)).resolves.toEqual([{ key: '서류-인식' }, { key: '민감정보_추출' }]);
    expect(seen.map((r) => [r.method, r.url])).toEqual([['GET', `/api/py/analyses/${ID}?include=stages`]]);
    expect(seen[0].headers['x-demo-code']).toBe('code-123');
  });

  it('stages 가 없거나 배열이 아니면 null', async () => {
    for (const result of [contractResult(), null, { stages: 'x' }, { stages: null }, [], 'result']) {
      const { service } = setup({ analysis: () => json(200, analysisOut({ status: 'done', result })) });
      await expect(service.loadStages(ID)).resolves.toBeNull();
    }
    const { service } = setup({ analysis: () => json(200, null) });
    await expect(service.loadStages(ID)).resolves.toBeNull();
  });

  it('404 는 null 이 아니라 오류(백엔드 detail) — 화면이 문구를 보인다, 401 도 같다', async () => {
    for (const [status, code, detail] of [
      [404, 'not_found', '분석 건을 찾을 수 없습니다.'],
      [401, 'unauthorized', '접근 코드가 맞지 않습니다.'],
    ] as const) {
      const { service } = setup({ analysis: () => json(status, { detail }) });
      await expect(service.loadStages(ID)).rejects.toMatchObject({ status, code, message: detail });
    }
  });
});
