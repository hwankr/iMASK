'use client';

import { Icon, Modal } from '@/components/ui';
import { fmtDT } from '@/lib/format';
import type { Analysis } from '@/services/types';
import styles from './ErrorModal.module.css';

export interface ErrorModalProps {
  /** 오류를 볼 분석 건. null 이면 닫혀 있다. */
  analysis: Analysis | null;
  onClose: () => void;
  onOpenDetail: (id: string) => void;
  onRetry: (id: string) => void;
}

/**
 * 분석 오류 내용 — 프로토타입 modalVM `type: 'error'`(Main 2498–2503) · 마크업 731.
 * 실패한(다시 분석 중인) 문서마다 이름과 오류, 안내 문단. 버튼: 닫기 · 상세 보기 · 다시 시도(열릴 때 포커스).
 * 다시 시도하는 동안은 돌림 표시 + '다시 시도하는 중…'(누를 수 없음, 포커스는 남는다).
 */
export function ErrorModal({ analysis: a, onClose, onOpenDetail, onRetry }: ErrorModalProps) {
  const files = a
    ? a.docs
        .filter((d) => d.status === 'failed' || d.status === 'running')
        .map((d) => ({ id: d.id, name: d.name, error: d.status === 'running' ? '다시 분석하는 중입니다…' : d.error || '처리하지 못했습니다.' }))
    : [];
  return (
    <Modal
      open={a !== null}
      onClose={onClose}
      title="분석 오류 내용"
      subtitle={a ? a.name + ' · 접수 ' + fmtDT(a.submittedAt) : undefined}
      width="sm"
      buttons={
        a
          ? [
              { label: '닫기', onClick: onClose, variant: 'ghost' },
              { label: '상세 보기', onClick: () => onOpenDetail(a.id), variant: 'secondary' },
              { label: a.retrying ? '다시 시도하는 중…' : '다시 시도', onClick: () => onRetry(a.id), variant: 'primary', loading: a.retrying, autoFocus: true },
            ]
          : []
      }
    >
      <div className={styles.body}>
        {files.map((f) => (
          <div key={f.id} className={styles.file}>
            <span className={styles.icon}>
              <Icon name="dg-i-x-circle" size={18} strokeWidth={2.1} />
            </span>
            <div className={styles.fileText}>
              <strong className={styles.fileName}>{f.name}</strong>
              <span className={styles.fileError}>{f.error}</span>
            </div>
          </div>
        ))}
        <p className={styles.note}>
          같은 파일로 다시 시도하거나, 원본을 다시 저장·스캔해 새 분석으로 올려 주세요. 위험등급은 분석이 끝나야 정해지므로 지금은 ‘미평가’입니다.
        </p>
      </div>
    </Modal>
  );
}
