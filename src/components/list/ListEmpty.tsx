import { Button } from '@/components/ui';
import { newAnalysisHref } from '@/lib/routes';
import { useRouteBase } from '@/services/react';
import styles from './ListEmpty.module.css';

/**
 * 분석 이력 없음 — Main 205–233. 그림, 제목, 단계 3개, '첫 문서 분석하기'(→ /analyses/new, `/demo` 아래면 /demo/analyses/new),
 * '샘플 분석 건 둘러보기'(데모 버튼 — 데모 서비스일 때만).
 * 실무자가 쓰는 화면이라 원본의 설명 문단과 아래 데모 안내 문구는 뺐다(데모 여부는 헤더 배지가 보인다).
 */
export function ListEmpty({ onLoadSamples }: { onLoadSamples?: () => void }) {
  const base = useRouteBase();
  return (
    <section aria-labelledby="dg-empty-title" className={styles.empty}>
      <EmptyArt />
      <h2 id="dg-empty-title" className={styles.title}>
        아직 분석한 문서가 없습니다
      </h2>
      <ol className={styles.steps}>
        <li className={styles.step}>
          <span className={styles.stepNumFirst}>1</span>문서 올리기
        </li>
        <li aria-hidden="true" className={styles.stepLine} />
        <li className={styles.step}>
          <span className={styles.stepNum}>2</span>탐지 결과와 원문 근거 확인
        </li>
        <li aria-hidden="true" className={styles.stepLine} />
        <li className={styles.step}>
          <span className={styles.stepNum}>3</span>검토 완료 후 보고서 내보내기
        </li>
      </ol>
      <div className={styles.ctas}>
        <Button href={newAnalysisHref(base)} variant="primary" size="xl" raised icon="dg-i-upload" iconStrokeWidth={2.2} className={styles.cta}>
          첫 문서 분석하기
        </Button>
        {onLoadSamples ? (
          <Button variant="secondary" size="xl" icon="dg-i-play" iconStrokeWidth={2.2} className={styles.ctaSecondary} onClick={onLoadSamples}>
            샘플 분석 건 둘러보기
          </Button>
        ) : null}
      </div>
    </section>
  );
}

/** 빈 목록 그림(184 × 132) — Main 207–217. 색은 토큰(클래스)으로. */
function EmptyArt() {
  return (
    <svg className={styles.art} viewBox="0 0 184 132" fill="none" aria-hidden="true" focusable="false">
      <rect x="58" y="10" width="80" height="100" rx="14" className={styles.artBack} />
      <rect x="40" y="20" width="84" height="104" rx="14" strokeWidth="2" className={styles.artPaper} />
      <rect x="54" y="40" width="42" height="7" rx="3.5" className={styles.artLine} />
      <rect x="54" y="56" width="56" height="7" rx="3.5" className={styles.artLine} />
      <rect x="54" y="72" width="34" height="9" rx="4.5" className={styles.artMark} />
      <rect x="54" y="90" width="48" height="7" rx="3.5" className={styles.artLine} />
      <circle cx="128" cy="82" r="24" strokeWidth="6" className={styles.artLens} />
      <path d="M145 99 160 114" strokeWidth="8" strokeLinecap="round" className={styles.artStroke} />
      <path d="M117 82.5 125 90.5 140 75" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" className={styles.artStroke} />
    </svg>
  );
}
