'use client';

import type { ExportFormat } from '@/display/rules';
import { Icon, Modal, RadioList, Spinner, cx } from '@/components/ui';
import { FORMAT_OPTIONS, LIVE_FORMAT_OPTIONS, exportView, type ExportUiState } from './exportModel';
import styles from './ExportModal.module.css';

export interface ExportModalProps {
  open: boolean;
  onClose: () => void;
  /** 모달 부제(분석 이름) */
  analysisName: string;
  /** 분석 ID 표기(DG-…) — 파일을 만들기 전 예상 파일 이름에 쓴다 */
  code: string;
  state: ExportUiState;
  onPickFormat: (format: ExportFormat) => void;
  /** '파일 만들기 · 저장' / '다시 시도' / '다시 내보내기' */
  onExport: () => void;
  /** 실제 분석이면 JSON 형식 설명이 다르다(문서 간 연결 없음) */
  live?: boolean;
}

/* 형식 설명은 원본처럼 보통 굵기 — 공통 RadioList 는 고른 줄의 라벨 전체를 굵게(700) 하므로 설명 글자에서 되돌린다 */
const withDesc = (list: typeof FORMAT_OPTIONS | typeof LIVE_FORMAT_OPTIONS) =>
  list.map((o) => ({ ...o, description: <span className={styles.desc}>{o.description}</span> }));
const OPTIONS = withDesc(FORMAT_OPTIONS);
const LIVE_OPTIONS = withDesc(LIVE_FORMAT_OPTIONS);

/**
 * 결과 내보내기 모달 — Main 733–744 · modalVM 'export'(2505–2518).
 * 형식(CSV·JSON), 마스킹 안내, 파일 이름, 진행 상태 5가지(만드는 중 · 내보내기 완료 · 파일을 만들었습니다 · 저장 취소 · 실패),
 * 만든 파일 미리보기(앞부분). 파일 내용은 서비스(buildExport)가 만든 그대로다. 실제 분석은 JSON 형식 설명만 다르다.
 */
export function ExportModal({ open, onClose, analysisName, code, state, onPickFormat, onExport, live = false }: ExportModalProps) {
  const v = exportView(state, code);
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="결과 내보내기"
      subtitle={analysisName}
      width="md"
      buttons={[
        { label: '닫기', onClick: onClose, variant: 'ghost' },
        { label: v.primaryLabel, onClick: onExport, variant: 'primary', loading: v.busy, autoFocus: true },
      ]}
    >
      <RadioList legend="파일 형식" name="dg-exp-format" options={live ? LIVE_OPTIONS : OPTIONS} value={state.format} onChange={onPickFormat} disabled={v.busy} />

      <div className={styles.mask}>
        <span className={styles.maskIcon}>
          <Icon name="dg-i-eye-off" size={17} />
        </span>
        <span>
          <strong className={styles.strong}>민감한 값은 마스킹해 내보냅니다.</strong> 주민등록번호·계좌번호·연락처 등은 마스킹한 표시값만 넣고 원문 값은 넣지 않습니다.
        </span>
      </div>

      <div className={styles.fileRow}>
        <span className={styles.fileLabel}>파일 이름</span>
        <span className={styles.fileName}>{v.fileName}</span>
      </div>

      {state.state === 'working' ? (
        <div role="status" className={cx(styles.box, styles.working)}>
          <Spinner size={16} />
          파일을 만들고 저장을 요청하고 있습니다…
        </div>
      ) : null}
      {state.state === 'saved' ? (
        <div role="status" className={cx(styles.box, styles.done, styles.saved)}>
          <span className={styles.boxIcon}>
            <Icon name="dg-i-check-circle" size={18} strokeWidth={2.2} />
          </span>
          <span>
            <strong className={styles.savedTitle}>내보내기 완료</strong> · {v.doneText}
          </span>
        </div>
      ) : null}
      {state.state === 'handed' ? (
        <div role="status" className={cx(styles.box, styles.done, styles.info)}>
          <span className={styles.boxIcon}>
            <Icon name="dg-i-info" size={18} />
          </span>
          <span>
            <strong className={styles.strong}>파일을 만들었습니다</strong> · {v.doneText} 브라우저 다운로드 목록에서 확인하세요. 저장되지 않았다면 다시 시도하세요.
          </span>
        </div>
      ) : null}
      {state.state === 'declined' ? (
        <div role="status" className={cx(styles.box, styles.done, styles.info)}>
          <span className={styles.boxIcon}>
            <Icon name="dg-i-info" size={18} />
          </span>
          <span>
            <strong className={styles.strong}>저장을 취소했습니다</strong> · 파일은 저장되지 않았습니다. 필요하면 다시 내보낼 수 있습니다.
          </span>
        </div>
      ) : null}
      {state.state === 'failed' ? (
        <div role="alert" className={cx(styles.box, styles.done, styles.failed)}>
          <span className={styles.boxIcon}>
            <Icon name="dg-i-x-circle" size={18} strokeWidth={2.1} />
          </span>
          <span>
            <strong className={styles.failedTitle}>내보내기에 실패했습니다</strong> · {v.failedText}
          </span>
        </div>
      ) : null}

      {v.preview ? (
        <details className={styles.preview}>
          <summary className={styles.previewSummary}>만든 파일 미리보기 (앞부분)</summary>
          <pre className={styles.previewText}>{v.preview}</pre>
        </details>
      ) : null}
    </Modal>
  );
}
