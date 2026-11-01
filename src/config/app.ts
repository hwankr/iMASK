/* ==========================================================================
   ① 설정값 — 브랜드명·강조색·업로드 제한은 여기서만 바꾼다.
   프로토타입 CONFIG(Main.dc.html 772줄) + Tweaks 의 강조색 기본값.
   - accent 는 <html style="--accent: …"> 로 들어가고, 파생 색은 tokens.css 가 만든다.
   - 사용자 정보·데모 지연 시간도 이 파일에만 둔다.
   ========================================================================== */

export interface AppConfig {
  /** 화면·내보내기 파일에 쓰는 서비스 이름 */
  readonly brandName: string;
  /** 강조색(16진수). tokens.css 의 --accent 기본값과 같게 둔다. */
  readonly accent: string;
  /** 로그인 전 단계의 담당자 정보(데모) */
  readonly user: { readonly name: string; readonly team: string };
  /** 업로드 제한 — 파일 개수, 파일당 MB, 허용 확장자(소문자) */
  readonly upload: {
    readonly maxFiles: number;
    readonly maxFileMB: number;
    readonly accept: readonly string[];
  };
  /** 데모 서비스 지연 시간(밀리초) */
  readonly sim: {
    /** 분석 요청 응답까지 */
    readonly requestMs: number;
    /** 대기 → 분석 시작까지 */
    readonly startMs: number;
    /** 문서 1개 분석 시간 */
    readonly docMs: number;
    /** 다시 분석 응답까지 */
    readonly retryMs: number;
    /** 파일 1개 업로드(선택 후 준비 완료)까지 */
    readonly uploadMs: number;
  };
}

export const CONFIG = {
  brandName: '문서가드',
  accent: '#00845C',
  user: { name: '이지은', team: '여신관리팀' },
  upload: { maxFiles: 10, maxFileMB: 20, accept: ['pdf', 'png', 'jpg', 'jpeg'] },
  sim: { requestMs: 1300, startMs: 800, docMs: 1900, retryMs: 2400, uploadMs: 700 },
} as const satisfies AppConfig;

export type Config = typeof CONFIG;
/** 업로드 허용 확장자 */
export type AcceptExt = (typeof CONFIG.upload.accept)[number];
