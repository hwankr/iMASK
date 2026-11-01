/* ==========================================================================
   /dev/states 업로드 상태 6개의 시작 조건 — 프로토타입 initScenario(Main.dc.html 1543–1552)와 값까지 같다.
   (분석명, 파일 이름·크기, 경고 문구·목록). 샘플 파일은 서비스 sampleFiles() 에서 받는다.
   ========================================================================== */

import { alertLimit, alertType, userFile, type UploadLimits, type UploadState } from '@/components/upload/uploadModel';
import { CONFIG } from '@/config/app';
import { pad2 } from '@/lib/format';
import type { AnalysisService, StateId } from '@/services/analysis-service';

export type UploadStateId = Extract<
  StateId,
  'upload' | 'upload-selected' | 'upload-unsupported' | 'upload-limit' | 'upload-failed' | 'upload-requesting'
>;

export const UPLOAD_STATE_IDS: readonly UploadStateId[] = [
  'upload',
  'upload-selected',
  'upload-unsupported',
  'upload-limit',
  'upload-failed',
  'upload-requesting',
];

export function isUploadStateId(id: StateId): id is UploadStateId {
  return (UPLOAD_STATE_IDS as readonly StateId[]).includes(id);
}

/** 상태별 처음 값(UploadScreen 의 initial) */
export async function uploadScenario(
  id: UploadStateId,
  service: Pick<AnalysisService, 'sampleFiles'>,
  limits: UploadLimits = CONFIG.upload,
): Promise<Partial<UploadState>> {
  const maxF = limits.maxFiles;
  const maxMB = limits.maxFileMB;
  switch (id) {
    case 'upload':
      return {};
    case 'upload-selected':
      return { name: '김서연 대출상담 서류 (샘플)', files: await service.sampleFiles() };
    case 'upload-unsupported':
      return {
        name: '정○○ 전세대출 서류',
        files: [userFile('대출신청서_스캔.pdf', 'PDF', 2411724), userFile('통장사본.jpg', 'JPG', 845824)],
        alerts: [
          alertType(['계약서_최종.docx — 지원하지 않는 형식 (DOCX)', 'IMG_2041.heic — 지원하지 않는 형식 (HEIC)'], limits.accept),
        ],
      };
    case 'upload-limit': {
      const files = [];
      for (let i = 1; i <= maxF; i++) files.push(userFile('거래내역_' + pad2(i) + '.jpg', 'JPG', 600000 + i * 37000));
      return {
        name: '거래내역 일괄 검토',
        files,
        alerts: [
          alertLimit(
            [
              '파일은 한 분석에 최대 ' + maxF + '개까지 올릴 수 있습니다 — 거래내역_' + pad2(maxF + 1) + '.jpg, 거래내역_' + pad2(maxF + 2) + '.jpg 제외',
              '스캔_전체.pdf (34.2MB) — 파일당 최대 ' + maxMB + 'MB를 넘습니다',
            ],
            3,
            maxF,
            maxMB,
          ),
        ],
      };
    }
    case 'upload-failed':
      return {
        name: '소득증빙 추가 서류',
        files: [
          userFile('소득금액증명_2025.pdf', 'PDF', 352256),
          userFile('건강보험_자격득실확인서.pdf', 'PDF', 1830000, { state: 'failed', error: '업로드 중 연결이 끊겼습니다. 다시 올려 주세요.' }),
          userFile('재직증명서.pdf', 'PDF', 205824),
        ],
      };
    case 'upload-requesting':
      return { name: '김서연 대출상담 서류 (샘플)', files: await service.sampleFiles(), requesting: true, touched: true, frozen: true };
  }
}
