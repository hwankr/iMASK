/* ==========================================================================
   내보내기 모달 상태와 화면 값 — 프로토타입 freshExp(1456) · modalVM 'export'(2505–2518) · doExport(1904–1916)
   ========================================================================== */

import { CONFIG } from '@/config/app';
import { EXPORT_FORMATS, LIVE_EXPORT_JSON_DESC, type ExportFormat } from '@/display/rules';
import { fmtDT, fmtSize } from '@/lib/format';
import type { ExportFile } from '@/services/types';

/**
 * 내보내기 진행 상태
 * - idle 아직 만들지 않음 · working 만드는 중 · saved 저장 완료 · handed 다운로드 요청(브라우저에 넘김)
 * - declined 저장 취소 · failed 실패
 * 브라우저 다운로드(Blob)는 handed 또는 failed 만 낸다. saved·declined 는 저장 위치를 알려 주는 저장 기능
 * (프로토타입 window.claude 경로)용 표시로, /dev/states 의 report-saved 에서 보인다.
 */
export type ExportPhase = 'idle' | 'working' | 'saved' | 'handed' | 'declined' | 'failed';

/** 내보내기 모달 상태 (원본 state.exp) */
export interface ExportUiState {
  format: ExportFormat;
  state: ExportPhase;
  /** 만든 파일(서비스 buildExport 결과 그대로) */
  file: ExportFile | null;
  /** 실패 이유(비면 기본 문구) */
  msg: string;
  /** 끝난 시각 'YYYY-MM-DD HH:mm'(없으면 빈 글자) */
  at: string;
}

/** 새 내보내기 상태 — 형식만 이어 받는다 (원본 freshExp) */
export function freshExport(format: ExportFormat = 'csv'): ExportUiState {
  return { format, state: 'idle', file: null, msg: '', at: '' };
}

/** buildExport 가 실패했을 때 (원본 doExport) */
export const BUILD_FAILED_MESSAGE = '파일 내용을 만들지 못했습니다. 다시 시도해 주세요.';
/** 실패 이유가 비었을 때 (원본 modalVM) */
export const DEFAULT_FAILED_MESSAGE = '파일을 저장하지 못했습니다. 다시 시도하거나 다른 형식을 선택하세요.';

/**
 * 아직 파일을 만들기 전에 보여 줄 파일 이름 — 원본 modalVM 의 fileName 계산 그대로.
 * 파일을 만든 뒤에는 서비스가 준 이름(file.name)을 쓴다.
 */
export function expectedExportName(code: string, format: ExportFormat, brand: string = CONFIG.brandName): string {
  return brand + '_' + code + '_검토결과' + (format === 'csv' ? '_탐지항목.csv' : '.json');
}

/** 형식 선택지 — 라벨·설명은 ② EXPORT_FORMATS */
export const FORMAT_OPTIONS = EXPORT_FORMATS.map((fm) => ({ value: fm.key, label: fm.label, description: fm.desc }));

/** 실제 분석의 형식 선택지 — JSON 설명만 ② LIVE_EXPORT_JSON_DESC(실제 분석 파일에는 문서 간 연결이 없다) */
export const LIVE_FORMAT_OPTIONS = FORMAT_OPTIONS.map((o) => (o.value === 'json' ? { ...o, description: LIVE_EXPORT_JSON_DESC } : o));

export interface ExportView {
  busy: boolean;
  fileName: string;
  /** '파일 이름 · 크기 · 시각' (파일이 없으면 빈 글자) */
  doneText: string;
  failedText: string;
  /** 바닥 주요 버튼 글자 */
  primaryLabel: string;
  preview: string;
}

/** 모달 화면 값 (원본 modalVM 'export') */
export function exportView(e: ExportUiState, code: string): ExportView {
  const busy = e.state === 'working';
  const done = !!e.file && (e.state === 'saved' || e.state === 'handed');
  return {
    busy,
    fileName: e.file ? e.file.name : expectedExportName(code, e.format),
    doneText: e.file ? e.file.name + ' · ' + fmtSize(e.file.size) + (e.at ? ' · ' + fmtDT(e.at) : '') : '',
    failedText: e.msg || DEFAULT_FAILED_MESSAGE,
    primaryLabel: busy ? '만드는 중…' : e.state === 'failed' ? '다시 시도' : done || e.state === 'declined' ? '다시 내보내기' : '파일 만들기 · 저장',
    preview: e.file ? e.file.preview : '',
  };
}
