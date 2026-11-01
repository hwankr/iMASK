import { Icon } from '@/components/ui';
import styles from './SampleCard.module.css';

export interface SampleCardProps {
  /** '샘플 문서 불러오기' */
  onLoad: () => void;
  disabled: boolean;
}

/** 데모용 샘플 문서로 체험하기 — Main.dc.html 254–258 */
export function SampleCard({ onLoad, disabled }: SampleCardProps) {
  return (
    <div className={styles.card}>
      <span aria-hidden="true" className={styles.tile}>
        <Icon name="dg-i-play" size={20} strokeWidth={2.2} />
      </span>
      <div className={styles.text}>
        <strong className={styles.title}>데모용 샘플 문서로 체험하기</strong>
        <span className={styles.desc}>가상의 신청서 · 원천징수영수증 · 거래내역서 3종으로 분석부터 검토 완료까지 진행해 볼 수 있습니다.</span>
      </div>
      <button type="button" className={styles.button} onClick={onLoad} disabled={disabled}>
        샘플 문서 불러오기
      </button>
    </div>
  );
}
