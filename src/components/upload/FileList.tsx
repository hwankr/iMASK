import type { Ref } from 'react';
import { cx, Icon, IconButton, IndeterminateBar } from '@/components/ui';
import { staggerStyle } from '@/lib/hooks/useStagger';
import type { UploadFileRow } from './uploadModel';
import styles from './FileList.module.css';

export interface FileListProps {
  listRef: Ref<HTMLUListElement>;
  rows: UploadFileRow[];
  count: number;
  total: string;
  /** 요청 중 — 제거 버튼 잠금 */
  busy: boolean;
  onRemove: (id: string) => void;
  onRetry: (id: string) => void;
}

/**
 * 선택한 파일 — Main.dc.html 289–312. 형식 타일, 이름, '샘플', 크기, 상태(올리는 중 · 준비됨 · 실패 + 다시 올리기), 제거.
 * 행은 같이 들어온 묶음 안에서 0.04초 간격으로 차례로 나타난다(dg-in).
 */
export function FileList({ listRef, rows, count, total, busy, onRemove, onRetry }: FileListProps) {
  return (
    <div className={styles.section}>
      <div className={styles.head}>
        <strong className={styles.count}>선택한 파일 {count}개</strong>
        <span className={styles.total}>합계 {total}</span>
      </div>
      <ul ref={listRef} className={styles.list}>
        {rows.map((r) => (
          <li key={r.file.id} className={cx(styles.row, r.separated && styles.separated, r.failed && styles.failed)} style={staggerStyle(r.enterIndex)}>
            <span aria-hidden="true" className={styles.tile}>
              {r.file.ext}
            </span>
            <div className={styles.info}>
              <div className={styles.nameLine}>
                <span className={styles.name}>{r.file.name}</span>
                {r.sample ? <span className={styles.sample}>샘플</span> : null}
              </div>
              <span className={styles.meta}>{r.meta}</span>
              {r.failed ? (
                <span className={styles.error}>
                  <Icon name="dg-i-x-circle" size={14} strokeWidth={2.1} />
                  {r.file.error}
                </span>
              ) : null}
            </div>
            {r.uploading ? (
              <span className={styles.uploading}>
                올리는 중
                <IndeterminateBar variant="track" size="sm" tone="accent" />
              </span>
            ) : null}
            {r.ready ? (
              <span className={styles.ready}>
                <Icon name="dg-i-check-circle" size={16} strokeWidth={2.2} />
                준비됨
              </span>
            ) : null}
            {r.failed ? (
              <button type="button" className={styles.retry} onClick={() => onRetry(r.file.id)}>
                <Icon name="dg-i-refresh" size={14} strokeWidth={2.2} />
                다시 올리기
              </button>
            ) : null}
            <IconButton
              label={r.removeLabel}
              icon="dg-i-trash"
              size={36}
              iconSize={18}
              strokeWidth={2}
              variant="muted"
              tooltip="top"
              className={styles.remove}
              disabled={busy}
              onClick={() => onRemove(r.file.id)}
              data-remove={r.file.id}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}
