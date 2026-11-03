import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // cacheComponents·partialPrefetching(create-next-app 기본값)은 끈다.
  // 이번 단계는 데이터가 모두 클라이언트 데모 서비스라 끔. 실제 API 단계에서 서버 데이터를 쓰게 되면 다시 검토.
  // (켜 두면 'use client' 페이지의 React.use(params)가 Suspense 없이 빌드되지 않는다.)
  cacheComponents: false,
  partialPrefetching: false,
  // next dev 가 AI 에이전트를 감지하면 저장소 루트에 AGENTS.md 를 만든다. 작업 범위 밖 파일이 생기지 않게 끈다.
  agentRules: false,
  // 개발 화면 왼쪽 아래의 경로 표시(N)를 숨긴다 — 디자인 비교 스크린샷을 가리지 않게. 컴파일·실행 오류는 그대로 보인다.
  devIndicators: false,
  // 서비스 모드(NEXT_PUBLIC_IMASK_SERVICE)를 값이 없을 때도 빈 글자로 빌드에 넣는다. Next 는 정해진 NEXT_PUBLIC_ 값만
  // 코드에 글자로 넣으므로, 데모 빌드(값 없음)에서는 `process.env.NEXT_PUBLIC_IMASK_SERVICE === 'api'` 가 실행 중 조회로 남아
  // 실제 분석 전용 pdf.js 동적 import(src/components/detail/liveFile.ts)를 번들러가 지우지 못한다 → 데모 묶음에 pdf.js 가 생긴다.
  // 빈 글자로 정해 두면 그 분기가 빌드 때 거짓이 되어 빠진다. 값이 'api' 면 그대로 'api'(모드 판단은 src/services/mode.ts 와 같다).
  env: {
    NEXT_PUBLIC_IMASK_SERVICE: process.env.NEXT_PUBLIC_IMASK_SERVICE ?? "",
  },
  // FastAPI 백엔드(api/index.py)로 가는 길. Vercel 공식 nextjs-fastapi 템플릿과 같은 방식이다.
  // - 개발(next dev): 로컬 uvicorn(기본 127.0.0.1:8000, IMASK_API_DEV_URL 로 바꿈)으로 그대로 넘긴다.
  // - 배포: 같은 Vercel 프로젝트의 Python 함수 /api/ (= api/index.py)로 보낸다. 함수는 원래 경로(/api/py/...)를 받는다.
  // 브라우저는 늘 같은 출처의 /api/py/... 만 부르므로 CORS 설정이 필요 없다.
  async rewrites() {
    const devApi = process.env.IMASK_API_DEV_URL ?? "http://127.0.0.1:8000";
    return [
      {
        source: "/api/py/:path*",
        destination: process.env.NODE_ENV === "development" ? `${devApi}/api/py/:path*` : "/api/",
      },
    ];
  },
};

export default nextConfig;
