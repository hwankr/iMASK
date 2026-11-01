'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import { Icon, IconButton, SkeletonCard, Spinner, cx } from '@/components/ui';
import { useReplayToggle } from '@/lib/hooks';
import type { PlaceholderModel, ViewerModel } from './detailModel';
import type { PanelProps } from './DocList';
import { PaperPage } from './PaperPage';
import { Tip } from './Tip';
import styles from './DocViewer.module.css';

/** 체험용 샘플로 새 분석을 시작하는 주소(T5 가 ?sample=1 을 읽는다) */
export const TRY_SAMPLE_HREF = '/analyses/new?sample=1';

export interface DocViewerProps {
  v: ViewerModel;
  mobile: boolean;
  /** 좁은 뷰어(700px 미만) — 도구 줄 글자가 줄어든다(원본 vCompact) */
  compact: boolean;
  scrollRef: (el: HTMLElement | null) => void;
  onPrev: () => void;
  onNext: () => void;
  onZoomOut: () => void;
  onZoomIn: () => void;
  onFit: () => void;
  onToggleMask: () => void;
  onPickFinding: (findingId: string) => void;
  /** 미리보기 대신 화면의 '이 문서 다시 분석'(T7) */
  onRetryDoc: (docId: string) => void;
  panel?: PanelProps;
}

function Placeholder({ ph, docId, onRetryDoc }: { ph: PlaceholderModel; docId: string; onRetryDoc: (docId: string) => void }) {
  const action = ph.action;
  return (
    <div className={styles.ph}>
      <span className={cx(styles.phIcon, ph.tone === 'err' && styles.phErr, ph.tone === 'run' && styles.phRun)}>
        {ph.spin ? <Spinner size={24} /> : <Icon name={ph.icon} size={28} strokeWidth={1.9} />}
      </span>
      <strong className={styles.phTitle}>{ph.title}</strong>
      <span className={styles.phText}>{ph.text}</span>
      {ph.skeleton ? <SkeletonCard look="viewer" lines={[46, 92, 78, 86, 58]} className={styles.phSkeleton} /> : null}
      {action && action.key === 'trySample' ? (
        <Link href={TRY_SAMPLE_HREF} className={cx(styles.bigBtn, styles.phBtn)}>
          <Icon name={action.icon} size={17} strokeWidth={2.2} />
          {action.label}
        </Link>
      ) : null}
      {action && action.key === 'retryDoc' ? (
        <button type="button" className={cx(styles.bigBtn, styles.phBtn)} disabled={action.disabled} onClick={() => onRetryDoc(docId)}>
          <Icon name={action.icon} size={17} strokeWidth={2.2} />
          {action.label}
        </button>
      ) : null}
      {ph.note ? <span className={styles.phNote}>{ph.note}</span> : null}
    </div>
  );
}

/**
 * 원문 뷰어(Main 402–456) — 문서 이름 줄, 공지(v.notices), 샘플 문서 한 쪽, 미리보기 대신 화면(placeholderVM),
 * 떠 있는 도구 줄(쪽 이동 · 확대 · 축소 · 화면 맞춤 · 마스킹 미리보기).
 * 쪽이 바뀌면 종이가 떠오르고(dg-page-a/b), 고를 때마다 테두리 신호가 다시 돈다(dg-ring-a/b).
 */
export function DocViewer({
  v,
  mobile,
  compact,
  scrollRef,
  onPrev,
  onNext,
  onZoomOut,
  onZoomIn,
  onFit,
  onToggleMask,
  onPickFinding,
  onRetryDoc,
  panel,
}: DocViewerProps) {
  const pageFlip = !useReplayToggle(v.pageKey);
  const ringFlip = !useReplayToggle(v.ringKey);
  // 떠 있는 도구 줄의 실제 높이(휴대폰만) — 좁은 휴대폰에서 두 줄로 접히면 CSS 가 스크롤 아래 여백을 그만큼 늘린다
  // (DocViewer.module.css 휴대폰 .scroll). 태블릿 · 데스크톱은 재지 않고 변수도 넘기지 않는다.
  const barRef = useRef<HTMLDivElement>(null);
  const [barH, setBarH] = useState<number | null>(null);
  useEffect(() => {
    const el = barRef.current;
    if (!mobile || !el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(([entry]) => {
      setBarH(entry.borderBoxSize?.[0]?.blockSize ?? el.offsetHeight);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [mobile]);
  const barVar = mobile && barH !== null ? { '--viewer-bar-h': `${barH}px` } : null;
  const zoomStyle = { '--paper-zoom': v.zoom, ...barVar } as CSSProperties;
  const wide = !compact;
  const mid = compact && !mobile;

  return (
    <section aria-label="원문 뷰어" className={styles.viewer} style={zoomStyle} {...panel}>
      <div ref={scrollRef} tabIndex={0} aria-label="원문 페이지 영역" className={styles.scroll}>
        <div className={cx(styles.fit, styles.nameLine)}>
          <span className={styles.nameIcon}>
            <Icon name="dg-i-file" size={15} />
          </span>
          <span className={styles.name}>{v.docName}</span>
          {v.hasPage ? <span className={styles.pageNo}>· {v.pageLabel}쪽</span> : null}
        </div>
        {v.notices.length ? (
          <div className={cx(styles.fit, styles.notices)}>
            {v.notices.map((nt) => (
              <div key={nt.tone + nt.title} role="note" className={cx(styles.notice, styles[nt.tone])}>
                <span className={styles.noticeIcon}>
                  <Icon name={nt.icon} size={17} strokeWidth={2.1} />
                </span>
                <div>
                  <strong className={styles.noticeTitle}>{nt.title}</strong> <span className={styles.noticeText}>{nt.text}</span>
                </div>
              </div>
            ))}
          </div>
        ) : null}
        {v.hasPage ? (
          <PaperPage blocks={v.blocks} ariaLabel={v.pageAria} scan={v.scan} pageFlip={pageFlip} ringFlip={ringFlip} tag={v.tag} onPickFinding={onPickFinding} />
        ) : null}
        {v.placeholder && v.doc ? <Placeholder ph={v.placeholder} docId={v.doc.id} onRetryDoc={onRetryDoc} /> : null}
      </div>

      <div className={styles.barWrap}>
        <div ref={barRef} className={styles.bar}>
          <div role="group" aria-label="페이지 이동" className={styles.group}>
            <IconButton label="이전 페이지" icon="dg-i-chev-left" size={34} iconSize={18} strokeWidth={2.2} tooltip="top" disabled={v.noPrev} onClick={onPrev} className={cx(styles.tool, styles.hitPrev)} />
            <span aria-live="polite" className={styles.label}>
              {v.pageLabel}
            </span>
            <IconButton label="다음 페이지" icon="dg-i-chev-right" size={34} iconSize={18} strokeWidth={2.2} tooltip="top" disabled={v.noNext} onClick={onNext} className={cx(styles.tool, styles.hitNext)} />
          </div>
          <span aria-hidden="true" className={styles.div} />
          <div role="group" aria-label="확대와 축소" className={styles.group}>
            <IconButton label="축소" icon="dg-i-zoom-out" size={34} iconSize={18} strokeWidth={2} tooltip="top" disabled={v.noOut} onClick={onZoomOut} className={cx(styles.tool, styles.hitZoomOut)} />
            <span className={cx(styles.label, styles.label2)}>{v.zoomLabel}</span>
            <IconButton label="확대" icon="dg-i-zoom-in" size={34} iconSize={18} strokeWidth={2} tooltip="top" disabled={v.noIn} onClick={onZoomIn} className={cx(styles.tool, styles.hitZoomIn)} />
            <Tip label="화면 맞춤" side="top" hidden={wide}>
              <button type="button" aria-pressed={v.isFit} aria-label="화면 맞춤" disabled={v.noPage} onClick={onFit} className={cx(styles.fitBtn, v.isFit && styles.fitOn)}>
                <Icon name="dg-i-fit" size={15} strokeWidth={2.1} />
                {wide ? '화면 맞춤' : null}
              </button>
            </Tip>
          </div>
          <span aria-hidden="true" className={styles.div} />
          <Tip label="화면에서만 가려 보는 미리보기입니다" side="top">
            <button type="button" aria-pressed={v.mask} aria-label="마스킹 미리보기" disabled={v.noMask} onClick={onToggleMask} className={cx(styles.maskBtn, v.mask && styles.maskOn)}>
              {mobile ? <Icon name="dg-i-eye-off" size={17} /> : null}
              <span aria-hidden="true" className={styles.track}>
                <span className={styles.knob} />
              </span>
              {wide ? '마스킹 미리보기' : null}
              {mid ? '마스킹' : null}
            </button>
          </Tip>
        </div>
      </div>
    </section>
  );
}
