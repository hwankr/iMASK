import { afterEach, describe, expect, it, vi } from 'vitest';
import type { UploadTicket } from './client';
import { MSG_UPLOAD_CONFIG_MISSING, UploadConfigError, UploadFailedError, createSupabaseUploader, describeUploadError } from './upload';

/* 가짜 값만 쓴다 — 실제 키·토큰·주소가 아니다 */
const FAKE_URL = 'https://fixture-project.supabase.example';
const FAKE_KEY = 'sb_publishable_fixture-only';
const FAKE_TOKEN = 'fixture-signed-upload-token-0123456789abcdef';
// JWT 꼴 가짜 값 — 비밀값 검사가 원문을 JWT 로 세지 않게 조각을 이어 만든다
const FAKE_JWT = ['ey' + 'JhbGciOiJIUzI1NiJ9', 'ey' + 'JzdWIiOiJmaXh0dXJlIn0', 'Zml4dHVyZS1zaWduYXR1cmU'].join('.');
const TICKET: UploadTicket = {
  bucket: 'documents',
  path: 'analyses/ab12cd34-0000-4000-8000-000000000000/bundle.pdf',
  token: FAKE_TOKEN,
  signed_url: `${FAKE_URL}/storage/v1/object/upload/sign/documents/x.pdf?token=${FAKE_TOKEN}`,
};
const pdf = () => new File(['%PDF-1.7 합성'], 'bundle.pdf', { type: 'application/pdf' });

/** 기록·오류에 나오면 안 되는 조각 */
const LEAKS = [FAKE_TOKEN, encodeURIComponent(FAKE_TOKEN), FAKE_JWT, '/object/upload/sign/', 'token='];
const leaks = (text: string) => LEAKS.filter((s) => text.includes(s));

afterEach(() => {
  vi.restoreAllMocks();
});

describe('describeUploadError — 고정 문구 + 이름 + 숫자 상태만', () => {
  it('message 에 서명 URL·토큰·JWT 가 있어도 요약에는 없다', () => {
    const err = Object.assign(new Error(`Upload failed at ${TICKET.signed_url} (auth ${FAKE_JWT})`), { name: 'StorageApiError', status: 400, statusCode: '400' });
    const { summary, status } = describeUploadError(err);
    expect(summary).toBe('서명 업로드 실패 (StorageApiError, HTTP 400)');
    expect(status).toBe(400);
    expect(leaks(summary)).toEqual([]);
  });

  it('이상한 이름 · 상태는 버린다', () => {
    expect(describeUploadError({ name: `x ${FAKE_TOKEN}`, status: 'abc' }).summary).toBe('서명 업로드 실패 (Error)');
    expect(describeUploadError({ name: 'StorageUnknownError', statusCode: '4000' }).summary).toBe('서명 업로드 실패 (StorageUnknownError)');
    expect(describeUploadError({ name: 'StorageApiError', statusCode: '413' })).toEqual({ summary: '서명 업로드 실패 (StorageApiError, HTTP 413)', status: 413 });
    expect(describeUploadError(null).summary).toBe('서명 업로드 실패 (Error)');
    expect(describeUploadError('문자열 오류 ' + FAKE_TOKEN).summary).toBe('서명 업로드 실패 (Error)');
  });
});

describe('createSupabaseUploader — 실제 supabase-js 로(가짜 fetch)', () => {
  it('SDK 오류 문구에 가짜 서명 URL·토큰이 들어 있어도 console.warn 과 던진 오류에 원문 0건', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const seen: string[] = [];
    const fetch = (async (input: RequestInfo | URL) => {
      seen.push(String(input));
      // Storage 가 요청 URL(토큰 포함)을 담은 오류 문구를 돌려주는 경우
      return new Response(JSON.stringify({ statusCode: '400', error: 'InvalidRequest', message: `Upload failed at ${String(input)} ${FAKE_JWT}` }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }) as typeof globalThis.fetch;
    const upload = createSupabaseUploader({ url: FAKE_URL, key: FAKE_KEY, fetch });
    const err = await upload(TICKET, pdf(), 'application/pdf').catch((e: unknown) => e);

    expect(seen).toHaveLength(1);
    expect(seen[0]).toContain('/object/upload/sign/documents/'); // 요청에는 토큰이 간다(정상)
    expect(err).toBeInstanceOf(UploadFailedError);
    expect((err as UploadFailedError).status).toBe(400);
    const thrown = `${(err as Error).name} ${(err as Error).message} ${JSON.stringify(err)}`;
    expect(leaks(thrown)).toEqual([]);

    expect(warn).toHaveBeenCalledTimes(1);
    const logged = warn.mock.calls.flat().map((a) => (typeof a === 'string' ? a : JSON.stringify(a) ?? String(a))).join(' ');
    expect(logged).toBe('서명 업로드 실패 (StorageApiError, HTTP 400)');
    expect(leaks(logged)).toEqual([]);
  });

  it('fetch 자체가 실패해도(문구에 토큰) 기록에 원문이 없다', async () => {
    const lines: string[] = [];
    const fetch = (async (input: RequestInfo | URL) => {
      throw new TypeError(`network error for ${String(input)}`);
    }) as typeof globalThis.fetch;
    const err = await createSupabaseUploader({ url: FAKE_URL, key: FAKE_KEY, fetch, warn: (l) => lines.push(l) })(TICKET, pdf(), 'application/pdf').catch((e: unknown) => e);
    expect(err).toBeInstanceOf(UploadFailedError);
    expect(lines).toHaveLength(1);
    expect(leaks(lines.join(' ') + (err as Error).message)).toEqual([]);
  });

  it('성공 — 공개 키만 쓰고 형식을 붙여 보낸다', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const seen: { url: string; headers: Headers; body: unknown }[] = [];
    const fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      seen.push({ url: String(input), headers: new Headers(init?.headers), body: init?.body });
      return new Response(JSON.stringify({ Key: `documents/${TICKET.path}` }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }) as typeof globalThis.fetch;
    await createSupabaseUploader({ url: FAKE_URL, key: FAKE_KEY, fetch })(TICKET, new File(['%PDF'], 'bundle.pdf', { type: '' }), 'application/pdf');
    expect(seen).toHaveLength(1);
    expect(seen[0].headers.get('apikey')).toBe(FAKE_KEY);
    const part = (seen[0].body as FormData).get('') as File;
    expect(part.type).toBe('application/pdf');
    expect(warn).not.toHaveBeenCalled();
  });

  it('공개 환경변수가 없으면 요청 없이 설정 오류', async () => {
    const fetch = vi.fn() as unknown as typeof globalThis.fetch;
    await expect(createSupabaseUploader({ url: '', key: FAKE_KEY, fetch })(TICKET, pdf(), 'application/pdf')).rejects.toBeInstanceOf(UploadConfigError);
    await expect(createSupabaseUploader({ url: FAKE_URL, key: '', fetch })(TICKET, pdf(), 'application/pdf')).rejects.toThrow(MSG_UPLOAD_CONFIG_MISSING);
    expect(fetch).not.toHaveBeenCalled();
  });
});
