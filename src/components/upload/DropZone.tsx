import { useId, type ChangeEvent, type DragEvent, type Ref } from 'react';
import { buttonClass, cx, Icon, VisuallyHidden } from '@/components/ui';
import styles from './DropZone.module.css';

export interface DropZoneProps {
  /** 파일이 있으면 한 줄로 줄인다 */
  compact: boolean;
  /** 끌어다 놓는 중 — 상자가 커지고 아이콘이 들썩인다 */
  drag: boolean;
  /** 파일 없이 시작을 눌렀다 */
  error: boolean;
  title: string;
  limitsText: string;
  hintText: string;
  /** <input accept> */
  accept: string;
  busy: boolean;
  zoneRef: Ref<HTMLDivElement>;
  inputRef: Ref<HTMLInputElement>;
  onPick: (e: ChangeEvent<HTMLInputElement>) => void;
  onDragOver: (e: DragEvent<HTMLDivElement>) => void;
  onDragLeave: (e: DragEvent<HTMLDivElement>) => void;
  onDrop: (e: DragEvent<HTMLDivElement>) => void;
}

/**
 * 문서 파일 — 머리 줄(라벨 · 제한 안내), 끌어다 놓는 상자, 문서 묶음 안내(Main 266–275).
 * '파일 선택'은 진짜 <input type="file" multiple> 을 버튼 모양 라벨이 감싼다(입력이 라벨 전체를 덮어 누르면 열린다).
 */
export function DropZone({
  compact,
  drag,
  error,
  title,
  limitsText,
  hintText,
  accept,
  busy,
  zoneRef,
  inputRef,
  onPick,
  onDragOver,
  onDragLeave,
  onDrop,
}: DropZoneProps) {
  const labelId = useId();
  const hintId = useId();
  return (
    <div className={styles.section}>
      <div className={styles.labelRow}>
        <span id={labelId} className={styles.label}>
          문서 파일{' '}
          <span aria-hidden="true" className={styles.req}>
            *
          </span>
        </span>
        <span className={styles.limits}>{limitsText}</span>
      </div>
      <div
        ref={zoneRef}
        role="group"
        aria-labelledby={labelId}
        data-drag={drag || undefined}
        className={cx(styles.zone, compact && styles.compact, error && styles.error, drag && styles.drag)}
        onDragEnter={onDragOver}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        <span aria-hidden="true" className={styles.icon}>
          <Icon name="dg-i-upload" size={28} strokeWidth={2} />
        </span>
        <span className={styles.title}>{title}</span>
        <label className={buttonClass({ variant: 'dark', size: 'lg', withIcon: true, className: styles.pick })}>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={accept}
            onChange={onPick}
            disabled={busy}
            aria-describedby={hintId}
            className={styles.input}
          />
          <Icon name="dg-i-folder" size={17} strokeWidth={2.1} />
          파일 선택
        </label>
        {compact ? (
          <VisuallyHidden id={hintId}>{hintText}</VisuallyHidden>
        ) : (
          <span id={hintId} className={styles.hint}>
            {hintText}
          </span>
        )}
      </div>
      <p className={styles.note}>
        <span className={styles.noteIcon}>
          <Icon name="dg-i-link" size={16} strokeWidth={2.1} />
        </span>
        <span>같은 업무와 관련된 서류를 함께 올리면 문서 간 정보를 함께 확인할 수 있습니다. 올린 파일은 모두 하나의 분석 건으로 묶입니다.</span>
      </p>
    </div>
  );
}
