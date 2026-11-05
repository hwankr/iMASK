/* ==========================================================================
   파일 저장 — 브라우저 다운로드(Blob). 프로토타입 deliverFile(Main.dc.html 1426–1452)의 브라우저 경로만 옮겼다.
   (window.claude 저장 경로는 옮기지 않는다 — BRIEF 1-1)
   - 파일 내용은 받은 그대로 담는다(CSV 의 BOM 포함). 화면에서 다시 만들지 않는다.
     글자(text — CSV · JSON)와 바이너리(data — Uint8Array · Blob, 가린 PDF) 둘 다 받는다.
   - 앵커를 눌러 다운로드를 요청하고, 잠시 뒤 객체 URL 을 해제한다.
   - 브라우저는 저장 위치·완료 여부를 알려 주지 않으므로 결과는 'handed'(다운로드 요청) 또는 'failed' 다.
   ========================================================================== */

/**
 * 저장할 파일 — 글자(서비스 ExportFile 의 일부 — CSV · JSON) 또는 바이너리(Uint8Array · Blob — 가린 PDF).
 * Blob 이어도 저장할 형식은 mime 이다.
 */
export type DownloadableFile = { name: string; mime: string; text: string } | { name: string; mime: string; data: Uint8Array | Blob };

/** 파일 내용 → Blob(형식 = mime) */
function toBlob(file: DownloadableFile): Blob {
  if ('data' in file) {
    const d = file.data;
    if (d instanceof Blob) return d.type === file.mime ? d : new Blob([d], { type: file.mime });
    if (!(d instanceof Uint8Array)) throw new Error('잘못된 파일 내용');
    // 보통 ArrayBuffer 위 보기 그대로 담고, 그 밖(SharedArrayBuffer 등)이면 복사본으로 담는다
    const bytes = d.buffer instanceof ArrayBuffer ? (d as Uint8Array<ArrayBuffer>) : new Uint8Array(d);
    return new Blob([bytes], { type: file.mime });
  }
  return new Blob([file.text], { type: file.mime });
}

export type DownloadResult = { state: 'handed' } | { state: 'failed'; message: string };

/** 객체 URL 해제까지 기다리는 시간 — 다운로드가 시작되기 전에 해제되지 않게(원본 60초) */
export const REVOKE_DELAY_MS = 60000;

/** 브라우저에서 저장하지 못했을 때 (원본 문구) */
export const DOWNLOAD_FAILED_MESSAGE = '브라우저에서 파일을 저장하지 못했습니다. 다시 시도해 주세요.';

/** 바꿔 끼울 수 있는 브라우저 기능(테스트용) */
export interface DownloadEnv {
  createObjectURL: (blob: Blob) => string;
  revokeObjectURL: (url: string) => void;
  /** 다운로드 앵커를 만들어 누른다 */
  clickAnchor: (href: string, filename: string) => void;
  /** 나중에 실행 */
  later: (fn: () => void, ms: number) => void;
}

function browserEnv(): DownloadEnv {
  return {
    createObjectURL: (blob) => URL.createObjectURL(blob),
    revokeObjectURL: (url) => URL.revokeObjectURL(url),
    clickAnchor: (href, filename) => {
      const link = document.createElement('a');
      link.href = href;
      link.download = filename;
      link.rel = 'noopener';
      link.hidden = true;
      // 문서에 붙여서 누른다(일부 브라우저는 붙지 않은 앵커의 click 을 무시한다). 누른 뒤 바로 뗀다.
      document.body.appendChild(link);
      try {
        link.click();
      } finally {
        link.remove();
      }
    },
    later: (fn, ms) => {
      window.setTimeout(fn, ms);
    },
  };
}

/** 파일을 브라우저 다운로드로 저장한다. 실패해도 던지지 않고 결과로 알린다. */
export function downloadFile(file: DownloadableFile, env: DownloadEnv = browserEnv()): DownloadResult {
  let url: string | null = null;
  try {
    const blob = toBlob(file);
    url = env.createObjectURL(blob);
    env.clickAnchor(url, file.name);
    const made = url;
    env.later(() => env.revokeObjectURL(made), REVOKE_DELAY_MS);
    return { state: 'handed' };
  } catch {
    if (url) {
      try {
        env.revokeObjectURL(url);
      } catch {
        /* 해제 실패는 무시 — 결과는 이미 실패다 */
      }
    }
    return { state: 'failed', message: DOWNLOAD_FAILED_MESSAGE };
  }
}
