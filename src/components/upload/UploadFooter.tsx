import { Button, cx } from '@/components/ui';
import styles from './UploadFooter.module.css';

export interface UploadFooterProps {
  /** 안내 문구(aria-live) */
  text: string;
  /** 오류 색 */
  error: boolean;
  /** 요청 중 — '분석 요청 중…' · 취소 잠금 */
  busy: boolean;
  /** 올리는 중 — '분석 시작' disabled */
  startDisabled: boolean;
  /** 요청 중이거나 올리는 중 — aria-disabled */
  cantStart: boolean;
  onCancel: () => void;
}

/**
 * 하단 버튼 줄 — Main.dc.html 316–324. 화면 아래에 붙는다(sticky). 휴대폰에서는 버튼 둘이 1:2 로 한 줄을 채운다.
 * '분석 시작'은 폼 제출 버튼이다 — 요청 중에는 돌림 표시 + '분석 요청 중…'(누름·제출 막힘, 포커스 유지).
 */
export function UploadFooter({ text, error, busy, startDisabled, cantStart, onCancel }: UploadFooterProps) {
  return (
    <div className={styles.bar}>
      <div className={styles.inner}>
        <span aria-live="polite" className={cx(styles.text, error && styles.textError)}>
          {text}
        </span>
        <div className={styles.buttons}>
          <Button variant="secondary" size="xl" className={styles.cancel} onClick={onCancel} disabled={busy}>
            취소
          </Button>
          <Button type="submit" variant="primary" size="xl" className={styles.start} loading={busy} disabled={startDisabled} aria-disabled={cantStart || undefined}>
            {busy ? '분석 요청 중…' : '분석 시작'}
          </Button>
        </div>
      </div>
    </div>
  );
}
