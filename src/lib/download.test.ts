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

const CSV = { name: 'iMASK_DG-20261030-0007_검토결과_탐지항목.csv', mime: 'text/csv;charset=utf-8', text: '﻿항목ID,정보종류\r\nF-01,이름\r\n' };

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

  it('객체 URL 을 만들지 못해도 던지지 않고 failed', () => {
    const { env } = fakeEnv({
      createObjectURL: () => {
        throw new Error('no url');
      },
    });
    expect(downloadFile(CSV, env)).toEqual({ state: 'failed', message: DOWNLOAD_FAILED_MESSAGE });
  });
});
