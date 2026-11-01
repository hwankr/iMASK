'use client';

import Link from 'next/link';
import { Icon, Spinner, VisuallyHidden, cx } from '@/components/ui';
import type { DetailActions } from './detailActions';
import type { FailModel } from './detailModel';
import { SpriteIcon } from './SpriteIcon';
import styles from './FailedBody.module.css';

export interface FailedBodyProps {
  fail: FailModel;
  locked: boolean;
  memo: string;
  memoPreview: string;
  memoBtn: string;
  actions: Pick<DetailActions, 'retry' | 'editMemo'>;
}

/**
 * 전체 분석 실패(Main 586–594) — 실패 안내, 파일별 오류, 다음에 할 수 있는 일,
 * '다시 시도'(T7) · '새 분석으로 다시 올리기'(→ /analyses/new) · '검토 메모'(T7), 검토 메모, 위험등급 안내.
 */
export function FailedBody({ fail, locked, memo, memoPreview, memoBtn, actions }: FailedBodyProps) {
  return (
    <div className={styles.wrap}>
      <div className={styles.inner}>
        <div className={styles.head}>
          <span className={styles.icon}>{fail.retrying ? <Spinner size={22} /> : <SpriteIcon name="dg-i-x-circle" className={styles.icon26} />}</span>
          <div className={styles.titles}>
            <h2 className={styles.h2}>{fail.title}</h2>
            <p className={styles.text}>{fail.text}</p>
          </div>
        </div>
        <ul className={styles.files}>
          {fail.files.map((ff, i) => (
            <li key={i} className={styles.file}>
              <span aria-hidden="true" className={styles.fileTile}>
                <Icon name="dg-i-file" size={19} />
              </span>
              <div className={styles.fileTexts}>
                <div className={styles.fileName}>{ff.name}</div>
                <div className={styles.fileMeta}>{ff.meta}</div>
              </div>
              <div className={styles.fileError}>
                <span className={styles.fileErrorIcon}>
                  <Icon name="dg-i-alert" size={15} strokeWidth={2.1} />
                </span>
                <span>
                  <VisuallyHidden>오류 내용: </VisuallyHidden>
                  {ff.error}
                </span>
              </div>
            </li>
          ))}
        </ul>
        <div className={styles.next}>
          <h3 className={styles.h3}>다음에 할 수 있는 일</h3>
          <ol className={styles.steps}>
            <li className={styles.step}>
              <span className={styles.num}>1</span>원본 파일을 다시 저장하거나 스캔해 새 분석으로 올립니다.
            </li>
            <li className={styles.step}>
              <span className={styles.num}>2</span>같은 파일로 다시 시도합니다. 파일이 손상된 경우 같은 결과가 나올 수 있습니다.
            </li>
            <li className={styles.step}>
              <span className={styles.num}>3</span>처리 내용을 검토 메모로 남기고 검토를 완료합니다.
            </li>
          </ol>
        </div>
        <div className={styles.btns}>
          <button type="button" className={cx(styles.btn, styles.primary)} disabled={fail.retrying} onClick={() => actions.retry()} data-slot="retry-all">
            <Icon name="dg-i-refresh" size={17} strokeWidth={2.2} />
            {fail.retryLabel}
          </button>
          <Link href="/analyses/new" className={cx(styles.btn, styles.secondary)}>
            <Icon name="dg-i-upload" size={17} strokeWidth={2.1} />새 분석으로 다시 올리기
          </Link>
          <button type="button" className={cx(styles.btn, styles.ghost)} disabled={locked} onClick={actions.editMemo}>
            <Icon name="dg-i-memo" size={17} />
            검토 메모 {memoBtn}
          </button>
        </div>
        {memo ? (
          <div className={styles.memo}>
            <strong>검토 메모</strong> · {memoPreview}
          </div>
        ) : null}
        <p className={styles.foot}>위험등급은 분석이 끝나야 정해집니다. 지금은 ‘미평가’이며, 검토 상태는 담당자가 완료할 때까지 그대로 유지됩니다.</p>
      </div>
    </div>
  );
}
