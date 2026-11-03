'use client';

/* ==========================================================================
   상세 — 실제 분석 모드(/analyses/[id], NEXT_PUBLIC_IMASK_SERVICE=api)
   - useAnalysis(id) 로만 데이터를 받는다. 대기·분석 중인 동안 3초마다 refresh()(앞 요청이 끝난 뒤 다음,
     탭이 숨겨지면 쉬고 다시 보이면 바로 한 번). 조회할 때마다 백엔드가 Upstage 상태를 한 번 확인한다.
   - 대기·분석 중: 흐르는 막대 + 안내 + Upstage 상태(+ 확인 실패 문구). 실패: 오류 문구 그대로 + '새 분석'.
     완료 + 공통 계약 결과(raw.detailReady): 데모와 같은 상세 검토 화면(DetailView — 문서 목록 · 원본 파일 원문과 위치 상자 ·
     결과 패널 · 분석 요약, 읽기 전용). 진행 중에서 완료로 바뀌면 새로 고침 없이 바로 바뀐다.
     완료지만 옛 형식(서류 0개 등): 요약 + 단계별 결과(JSON 나무).
   - 401 → 접근 코드 입력 + '다시 불러오기'. 404 → 안내 + '새 분석'(데모처럼 목록으로 보내지 않는다).
   - 상태가 바뀌면 화면 낭독기에 알린다.
   ========================================================================== */

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import type { FormEvent } from 'react';
import { AnalysisStatusLabel, Banner, Button, Icon, IndeterminateBar, Skeleton, VisuallyHidden, cx } from '@/components/ui';
import { fmtDT, fmtSize } from '@/lib/format';
import { apiErrorCode } from '@/services';
import { useAnalysis, useLiveExtras } from '@/services/react';
import type { Analysis } from '@/services/types';
import { DetailView } from '@/components/detail/DetailScreen';
import { AccessCodeField } from './AccessCodeField';
import { LiveResult } from './LiveResult';
import { useClock, usePolling, useStatusAnnounce } from './liveHooks';
import { elapsedText, isPolling, upstageStatusText } from './liveModel';
import styles from './LiveDetailScreen.module.css';

const NEW_HREF = '/analyses/new';

export function LiveDetailScreen({ id }: { id: string }) {
  const { data, error, refresh } = useAnalysis(id);
  const extras = useLiveExtras();
  const code = apiErrorCode(error);
  const unauthorized = code === 'unauthorized';
  usePolling(!!data && isPolling(data.status) && !unauthorized, refresh);
  useStatusAnnounce(data?.status);

  if (data === undefined) {
    if (unauthorized) return <AccessGate onRetry={refresh} wrong />;
    if (error) return <LoadFailed message={messageOf(error)} onRetry={refresh} />;
    return <LiveSkeleton />;
  }
  if (data === null) return <NotFound />;
  if (data.status === 'done' && data.raw?.detailReady) {
    const notice = unauthorized ? '접근 코드가 맞지 않아 최신 상태를 확인하지 못했습니다. 지금 보이는 결과는 마지막으로 받은 값입니다.' : error ? messageOf(error) : '';
    return <DetailView analysis={data} live={{ extras, notice }} />;
  }
  return <LiveView a={data} unauthorized={unauthorized} refreshError={error && !unauthorized ? messageOf(error) : ''} onRetry={refresh} />;
}

function messageOf(error: unknown): string {
  return error instanceof Error && error.message ? error.message : '분석 건을 불러오지 못했습니다.';
}

/* ---------- 분석 건 ---------- */

function LiveView({ a, unauthorized, refreshError, onRetry }: { a: Analysis; unauthorized: boolean; refreshError: string; onRetry: () => Promise<void> }) {
  const router = useRouter();
  const raw = a.raw;
  const polling = isPolling(a.status);
  const now = useClock(polling);
  const elapsed = polling && raw && now ? elapsedText(raw.createdAt, now) : '';
  // 올린 파일은 raw.file 에서 — 완료 뒤 docs 가 분류된 서류로 바뀌어도 머리는 올린 파일 하나를 보인다
  const file = raw?.file ?? null;
  const failed = a.status === 'failed' || a.status === 'partial';

  return (
    <div className={styles.screen}>
      <div className={styles.page}>
        <div>
          <Link href="/" className={styles.back}>
            <Icon name="dg-i-arrow-left" size={17} strokeWidth={2.2} />
            문서 분석
          </Link>
        </div>

        <header className={styles.head} data-live-status={a.status}>
          <span className={styles.eyebrow}>실제 분석 · Upstage 워크플로우</span>
          <h1 className={styles.title}>{a.name || '이름 없는 분석'}</h1>
          <div className={styles.meta}>
            <AnalysisStatusLabel status={a.status} strong />
            <span className={styles.metaItem}>
              <VisuallyHidden>분석 번호 </VisuallyHidden>
              <span className={styles.mono}>{a.code}</span>
            </span>
            <span className={styles.metaItem}>요청 {fmtDT(a.submittedAt)}</span>
            {file ? (
              <span className={styles.metaItem}>
                {file.name} · {fmtSize(file.size)}
              </span>
            ) : null}
            {elapsed ? (
              <span className={styles.metaItem}>
                경과 <span className={styles.mono}>{elapsed}</span>
              </span>
            ) : null}
          </div>
        </header>

        {unauthorized ? (
          <div className={styles.card}>
            <AccessForm onRetry={onRetry} wrong lead="접근 코드가 맞지 않아 상태를 확인하지 못했습니다. 코드를 다시 넣고 다시 불러오세요." />
          </div>
        ) : null}

        {polling ? (
          <section className={cx(styles.card, styles.running)} aria-label="진행 상태">
            <IndeterminateBar variant="track" tone="run" size="md" />
            <p className={styles.runText}>
              {a.status === 'queued' ? '분석을 준비하고 있습니다.' : 'Upstage 워크플로우가 분석하고 있습니다(보통 1~3분).'} 3초마다 상태를 확인합니다.
            </p>
            <p className={styles.runSub}>
              Upstage 상태: <strong>{upstageStatusText(raw?.upstageStatus ?? '')}</strong>
            </p>
            {raw?.pollError ? (
              <p className={styles.soft}>
                <Icon name="dg-i-info" size={15} /> 이번 확인은 실패했습니다: {raw.pollError} 분석은 계속되며 다음 확인에서 다시 봅니다.
              </p>
            ) : null}
            {refreshError ? (
              <p className={styles.soft}>
                <Icon name="dg-i-info" size={15} /> 서버에서 상태를 받지 못했습니다: {refreshError} 3초 뒤 다시 확인합니다.
              </p>
            ) : null}
          </section>
        ) : null}

        {failed ? (
          <Banner
            shape="card"
            variant="failed"
            title="분석에 실패했습니다"
            description={raw?.error || '실패 이유를 받지 못했습니다.'}
            actions={[{ label: '새 분석', onClick: () => router.push(NEW_HREF) }]}
          />
        ) : null}

        {a.status === 'done' || (failed && raw?.result) ? (
          <LiveResult result={raw?.result ?? null} createdAt={raw?.createdAt ?? ''} updatedAt={raw?.updatedAt ?? ''} jobId={raw?.jobId ?? ''} />
        ) : null}

        {a.status === 'done' && refreshError ? <p className={styles.soft}>{refreshError}</p> : null}
      </div>
    </div>
  );
}

/* ---------- 접근 코드 · 오류 · 없음 · 불러오는 중 ---------- */

function AccessForm({ onRetry, wrong, lead }: { onRetry: () => Promise<void>; wrong: boolean; lead: string }) {
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    void onRetry();
  };
  return (
    <form className={styles.gateForm} onSubmit={submit} noValidate>
      <p className={styles.gateLead}>{lead}</p>
      <AccessCodeField error={wrong ? '접근 코드가 맞지 않습니다.' : undefined} />
      <div>
        <Button type="submit" variant="primary" icon="dg-i-refresh">
          다시 불러오기
        </Button>
      </div>
    </form>
  );
}

function AccessGate({ onRetry, wrong }: { onRetry: () => Promise<void>; wrong: boolean }) {
  return (
    <div className={styles.screen}>
      <div className={cx(styles.page, styles.narrow)}>
        <h1 className={styles.title}>접근 코드가 필요합니다</h1>
        <div className={styles.card}>
          <AccessForm onRetry={onRetry} wrong={wrong} lead="실제 분석 결과를 보려면 팀에서 받은 접근 코드를 넣으세요." />
        </div>
      </div>
    </div>
  );
}

function LoadFailed({ message, onRetry }: { message: string; onRetry: () => Promise<void> }) {
  return (
    <div className={styles.screen}>
      <div className={cx(styles.page, styles.narrow)}>
        <div role="alert" className={styles.alert}>
          <Icon name="dg-i-x-circle" size={18} strokeWidth={2.1} />
          <span>
            분석 건을 불러오지 못했습니다. {message}
          </span>
        </div>
        <div>
          <Button variant="secondary" icon="dg-i-refresh" onClick={() => void onRetry()}>
            다시 불러오기
          </Button>
        </div>
      </div>
    </div>
  );
}

function NotFound() {
  return (
    <div className={styles.screen}>
      <div className={cx(styles.page, styles.narrow)}>
        <h1 className={styles.title}>분석 건을 찾을 수 없습니다</h1>
        <p className={styles.lead}>주소가 틀렸거나 지워진 분석입니다. 새 분석을 시작하거나 목록에서 다시 고르세요.</p>
        <div className={styles.actions}>
          <Button href={NEW_HREF} variant="primary" icon="dg-i-plus">
            새 분석
          </Button>
          <Button href="/" variant="secondary">
            목록으로
          </Button>
        </div>
      </div>
    </div>
  );
}

function LiveSkeleton() {
  return (
    <div className={styles.screen} aria-busy="true">
      <VisuallyHidden>
        <span role="status">분석 건을 불러오는 중입니다.</span>
      </VisuallyHidden>
      <div className={styles.page} aria-hidden="true">
        <Skeleton size="title" width={40} />
        <Skeleton width={70} />
        <div className={styles.card}>
          <Skeleton size="title" width={30} />
          <Skeleton width={90} />
          <Skeleton width={80} />
          <Skeleton width={60} />
        </div>
      </div>
    </div>
  );
}
