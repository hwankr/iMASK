import { cx, Icon, IconButton } from '@/components/ui';
import type { UploadAlert } from './uploadModel';
import styles from './UploadAlertBox.module.css';

export interface UploadAlertBoxProps {
  alert: UploadAlert;
  onDismiss: () => void;
}

/** 경고 상자 — 지원하지 않는 형식(빨강) · 업로드 제한(주황). Main.dc.html 277–287, uploadVM alerts(2025) */
export function UploadAlertBox({ alert, onDismiss }: UploadAlertBoxProps) {
  return (
    <div role="alert" className={cx(styles.alert, alert.id === 'type' ? styles.type : styles.limit)}>
      <span className={styles.tile}>
        <Icon name={alert.icon} size={18} strokeWidth={2.1} />
      </span>
      <div className={styles.body}>
        <strong className={styles.title}>{alert.title}</strong>
        <ul className={styles.items}>
          {alert.items.map((it, i) => (
            <li key={i}>{it}</li>
          ))}
        </ul>
        <span className={styles.hint}>{alert.hint}</span>
      </div>
      <IconButton label="안내 닫기" icon="dg-i-x" size={34} iconSize={17} strokeWidth={2.2} variant="ghost" className={styles.close} onClick={onDismiss} data-alert-close="" />
    </div>
  );
}
