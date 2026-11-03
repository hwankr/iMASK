/* 실제 분석 서비스 — 바깥에는 서비스 만들기 · 판별 · 오류 판별만 내보낸다(클라이언트·매핑은 안에서만 쓴다). */

export { createApiService, isApiService, type ApiService, type ApiServiceDeps } from './service';
export { ApiError, apiErrorAnalysisId, apiErrorCode, isApiError, type ApiErrorCode } from './client';
