/* 실제 분석 서비스의 내보내기 — buildExport(조회 하나 → 거절 조건 → 안전한 사본 → 공용 모듈) · logExport(log_export 본문을
   검토 동작과 같은 보내기로). 가짜 백엔드(fakeFetch)로 요청 수 · 본문 · 알림 · 오류를 확인한다. 원문 값은 출력에 옮기지 않는다. */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CONFIG } from '@/config/app';
import type { AnalysisService } from '../analysis-service';
import type { ExportFile } from '../types';
import { ApiError, createApiClient, isApiError } from './client';
import { MSG_NO_REPORT, createApiService } from './service';
import { analysisOut, contractResult, fakeFetch, json, type SeenRequest } from './testing';

const ID = 'ab12cd34-0000-4000-8000-000000000000';
const GET_URL = `/api/py/analyses/${ID}`;
const ACTION_URL = `/api/py/analyses/${ID}/review-actions`;
const NEW_REVIEW = { status: 'needed', memo: '', memo_at: null, reviewer: '', reviewed_at: null, completion_note: '', findings: {}, history: [], version: 1 };

const doneOut = (review: unknown = NEW_REVIEW) => analysisOut({ status: 'done', result: contractResult(), review: structuredClone(review) });

function setup(opts: { get?: () => Response | Promise<Response>; post?: (req: SeenRequest) => Response | Promise<Response> } = {}) {
  const { fetch, seen } = fakeFetch((req) => {
    if (req.method === 'POST' && req.url === ACTION_URL) return opts.post ? opts.post(req) : json(200, { analysis: doneOut(), changed: true });
    if (req.method === 'GET' && req.url === GET_URL) return opts.get ? opts.get() : json(200, doneOut());
    return json(404, { detail: '분석 건을 찾을 수 없습니다.' });
  });
  const service: AnalysisService = createApiService({ client: createApiClient({ fetch }), upload: async () => {} });
  const notified = vi.fn();
  service.subscribe(notified);
  return { service, seen, notified, gets: () => seen.filter((r) => r.method === 'GET'), posts: () => seen.filter((r) => r.method === 'POST') };
}

afterEach(() => {
  vi.useRealTimers();
});

/** 원래 응답의 대상 원문 값(masked 와 다르고 2자 이상) */
function rawValues(): string[] {
  const findings = (contractResult().findings as Record<string, unknown>[]) ?? [];
  return findings
    .map((f) => [String(f.value ?? ''), String(f.masked ?? '')])
    .filter(([v, m]) => v && Array.from(v).length >= 2 && v !== m)
    .map(([v]) => v);
}

describe('buildExport — 거절 조건', () => {
  it('없는 분석(404) → ApiError(not_found), 조회 하나 · 쓰기 없음 · 알림 한 번(화면이 목록으로)', async () => {
    const { service, gets, posts, notified } = setup({ get: () => json(404, { detail: '분석 건을 찾을 수 없습니다.' }) });
    const err = await service.buildExport(ID, 'csv').catch((e: unknown) => e);
    expect(isApiError(err) && err.code).toBe('not_found');
    expect(gets()).toHaveLength(1);
    expect(posts()).toHaveLength(0);
    expect(notified).toHaveBeenCalledTimes(1);
  });

  const notTargets: [string, () => unknown][] = [
    ['대기', () => analysisOut({ status: 'queued' })],
    ['분석 중', () => analysisOut({ status: 'running', upstage_job_id: 'job_x' })],
    ['실패', () => analysisOut({ status: 'failed', error: '실패', review: NEW_REVIEW })],
    ['일부 실패', () => analysisOut({ status: 'partial', error: '일부', result: contractResult(), review: NEW_REVIEW })],
    ['옛 형식 완료', () => analysisOut({ status: 'done', result: { format: 'imask-upstage-v1', summary: { risk_level: '상' } }, review: NEW_REVIEW })],
    ['검토 기록 null(reviewable false)', () => analysisOut({ status: 'done', result: contractResult(), review: null })],
  ];
  for (const [name, body] of notTargets) {
    it(`${name} → MSG_NO_REPORT 로 거절(조회 하나 · 쓰기 · 알림 없음)`, async () => {
      const { service, gets, posts, notified } = setup({ get: () => json(200, body()) });
      await expect(service.buildExport(ID, 'json')).rejects.toThrow(MSG_NO_REPORT);
      expect(gets()).toHaveLength(1);
      expect(posts()).toHaveLength(0);
      expect(notified).not.toHaveBeenCalled();
    });
  }

  it('조회가 500 이면 그 오류로 거절', async () => {
    const { service } = setup({ get: () => json(500, { detail: '서버 오류' }) });
    const err = await service.buildExport(ID, 'csv').catch((e: unknown) => e);
    expect(isApiError(err) && err.code).toBe('server');
  });
});

describe('buildExport — 보고서 대상', () => {
  it('CSV · JSON 파일 — 브랜드 인자 무시(iMASK_<code>_…), 원문 값 없음, 데모데이터 false, 생성 시각 서울', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-11-04T15:00:30Z')); // 서울 2026-11-05 00:00
    const { service, gets, posts } = setup();
    const csv = await service.buildExport(ID, 'csv', '다른브랜드');
    expect(csv.name).toBe('iMASK_DG-20261102-AB12_검토결과_탐지항목.csv');
    expect(csv.name.startsWith(CONFIG.brandName + '_')).toBe(true);
    const jsonFile = await service.buildExport(ID, 'json', '다른브랜드');
    expect(jsonFile.name).toBe('iMASK_DG-20261102-AB12_검토결과.json');
    const obj = JSON.parse(jsonFile.text);
    expect(obj.보고서).toMatchObject({ 서비스: 'iMASK', 생성시각: '2026.11.05 00:00', 데모데이터: false });
    expect(obj.검토사항).toEqual([]); // 옛 결과(items 없음) — 검토사항 0개, 키는 데모 자리
    expect(Object.keys(obj)).not.toContain('문서간연결');
    const raws = rawValues();
    expect(raws.length).toBeGreaterThan(0);
    for (const f of [csv, jsonFile]) {
      expect(raws.filter((v) => f.text.includes(v)).length, f.format).toBe(0);
      expect(f.size).toBe(new TextEncoder().encode(f.text).length);
    }
    expect(gets()).toHaveLength(2);
    expect(posts()).toHaveLength(0);
  });

  it('요청은 조회 하나 — 진행 중 조회(get)를 나눠 쓴다', async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => {
      release = r;
    });
    const { service, gets } = setup({
      get: async () => {
        await gate;
        return json(200, doneOut());
      },
    });
    const viewing = service.get(ID);
    const file = service.buildExport(ID, 'csv');
    release();
    expect(await viewing).not.toBeNull();
    expect((await file).format).toBe('csv');
    expect(gets()).toHaveLength(1);
  });

  it('검토 완료로 잠긴 분석도 파일을 만든다', async () => {
    const { service } = setup({ get: () => json(200, doneOut({ ...NEW_REVIEW, status: 'done', reviewer: '이지은', reviewed_at: '2026-11-04T01:00:00+00:00' })) });
    const f = await service.buildExport(ID, 'json');
    expect(JSON.parse(f.text).분석.검토상태).toBe('검토 완료');
  });
});

describe('buildExport — 아주 긴 원문 값(V-T2-1 V1 회귀)', () => {
  const big = (seed: number, len: number) => {
    const out: string[] = [];
    for (let i = 0; i < len; i++) out.push(String.fromCodePoint(0xac00 + ((i * 7 + seed) % 11172)));
    return out.join('');
  };

  for (const len of [65536, 262144]) {
    it(`${len} 코드 포인트 값 — CSV · JSON 이 만들어지고, 파일 · 콘솔 어디에도 원문 값이 없다`, async () => {
      const value = big(len, len);
      const out = doneOut();
      const result = out.result as Record<string, unknown>;
      const findings = result.findings as Record<string, unknown>[];
      findings[0].value = value;
      findings[0].masked = '***';
      findings[3].risk_reason = '판단 ' + value;
      (result.overall as Record<string, unknown>).text = '- 사유 ' + value;
      const printed: string[] = [];
      const spies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) =>
        vi.spyOn(console, m).mockImplementation((...args: unknown[]) => void printed.push(args.map(String).join(' '))),
      );
      try {
        const { service } = setup({ get: () => json(200, out) });
        for (const format of ['csv', 'json'] as const) {
          const file = await service.buildExport(ID, format);
          expect(file.text.includes(value.slice(2000, 2064)), format).toBe(false);
          expect(file.size).toBe(new TextEncoder().encode(file.text).length);
        }
      } finally {
        spies.forEach((s) => s.mockRestore());
      }
      expect(printed.filter((p) => p.includes(value.slice(2000, 2064)))).toHaveLength(0);
    });
  }
});

describe('logExport — log_export 본문 · 알림 · 오류', () => {
  const FILE: ExportFile = { format: 'csv', name: 'iMASK_DG-20261102-AB12_검토결과_탐지항목.csv', mime: 'text/csv;charset=utf-8', text: 'x', size: 6127, preview: '' };

  it('본문은 정확히 6키 — type · actor · format · size · state · file_name, 보내기 전 조회 없음 · 성공하면 알림 한 번', async () => {
    const { service, seen, gets, posts, notified } = setup();
    await service.logExport(ID, FILE, 'handed');
    expect(gets()).toHaveLength(0);
    expect(posts()).toHaveLength(1);
    expect(seen[0].url).toBe(ACTION_URL);
    const body = posts()[0].body as Record<string, unknown>;
    expect(Object.keys(body).sort()).toEqual(['actor', 'file_name', 'format', 'size', 'state', 'type']);
    expect(body).toEqual({ type: 'log_export', actor: CONFIG.user.name, format: 'csv', size: 6127, state: 'handed', file_name: FILE.name });
    expect(notified).toHaveBeenCalledTimes(1);
    await service.logExport(ID, { ...FILE, format: 'json', name: 'iMASK_DG-20261102-AB12_검토결과.json', size: 22021 }, 'saved');
    expect(posts()[1].body).toEqual({ type: 'log_export', actor: CONFIG.user.name, format: 'json', size: 22021, state: 'saved', file_name: 'iMASK_DG-20261102-AB12_검토결과.json' });
    expect(notified).toHaveBeenCalledTimes(2);
  });

  for (const [status, code] of [
    [409, 'conflict'],
    [404, 'not_found'],
  ] as const) {
    it(`${status} → 알림 한 번 + 그 오류(${code})로 거절`, async () => {
      const { service, notified } = setup({ post: () => json(status, { detail: '검토할 수 없는 분석입니다.' }) });
      const err = await service.logExport(ID, FILE, 'handed').catch((e: unknown) => e);
      expect(err).toBeInstanceOf(ApiError);
      expect(isApiError(err) && err.code).toBe(code);
      expect(notified).toHaveBeenCalledTimes(1);
    });
  }

  it('500 · 네트워크 → 알림 없이 그 오류로 거절', async () => {
    const s500 = setup({ post: () => json(500, { detail: '서버 오류' }) });
    const e500 = await s500.service.logExport(ID, FILE, 'handed').catch((e: unknown) => e);
    expect(isApiError(e500) && e500.code).toBe('server');
    expect(s500.notified).not.toHaveBeenCalled();
    const net = setup({
      post: () => {
        throw new TypeError('fetch failed');
      },
    });
    const eNet = await net.service.logExport(ID, FILE, 'handed').catch((e: unknown) => e);
    expect(isApiError(eNet) && eNet.code).toBe('network');
    expect(net.notified).not.toHaveBeenCalled();
  });

  it('성공 뒤 그 분석의 진행 중 조회를 떼어 새 조회가 저장 뒤 값을 받는다', async () => {
    let n = 0;
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => {
      release = r;
    });
    const { service, gets } = setup({
      get: async () => {
        n += 1;
        if (n === 1) await gate;
        return json(200, doneOut({ ...NEW_REVIEW, history: n === 1 ? [] : [{ id: 'H2', at: '2026-11-04T02:00:00+00:00', actor: '이지은', kind: 'export', target: FILE.name, change: 'CSV · 6KB · 다운로드 요청', reason: '민감한 값 마스킹' }] }));
      },
    });
    const old = service.get(ID);
    await service.logExport(ID, FILE, 'handed');
    const fresh = await service.get(ID);
    release();
    await old;
    expect(gets()).toHaveLength(2);
    expect(fresh?.history.map((h) => h.kind)).toEqual(['export']);
  });
});
