/* ==========================================================================
   서명 업로드 — 브라우저가 Supabase Storage 에 파일을 직접 올린다(Vercel 요청 본문 4.5MB 제한 때문).
   - @supabase/supabase-js 의 storage.from(bucket).uploadToSignedUrl(path, token, file).
     서명 토큰이 권한이고, 공개 키(publishable key)는 Supabase 게이트웨이를 지나기 위한 값이다.
   - supabase-js 는 실제로 올릴 때만 동적 import 로 불러온다(데모 모드·첫 화면 묶음에 넣지 않는다).
   - 공개 환경변수 둘은 process.env.NEXT_PUBLIC_… 를 글자 그대로 참조한다(빌드 때 값이 들어간다).
   - File 을 넘기면 supabase-js 가 multipart 로 보내고 그 칸의 형식은 File.type 이다(contentType 옵션은
     Blob 에는 쓰이지 않음). 브라우저가 형식을 비워 두면 버킷의 허용 형식에 걸리므로, 형식이 다르면
     같은 내용으로 형식을 붙인 File 을 새로 만든다.
   - **서명 URL·토큰은 기록하지 않는다.** SDK 오류(StorageApiError)의 message 는 바깥 응답 문구를 그대로
     담아 서명 URL·토큰이 섞일 수 있으므로, 기록에도 던지는 오류에도 message 를 쓰지 않는다 —
     고정 문구 + 오류 이름(영문자만) + 숫자 HTTP 상태만 남긴다(describeUploadError).
   ========================================================================== */

import type { UploadTicket } from './client';

/** 서명 업로드 함수 — 실패하면 던진다 */
export type Uploader = (ticket: UploadTicket, file: File, contentType: string) => Promise<void>;

export const MSG_UPLOAD_CONFIG_MISSING = '업로드 설정(NEXT_PUBLIC_SUPABASE_URL·NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY)이 없습니다.';

/** 업로드 설정이 없을 때의 오류 — 서비스가 문구를 그대로 화면에 넘긴다 */
export class UploadConfigError extends Error {
  constructor() {
    super(MSG_UPLOAD_CONFIG_MISSING);
    this.name = 'UploadConfigError';
  }
}

/** 업로드 실패 — SDK 오류의 문구는 버리고 이름·숫자 상태만 담는다 */
export class UploadFailedError extends Error {
  /** HTTP 상태(모르면 null) */
  readonly status: number | null;
  constructor(summary: string, status: number | null) {
    super(summary);
    this.name = 'UploadFailedError';
    this.status = status;
  }
}

/** 오류 이름 — 영문자·숫자만, 40자까지. 그 밖이면 'Error' */
function safeName(error: unknown): string {
  const name = error && typeof error === 'object' ? (error as { name?: unknown }).name : undefined;
  return typeof name === 'string' && /^[A-Za-z][A-Za-z0-9]{0,39}$/.test(name) ? name : 'Error';
}

/** HTTP 상태 — 100~599 정수만(StorageApiError.status 는 숫자, statusCode 는 문자열) */
function safeStatus(error: unknown): number | null {
  if (!error || typeof error !== 'object') return null;
  for (const key of ['status', 'statusCode'] as const) {
    const raw = (error as Record<string, unknown>)[key];
    const n = typeof raw === 'number' ? raw : typeof raw === 'string' && /^\d{3}$/.test(raw) ? Number(raw) : NaN;
    if (Number.isInteger(n) && n >= 100 && n <= 599) return n;
  }
  return null;
}

/**
 * 업로드 오류를 기록해도 되는 한 줄로 — 고정 문구 + 이름 + 숫자 상태. message 는 읽지 않는다
 * (바깥 응답 문구에 서명 URL·토큰이 섞일 수 있다).
 */
export function describeUploadError(error: unknown): { summary: string; status: number | null } {
  const status = safeStatus(error);
  return { summary: `서명 업로드 실패 (${safeName(error)}${status === null ? '' : `, HTTP ${status}`})`, status };
}

/** 형식이 맞는 File(같으면 그대로) */
export function withContentType(file: File, contentType: string): File {
  if (file.type === contentType) return file;
  return new File([file], file.name, { type: contentType, lastModified: file.lastModified });
}

export interface SupabaseUploaderOptions {
  /** 기본: NEXT_PUBLIC_SUPABASE_URL */
  url?: string;
  /** 기본: NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY */
  key?: string;
  /** supabase-js 가 쓸 fetch(테스트용). 기본은 전역 fetch */
  fetch?: typeof fetch;
  /** 실패 기록(기본 console.warn) — 받는 글자는 describeUploadError 의 요약뿐이다 */
  warn?: (line: string) => void;
}

/** supabase-js 로 서명 업로드하는 함수를 만든다 */
export function createSupabaseUploader(options: SupabaseUploaderOptions = {}): Uploader {
  return async (ticket, file, contentType) => {
    const url = options.url ?? process.env.NEXT_PUBLIC_SUPABASE_URL;
    const key = options.key ?? process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
    if (!url || !key) throw new UploadConfigError();
    const warn = options.warn ?? ((line: string) => console.warn(line));
    let error: unknown = null;
    try {
      const { createClient } = await import('@supabase/supabase-js');
      // 로그인을 쓰지 않는다 — 세션을 저장하거나 새로 고치지 않게 끈다
      const client = createClient(url, key, {
        auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
        ...(options.fetch ? { global: { fetch: options.fetch } } : {}),
      });
      ({ error } = await client.storage
        .from(ticket.bucket)
        .uploadToSignedUrl(ticket.path, ticket.token, withContentType(file, contentType), { contentType }));
    } catch (thrown) {
      error = thrown ?? new Error('upload');
    }
    if (error) {
      const { summary, status } = describeUploadError(error);
      warn(summary);
      throw new UploadFailedError(summary, status);
    }
  };
}

/** 기본 업로더 — 공개 환경변수와 전역 fetch */
export const uploadWithSupabase: Uploader = createSupabaseUploader();
