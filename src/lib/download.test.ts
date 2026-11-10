import { describe, expect, it } from 'vitest';
import { DOWNLOAD_FAILED_MESSAGE, REVOKE_DELAY_MS, downloadFile, type DownloadEnv } from './download';

function fakeEnv(overrides: Partial<DownloadEnv> = {}) {
  const log: string[] = [];
  const blobs: Blob[] = [];
  const timers: { fn: () => void; ms: number }[] = [];
  const env: DownloadEnv = {
    createObjectURL: (blob) => {
      blobs.push(blob);
      log.push('create');
      return 'blob:fake/' + blobs.length;
    },
    revokeObjectURL: (url) => {
      log.push('revoke ' + url);
    },
    clickAnchor: (href, filename) => {
      log.push('click ' + href + ' ' + filename);
    },
    later: (fn, ms) => {
      timers.push({ fn, ms });
    },
    ...overrides,
  };
  return { env, log, blobs, timers };
}

const CSV = { name: 'iMASK_IM-20261030-0007_검토결과_탐지항목.csv', mime: 'text/csv;charset=utf-8', text: '﻿항목ID,정보종류\r\nF-01,이름\r\n' };

describe('downloadFile — 브라우저 다운로드', () => {
  it('Blob 을 만들어 앵커를 누르고 handed 를 돌려준다', () => {
    const { env, log } = fakeEnv();
    expect(downloadFile(CSV, env)).toEqual({ state: 'handed' });
    expect(log).toEqual(['create', 'click blob:fake/1 ' + CSV.name]);
  });

  it('파일 내용을 그대로(BOM 포함) 담고 MIME 을 붙인다', async () => {
    const { env, blobs } = fakeEnv();
    downloadFile(CSV, env);
    expect(blobs).toHaveLength(1);
    expect(blobs[0].type).toBe('text/csv;charset=utf-8');
    const bytes = new Uint8Array(await blobs[0].arrayBuffer());
    expect(Array.from(bytes.slice(0, 3))).toEqual([0xef, 0xbb, 0xbf]);
    // Blob.text() 는 UTF-8 BOM 을 떼고 읽으므로 바이트로 비교한다
    expect(Array.from(bytes)).toEqual(Array.from(new TextEncoder().encode(CSV.text)));
  });

  it('객체 URL 은 바로 해제하지 않고 잠시 뒤 해제한다', () => {
    const { env, log, timers } = fakeEnv();
    downloadFile(CSV, env);
    expect(log.some((l) => l.startsWith('revoke'))).toBe(false);
    expect(timers).toHaveLength(1);
    expect(timers[0].ms).toBe(REVOKE_DELAY_MS);
    timers[0].fn();
    expect(log[log.length - 1]).toBe('revoke blob:fake/1');
  });

  it('앵커를 누르다 실패하면 failed 와 원본 문구, URL 은 바로 해제한다', () => {
    const { env, log, timers } = fakeEnv({
      clickAnchor: () => {
        throw new Error('blocked');
      },
    });
    expect(downloadFile(CSV, env)).toEqual({ state: 'failed', message: DOWNLOAD_FAILED_MESSAGE });
    expect(log).toEqual(['create', 'revoke blob:fake/1']);
    expect(timers).toHaveLength(0);
  });

  it('바이너리(Uint8Array) — 바이트 그대로 담고 mime 을 붙인다', async () => {
    const { env, blobs, log } = fakeEnv();
    const data = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d, 0x00, 0xff, 0x80]);
    const PDF = { name: 'iMASK_IM-20261105-0001_마스킹.pdf', mime: 'application/pdf', data };
    expect(downloadFile(PDF, env)).toEqual({ state: 'handed' });
    expect(log).toEqual(['create', 'click blob:fake/1 ' + PDF.name]);
    expect(blobs[0].type).toBe('application/pdf');
    expect(Array.from(new Uint8Array(await blobs[0].arrayBuffer()))).toEqual(Array.from(data));
  });

  it('바이너리(일부만 보는 Uint8Array) — 보는 범위의 바이트만 담는다', async () => {
    const { env, blobs } = fakeEnv();
    const whole = new Uint8Array([1, 2, 3, 4, 5, 6]);
    downloadFile({ name: 'a.pdf', mime: 'application/pdf', data: whole.subarray(2, 5) }, env);
    expect(Array.from(new Uint8Array(await blobs[0].arrayBuffer()))).toEqual([3, 4, 5]);
  });

  it('바이너리(Blob) — 형식이 같으면 그대로, 다르면 mime 으로 다시 담는다', async () => {
    const same = new Blob([new Uint8Array([7, 8])], { type: 'application/pdf' });
    const a = fakeEnv();
    downloadFile({ name: 'a.pdf', mime: 'application/pdf', data: same }, a.env);
    expect(a.blobs[0]).toBe(same);
    const other = new Blob([new Uint8Array([9])]);
    const b = fakeEnv();
    downloadFile({ name: 'b.pdf', mime: 'application/pdf', data: other }, b.env);
    expect(b.blobs[0].type).toBe('application/pdf');
    expect(Array.from(new Uint8Array(await b.blobs[0].arrayBuffer()))).toEqual([9]);
  });

  it('바이너리 — 앵커를 누르다 실패하면 failed 와 원본 문구, URL 은 바로 해제', () => {
    const { env, log, timers } = fakeEnv({
      clickAnchor: () => {
        throw new Error('blocked');
      },
    });
    expect(downloadFile({ name: 'a.pdf', mime: 'application/pdf', data: new Uint8Array([1]) }, env)).toEqual({ state: 'failed', message: DOWNLOAD_FAILED_MESSAGE });
    expect(log).toEqual(['create', 'revoke blob:fake/1']);
    expect(timers).toHaveLength(0);
  });

  it('바이너리 — 내용이 Uint8Array · Blob 이 아니면 던지지 않고 failed', () => {
    const { env, log } = fakeEnv();
    const bad = { name: 'a.pdf', mime: 'application/pdf', data: [1, 2, 3] as unknown as Uint8Array };
    expect(downloadFile(bad, env)).toEqual({ state: 'failed', message: DOWNLOAD_FAILED_MESSAGE });
    expect(log).toEqual([]);
  });

  it('객체 URL 을 만들지 못해도 던지지 않고 failed', () => {
    const { env } = fakeEnv({
      createObjectURL: () => {
        throw new Error('no url');
      },
    });
    expect(downloadFile(CSV, env)).toEqual({ state: 'failed', message: DOWNLOAD_FAILED_MESSAGE });
  });
});
