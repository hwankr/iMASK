'use client';

import { useState, type ReactNode } from 'react';
import { DemoBadge } from '@/components/layout/DemoBadge';
import {
  AnalysisStatusLabel,
  Banner,
  Button,
  CountUp,
  Dropdown,
  FilterChips,
  FindingStatusLabel,
  Icon,
  IconButton,
  IndeterminateBar,
  Modal,
  RadioList,
  ReviewStatusPill,
  RiskBadge,
  SearchField,
  SegmentedTabs,
  SkeletonCard,
  Spinner,
  Switch,
  TextField,
  Toast,
  cx,
  useToast,
  type DropdownOption,
} from '@/components/ui';
import { CONFIG } from '@/config/app';
import {
  ASTATUS,
  CATS,
  FP_REASONS,
  FSTATUS,
  RISK,
  RISK_LEVELS,
  RSTATUS,
  type AnalysisStatus,
  type FindingStatus,
  type FpReason,
  type InfoCategory,
  type ReviewStatus,
  type RiskLevel,
} from '@/display/rules';
import { staggerStyle, useReplayToggle } from '@/lib/hooks/useStagger';
import styles from './board.module.css';

/* 보드에 쓰인 예시 건수(Components.dc.html 03 드롭다운 펼친 상태) */
const RISK_COUNTS: Record<RiskLevel, number> = { high: 2, medium: 1, low: 1, unrated: 2 };
const REVIEW_COUNTS: Record<ReviewStatus, number> = { none: 2, needed: 3, done: 1 };

type RiskFilter = 'all' | RiskLevel;
type ReviewFilter = 'all' | ReviewStatus;
type ChipFilter = 'all' | 'open' | 'high' | 'medium';
type ResultTab = 'findings' | 'review' | 'links';
type SortKey = 'recent' | 'risk';

/** 위험등급 필터 선택지 — 라벨·막대·색은 ② RISK 에서 */
const RISK_OPTIONS: readonly DropdownOption<RiskFilter>[] = [
  { value: 'all', label: '전체', icon: 'dg-i-layers', count: 6 },
  ...RISK_LEVELS.map((k) => ({ value: k, label: RISK[k].label, icon: RISK[k].glyph, iconColor: RISK[k].fg, tileColor: RISK[k].bg, count: RISK_COUNTS[k] })),
];

/** 검토 상태 필터 선택지 — 라벨·아이콘·색은 ② RSTATUS 에서 */
const REVIEW_OPTIONS: readonly DropdownOption<ReviewFilter>[] = [
  { value: 'all', label: '전체', icon: 'dg-i-layers', count: 6 },
  ...(Object.keys(RSTATUS) as ReviewStatus[]).map((k) => ({
    value: k,
    label: RSTATUS[k].label,
    icon: RSTATUS[k].icon,
    iconColor: RSTATUS[k].fg,
    tileColor: RSTATUS[k].bg,
    count: REVIEW_COUNTS[k],
  })),
];

const SORT_OPTIONS: readonly DropdownOption<SortKey>[] = [
  { value: 'recent', label: '최근 접수순', icon: 'dg-i-clock' },
  { value: 'risk', label: '위험도순', icon: RISK.high.glyph, iconColor: RISK.high.fg, tileColor: RISK.high.bg },
];

/** 분류 수정 창의 정보 종류 — ② CATS, 최초 AI 값은 '계좌번호' */
const AI_CAT: InfoCategory = '계좌번호';
const CAT_OPTIONS: readonly DropdownOption<InfoCategory>[] = CATS.map((c) => ({ value: c, label: c, aiOriginal: c === AI_CAT }));

const ANALYSIS_KEYS = Object.keys(ASTATUS) as AnalysisStatus[];
const REVIEW_KEYS = Object.keys(RSTATUS) as ReviewStatus[];
const FINDING_KEYS = Object.keys(FSTATUS) as FindingStatus[];

/** 보드 03 '선택 목록' — ② FP_REASONS 중 보드에 그려진 두 개 */
const BOARD_REASONS = [FP_REASONS[0], FP_REASONS[2]] as const;

const MOTION_ROWS: readonly [string, string, string][] = [
  ['화면 전환', '12px 아래에서 떠오르며 나타남 · 0.45초', '어느 화면으로 왔는지 알림'],
  ['목록 · 필터 변경', '행이 0.04초 간격으로 차례로 등장', '결과가 새로 걸러졌음을 보여 줌'],
  ['요약 숫자', '0에서 세어 올라가고, 검토 후엔 새 값까지 이어서 변함', '검토 완료가 숫자에 반영됨을 체감'],
  ['탭 · 스위치 · 메뉴', '흰 판과 밑줄이 선택한 곳으로 미끄러짐', '무엇이 바뀌었는지 눈으로 따라감'],
  ['탐지 항목 펼침', '내용이 위에서 내려오며 열리고 화살표가 돌아감', '같은 자리에서 열렸음을 알림'],
  ['원문 위치', '해당 위치까지 부드럽게 이동 후 테두리 신호 두 번, 쪽이 바뀌면 종이가 떠오름', '근거 위치를 놓치지 않게'],
  ['모달 · 토스트', '배경이 흐려지고 창이 살짝 커지며 떠오름 · 토스트는 아래에서 올라옴', '작업 흐름을 끊지 않는 확인'],
  ['업로드', '끌어다 놓는 동안 상자가 커지고 아이콘이 들썩임 · 파일 행이 차례로 등장', '놓을 수 있는 곳임을 알림'],
];

function Section({ num, id, title, desc, children, last = false }: { num: string; id: string; title: string; desc: string; children: ReactNode; last?: boolean }) {
  return (
    <section aria-labelledby={id} className={cx(styles.section, last && styles.sectionLast)}>
      <div className={styles.sectionHead}>
        <span className={styles.num}>{num}</span>
        <h2 id={id} className={styles.h2}>
          {title}
        </h2>
        <p className={styles.desc}>{desc}</p>
      </div>
      <div className={styles.sectionBody}>{children}</div>
    </section>
  );
}

function RowLabel({ title, sub }: { title: string; sub?: string }) {
  return (
    <span className={styles.rowLabel}>
      {title}
      {sub ? <span className={styles.rowSub}>{sub}</span> : null}
    </span>
  );
}

function CheckList({ items }: { items: readonly string[] }) {
  return (
    <ul className={styles.checks}>
      {items.map((t) => (
        <li key={t}>
          <span className={styles.checkIcon}>
            <Icon name="dg-i-check-circle" size={17} strokeWidth={2} />
          </span>
          <span>{t}</span>
        </li>
      ))}
    </ul>
  );
}

function Pending({ what }: { what: string }) {
  return (
    <div className={styles.pending}>
      <Icon name="dg-i-info" size={18} strokeWidth={2} />
      <span>
        <strong>화면 작업에서 구현</strong> · {what}
      </span>
    </div>
  );
}

/** 모달 안 대상 카드 — 보드 06 · Main 713 (화면 모달은 T7 이 만든다) */
function TargetCard() {
  return (
    <div className={styles.target}>
      <span className={styles.targetRow}>
        <RiskBadge level="medium" size="xs" />
        <strong className={styles.targetTitle}>계좌번호 · 계좌번호 형식 숫자열</strong>
        <span className={styles.targetId}>F-10</span>
      </span>
      <span className={styles.targetValue}>110-**-****02</span>
    </div>
  );
}

function Swatch({ tone, name, children }: { tone: string; name: string; children: ReactNode }) {
  return (
    <div className={styles.swatch}>
      <span className={cx(styles.chip, styles[tone])} />
      <span className={styles.swatchName}>{name}</span>
      <span className={styles.swatchCode}>{children}</span>
    </div>
  );
}

/**
 * Components.dc.html 보드(01~08)를 실제 컴포넌트로 다시 그린다.
 * 보드의 제목·설명·배치를 따르고, 각 컴포넌트의 상태(올림·로딩·비활성, 기본·입력 중·오류, 펼친 드롭다운 …)를 보여 준다.
 */
export function ComponentsBoard() {
  const toast = useToast();

  /* 02 */
  const [page, setPage] = useState(1);
  const [fit, setFit] = useState(true);

  /* 03 */
  const [nameA, setNameA] = useState('');
  const [nameB, setNameB] = useState('대출상담 서류 묶음');
  const [nameC, setNameC] = useState('');
  const [q, setQ] = useState('');
  const [risk, setRisk] = useState<RiskFilter>('all');
  const [review, setReview] = useState<ReviewFilter>('needed');
  const [riskOpen, setRiskOpen] = useState<RiskFilter>('high');
  const [sort, setSort] = useState<SortKey>('recent');
  const [cat, setCat] = useState<InfoCategory>(AI_CAT);
  const [tab, setTab] = useState<ResultTab>('findings');
  const [chip, setChip] = useState<ChipFilter>('all');
  const [onlyDoc, setOnlyDoc] = useState(false);
  const [mask, setMask] = useState(true);
  const [boardReason, setBoardReason] = useState<FpReason | null>(BOARD_REASONS[0]);

  /* 06 */
  const [fpOpen, setFpOpen] = useState(false);
  const [fpReason, setFpReason] = useState<FpReason | null>(null);
  const [fpNote, setFpNote] = useState('');
  const [fpError, setFpError] = useState('');
  const [busyOpen, setBusyOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [boardNote, setBoardNote] = useState('은행 양식 관리번호로 개인 계좌번호가 아님');

  /* 07 */
  const [count, setCount] = useState(23);
  const [countKey, setCountKey] = useState(0);
  const [replay, setReplay] = useState(0);
  const flip = useReplayToggle(String(replay));

  const openFp = () => {
    setFpReason(null);
    setFpNote('');
    setFpError('');
    setFpOpen(true);
  };
  const submitFp = () => {
    if (!fpReason) return setFpError('오탐으로 판단한 이유를 골라 주세요.');
    if (!fpNote.trim()) return setFpError('상세 사유를 입력해 주세요.');
    setFpOpen(false);
    toast('오탐으로 표시했습니다 · F-10');
  };
  const openBusy = () => {
    setBusy(true);
    setBusyOpen(true);
    window.setTimeout(() => setBusy(false), 2400);
  };

  return (
    <div className={styles.board}>
      <header className={styles.boardHead}>
        <div className={styles.boardIntro}>
          <span className={styles.eyebrow}>
            <Icon name="dg-logo" size={24} className={styles.eyebrowLogo} />
            {CONFIG.brandName} · 디자인 기준
            <span className={styles.devTag}>개발용</span>
          </span>
          <h1 className={styles.h1}>공통 컴포넌트</h1>
          <p className={styles.lead}>
            흰 바탕, 큰 숫자, 채운 버튼과 입력, 카드 대신 구분선과 띠로 나누는 화면. 색은 항상 글자와 아이콘을 함께 붙이고, 움직임은 상태가 바뀐 곳에만 짧게 씁니다.
          </p>
        </div>
        <DemoBadge size="lg" label="데모 데이터 표시" />
      </header>

      {/* ------------------------------------------------------------------ 01 */}
      <Section num="01" id="c1" title="상태 표기 3종" desc="서로 다른 정보는 서로 다른 모양으로 둡니다. 세 값은 각각의 필드로 저장되고, 항상 라벨과 함께 놓습니다.">
        <div className={styles.stack28}>
          <div className={styles.rows}>
            <RowLabel title="위험등급" sub="채운 사각 · 막대 수" />
            <div className={styles.wrap8}>
              {RISK_LEVELS.map((k) => (
                <RiskBadge key={k} level={k} size="md" />
              ))}
              <span className={styles.noteMl}>분석 서비스가 준 값 그대로. 검토 완료나 오탐 표시로 낮아지지 않습니다.</span>
            </div>
            <RowLabel title="분석 상태" sub="배경 없이 아이콘 + 글자" />
            <div className={styles.wrapStatus}>
              {ANALYSIS_KEYS.map((k) => (
                <AnalysisStatusLabel key={k} status={k} size="lg" />
              ))}
              <span className={styles.note}>‘완료’는 안전하다는 뜻이 아니라 중립색. 진행률은 꾸며내지 않습니다.</span>
            </div>
            <RowLabel title="검토 상태" sub="둥근 알약" />
            <div className={styles.wrap8}>
              {REVIEW_KEYS.map((k) => (
                <ReviewStatusPill key={k} status={k} size="md" />
              ))}
              <span className={styles.noteMl}>‘검토 대기’만 어둡게 채워 할 일이 눈에 먼저 들어오게 합니다.</span>
            </div>
            <RowLabel title="탐지 확인 상태" sub="아이콘 + 글자" />
            <div className={styles.wrapStatus}>
              {FINDING_KEYS.map((k) => (
                <FindingStatusLabel key={k} status={k} />
              ))}
            </div>
            <RowLabel title="크기" sub="쓰이는 자리마다" />
            <div className={styles.wrap8}>
              <RiskBadge level="high" size="xs" />
              <RiskBadge level="high" size="sm" />
              <RiskBadge level="high" size="sm" strong />
              <RiskBadge level="high" size="md" />
              <RiskBadge level="high" size="lg" />
              <ReviewStatusPill status="needed" size="xs" />
              <ReviewStatusPill status="needed" size="sm" />
              <ReviewStatusPill status="needed" size="md" />
              <ReviewStatusPill status="needed" size="lg" />
              <AnalysisStatusLabel status="running" size="xs" />
              <AnalysisStatusLabel status="running" size="sm" />
              <AnalysisStatusLabel status="running" size="md" />
              <AnalysisStatusLabel status="done" size="xl" />
            </div>
          </div>
          <div className={styles.together}>
            <span className={styles.togetherTitle}>함께 놓인 모습</span>
            <span className={styles.togetherItem}>
              <span className={styles.togetherLabel}>위험등급</span>
              <RiskBadge level="high" size="md" />
            </span>
            <span className={styles.togetherItem}>
              <span className={styles.togetherLabel}>분석 상태</span>
              <AnalysisStatusLabel status="partial" size="md" strong />
            </span>
            <span className={cx(styles.togetherItem, styles.togetherLast)}>
              <span className={styles.togetherLabel}>검토 상태</span>
              <ReviewStatusPill status="needed" size="md" />
            </span>
          </div>
        </div>
      </Section>

      {/* ------------------------------------------------------------------ 02 */}
      <Section num="02" id="c2" title="버튼" desc="채운 초록 버튼은 그 화면의 다음 행동에만. 나머지는 회색으로 채운 버튼이나 글자 버튼으로 둡니다. 누르면 살짝 줄어듭니다.">
        <div className={cx(styles.rows, styles.rowsButtons)}>
          <RowLabel title="주요" />
          <div className={styles.wrap10}>
            <Button size="xl" icon="dg-i-plus" raised>
              새 분석
            </Button>
            <Button size="lg" icon="dg-i-check-badge">
              검토 완료
            </Button>
            <Button size="lg" className={styles.forceHover}>
              마우스를 올린 상태
            </Button>
            <Button size="lg" loading>
              분석 요청 중…
            </Button>
            <Button size="lg" disabled>
              사용할 수 없음
            </Button>
          </div>
          <RowLabel title="보조" />
          <div className={styles.wrap10}>
            <Button size="lg" variant="secondary" icon="dg-i-report" iconStrokeWidth={2}>
              결과 보고서
            </Button>
            <Button size="lg" variant="soft">
              같은 사람·같은 건 맞음
            </Button>
            <Button size="lg" variant="danger">
              오류 확인
            </Button>
            <Button size="lg" variant="ghost" icon="dg-i-arrow-left">
              글자 버튼
            </Button>
            <Button size="lg" variant="dark" icon="dg-i-folder">
              파일 선택
            </Button>
          </div>
          <RowLabel title="항목 행동" sub="펼친 행 안 · 36px" />
          <div className={styles.itemBox}>
            <Button size="item" icon="dg-i-check">
              탐지 내용 확인
            </Button>
            <Button size="item" variant="outline" icon="dg-i-file">
              원문 확인
            </Button>
            <Button size="item" variant="outline" icon="dg-i-ban">
              오탐으로 표시
            </Button>
            <Button size="item" variant="outline" icon="dg-i-pencil">
              분류 수정
            </Button>
            <Button size="item" variant="ghost" icon="dg-i-memo">
              메모
            </Button>
          </div>
          <RowLabel title="크기" sub="sm · md · lg · xl" />
          <div className={styles.wrap10}>
            <Button size="sm" variant="secondary">
              작게
            </Button>
            <Button size="md" variant="secondary" icon="dg-i-report" iconStrokeWidth={2}>
              기본
            </Button>
            <Button size="md" icon="dg-i-check-badge">
              기본 주요
            </Button>
            <Button size="md" variant="ghost" icon="dg-i-chev-left">
              목록으로
            </Button>
            <Button href="/" size="md" variant="secondary">
              링크 버튼
            </Button>
          </div>
          <RowLabel title="아이콘 · 포커스" />
          <div className={styles.wrap10}>
            <div className={styles.toolbar}>
              <IconButton label="이전 페이지" icon="dg-i-chev-left" size={34} onClick={() => setPage((p) => Math.max(1, p - 1))} />
              <span className={styles.pager}>{page} / 2</span>
              <IconButton label="다음 페이지" icon="dg-i-chev-right" size={34} variant="secondary" onClick={() => setPage((p) => Math.min(2, p + 1))} />
              <span aria-hidden="true" className={styles.toolDivider} />
              <Button size="sm" variant={fit ? 'soft' : 'ghost'} icon="dg-i-fit" aria-pressed={fit} className={styles.fitBtn} onClick={() => setFit((v) => !v)}>
                화면 맞춤
              </Button>
            </div>
            <Button size="lg" variant="secondary" className={styles.forceFocus}>
              키보드 포커스
            </Button>
            <span className={styles.note}>아이콘만 있는 버튼에는 설명과 툴팁을 붙입니다 · 휴대폰에서는 최소 44px</span>
          </div>
        </div>
      </Section>

      {/* ------------------------------------------------------------------ 03 */}
      <Section num="03" id="c3" title="입력과 선택" desc="테두리 없이 회색으로 채운 입력. 누르면 흰색으로 떠오르고, 오류는 붉은 바탕과 문구로 알립니다.">
        <div className={cx(styles.stack26, styles.board03)}>
          <div className={styles.grid3}>
            <TextField label="분석명" value={nameA} onChange={(e) => setNameA(e.target.value)} placeholder="예: 김○○ 대출상담 서류" help="기본" />
            <TextField label="분석명" value={nameB} onChange={(e) => setNameB(e.target.value)} help="입력 중" className={styles.forceFocusField} />
            <TextField
              label="분석명"
              required
              value={nameC}
              onChange={(e) => setNameC(e.target.value)}
              error={nameC.trim() ? undefined : '분석명을 입력해 주세요.'}
              help="입력했습니다"
            />
          </div>
          <div className={styles.wrap8}>
            <SearchField value={q} onChange={(e) => setQ(e.target.value)} className={styles.search} />
            <Dropdown variant="filter" title="위험등급" value={risk} options={RISK_OPTIONS} onChange={setRisk} />
            <Dropdown variant="filter" title="검토 상태" value={review} options={REVIEW_OPTIONS} onChange={setReview} />
            <span className={styles.noteMl8}>필터가 걸리면 초록으로 바뀝니다</span>
          </div>
          <div className={styles.grid2}>
            <div className={styles.cell}>
              <span className={styles.cap}>세그먼트 탭 · 흰 판이 미끄러져 이동</span>
              <SegmentedTabs
                ariaLabel="결과 구분"
                value={tab}
                onChange={setTab}
                className={styles.max420}
                tabs={[
                  { value: 'findings', label: '탐지 항목', count: 23 },
                  { value: 'review', label: '검토사항', count: 5, tone: 'warn' },
                  { value: 'links', label: '문서 간 연결', count: 3 },
                ]}
              />
            </div>
            <div className={styles.cell}>
              <span className={styles.cap}>필터 칩 · 선택하면 어둡게</span>
              <FilterChips
                ariaLabel="탐지 항목 필터"
                value={chip}
                onChange={setChip}
                chips={[
                  { value: 'all', label: '전체', count: 23 },
                  { value: 'open', label: FSTATUS.open.label, count: 20 },
                  { value: 'high', label: RISK.high.label, count: 3 },
                  { value: 'medium', label: RISK.medium.label, count: 11 },
                ]}
              />
            </div>
            <div className={styles.cell}>
              <span className={styles.cap}>스위치</span>
              <div className={styles.switches}>
                <Switch checked={onlyDoc} onChange={setOnlyDoc} label="현재 문서만 보기" />
                <Switch checked={mask} onChange={setMask} label="마스킹 미리보기" />
              </div>
            </div>
            <div className={styles.cell}>
              <span className={styles.cap}>선택 목록 · 모달 안의 사유 선택</span>
              <RadioList
                legend="오탐으로 판단한 이유"
                legendHidden
                options={BOARD_REASONS.map((r) => ({ value: r, label: r }))}
                value={boardReason}
                onChange={setBoardReason}
                className={styles.max420}
              />
            </div>
          </div>
          <div className={styles.ddDemo}>
            <span className={styles.cap}>드롭다운 · 펼친 상태</span>
            <div className={styles.ddRow}>
              <div className={styles.ddOpenSlot}>
                <Dropdown variant="filter" title="위험등급" value={riskOpen} options={RISK_OPTIONS} onChange={setRiskOpen} defaultOpen />
              </div>
              <CheckList
                items={[
                  '브라우저 기본 목록 대신 같은 디자인의 메뉴를 씁니다. 버튼 아래로 살짝 내려오며 열리고 화살표가 뒤집힙니다.',
                  '항목마다 상태 아이콘과 해당 건수를 함께 보여 주고, 고른 항목은 초록 체크로 표시합니다.',
                  '바깥을 누르거나 Esc로 닫히고, 키보드 화살표 · Home · End로 이동해 Enter로 고릅니다.',
                  '분류 수정 창의 드롭다운은 최초 AI 값에 ‘최초 AI’ 표시를 붙여, 무엇을 바꾸는지 알 수 있게 합니다.',
                ]}
              />
            </div>
            <div className={styles.ddMore}>
              <div className={styles.cell}>
                <span className={styles.cap}>정렬 · 바탕 없는 트리거</span>
                <Dropdown variant="sort" title="정렬" value={sort} options={SORT_OPTIONS} onChange={setSort} />
              </div>
              <div className={cx(styles.cell, styles.fieldCell)}>
                <span id="dg-dev-cat-l" className={styles.fieldLabel}>
                  정보 종류
                </span>
                <Dropdown variant="field" title="정보 종류" labelledBy="dg-dev-cat-l" value={cat} options={CAT_OPTIONS} onChange={setCat} changed={cat !== AI_CAT} />
              </div>
            </div>
          </div>
        </div>
      </Section>

      {/* ------------------------------------------------------------------ 04 */}
      <Section num="04" id="c4" title="목록 행" desc="테두리 상자 대신 구분선으로 이어지는 행. 왼쪽 타일 색은 위험등급을 따르고, 눌러서 펼치면 같은 자리에서 근거와 행동이 열립니다.">
        <Pending what="분석 목록 행은 목록 화면(T4), 탐지 항목 행은 상세 결과 패널(T6)에서 만듭니다." />
      </Section>

      {/* ------------------------------------------------------------------ 05 */}
      <Section num="05" id="c5" title="원문 하이라이트" desc="평소엔 위험 색 밑줄, 고르면 테두리와 이름표. 선택한 순간 테두리 밖으로 두 번 퍼지는 신호로 위치를 알려 줍니다.">
        <Pending what="원문 뷰어와 하이라이트는 상세 검토 화면(T6)에서 만듭니다." />
      </Section>

      {/* ------------------------------------------------------------------ 06 */}
      <Section num="06" id="c6" title="알림과 진행" desc="화면 위 띠, 아래 토스트, 모달. 진행률을 모르면 숫자 대신 흐르는 막대로 진행 중임만 알립니다.">
        <div className={styles.grid2top}>
          <div className={styles.stack12}>
            <Banner shape="card" variant="running" title="분석 중입니다 · 문서 3개 중 1개 완료" description="정확한 진행률은 표시하지 않습니다." />
            <Banner shape="card" variant="partial" title="문서 3개 중 1개를 분석하지 못했습니다." description="이미 찾은 상 등급 정보는 그대로 둡니다." />
            <Banner shape="card" variant="done" title={`검토 완료 · ${CONFIG.user.name} · 2026.10.29 09:12`} description="위험등급과 최초 결과는 유지됩니다." />
            <Banner
              shape="card"
              variant="failed"
              title="분석에 실패했습니다."
              description="같은 파일로 다시 시도하거나 원본을 다시 올려 주세요."
              actions={[{ label: '다시 시도', onClick: () => toast('다시 분석했지만 실패했습니다 · 파일을 읽지 못했습니다', { kind: 'error' }) }]}
            />
            <Banner shape="card" variant="info" icon="dg-i-clock" title="분석 대기 중입니다." description="접수 순서에 따라 곧 분석이 시작됩니다." />
            <SkeletonCard label="뼈대 화면 · 원문 준비 중" />
            <Toast
              floating={false}
              text="검토를 완료했습니다"
              action={{ label: '보고서 보기', onClick: () => toast('보고서 화면은 뒤 작업(T8)에서 연결합니다') }}
              className={styles.selfStart}
            />
            <div className={styles.wrap8}>
              <Button size="sm" variant="secondary" onClick={() => toast('탐지 내용을 확인했습니다 · F-03')}>
                토스트 띄우기
              </Button>
              <Button size="sm" variant="secondary" onClick={() => toast('다시 분석했지만 실패했습니다 · 파일을 읽지 못했습니다', { kind: 'error' })}>
                오류 토스트
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={() =>
                  toast('분석이 끝났습니다 · 대출상담 서류 묶음 — 탐지 23건, 검토사항 5건', {
                    action: { label: '결과 보기', onClick: () => toast('결과 화면은 뒤 작업(T6)에서 연결합니다') },
                  })
                }
              >
                행동 버튼이 있는 토스트
              </Button>
            </div>
            <div className={styles.progressRow}>
              <span className={styles.progressItem}>
                <Spinner size={14} />
                <Spinner size={16} />
                <Spinner size={22} />
              </span>
              <span className={styles.progressItem}>
                올리는 중
                <IndeterminateBar variant="track" size="sm" tone="accent" />
              </span>
              <span className={cx(styles.progressItem, styles.progressWide)}>
                <IndeterminateBar variant="track" size="md" tone="run" />
              </span>
            </div>
          </div>
          <div className={styles.stack12}>
            <Modal
              inline
              open
              title="오탐으로 표시"
              subtitle="개인정보 · 중요정보가 아니라고 판단한 이유를 남깁니다."
              onClose={() => toast('견본 모달입니다 · 아래 ‘모달 열기’로 실제 모달을 엽니다')}
              buttons={[
                { label: '취소', variant: 'secondary', onClick: () => undefined },
                { label: '오탐으로 표시', variant: 'primary', onClick: () => undefined },
              ]}
            >
              <TargetCard />
              <TextField
                label="상세 사유"
                labelNote="(필수 · 검토 이력에 남습니다)"
                multiline
                rows={2}
                value={boardNote}
                onChange={(e) => setBoardNote(e.target.value)}
              />
            </Modal>
            <span className={styles.modalCaption}>모달은 아래에서 살짝 떠오르고, 휴대폰에서는 아래에서 올라오는 시트가 됩니다.</span>
            <div className={styles.wrap8}>
              <Button size="md" onClick={openFp}>
                모달 열기
              </Button>
              <Button size="md" variant="secondary" onClick={openBusy}>
                닫을 수 없는 상태
              </Button>
            </div>
          </div>
        </div>
      </Section>

      {/* ------------------------------------------------------------------ 07 */}
      <Section num="07" id="c7" title="움직임" desc="빨리 시작해 부드럽게 멈추는 곡선 하나로 통일합니다. 시스템에서 ‘동작 줄이기’를 켜면 모든 움직임이 즉시 끝납니다.">
        <div className={styles.stack20}>
          <div className={styles.motionBand}>
            <span className={styles.curve}>cubic-bezier(.2, .8, .2, 1)</span>
            <span className={styles.motionText}>누름 0.12초 · 색 변화 0.15–0.25초 · 등장 0.3–0.45초 · 숫자 0.7–1.1초</span>
            <span className={styles.countWrap} data-testid="countup">
              <CountUp key={countKey} value={count} className={styles.count34} />
              <span className={styles.countUnit}>건</span>
            </span>
          </div>
          <div className={styles.wrap8}>
            <Button size="sm" variant="secondary" onClick={() => setCount((c) => (c === 23 ? 17 : 23))}>
              값 바꾸기 (검토 후 이어서 변함)
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setCountKey((k) => k + 1)}>
              0부터 다시 세기
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setReplay((r) => r + 1)}>
              목록 차례 등장 다시 보기
            </Button>
          </div>
          <ol className={styles.stagger} aria-label="차례 등장 견본">
            {['개인여신거래신청서', '소득금액증명원', '급여명세서', '주민등록등본', '통장 사본'].map((t, i) => (
              <li key={t} className={flip ? styles.rowInB : styles.rowIn} style={staggerStyle(i)}>
                <span className={styles.staggerIdx}>{i + 1}</span>
                {t}
              </li>
            ))}
          </ol>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">어디서</th>
                  <th scope="col">어떻게 움직이나</th>
                  <th scope="col">왜</th>
                </tr>
              </thead>
              <tbody>
                {MOTION_ROWS.map(([a, b, c]) => (
                  <tr key={a}>
                    <td>{a}</td>
                    <td>{b}</td>
                    <td>{c}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Section>

      {/* ------------------------------------------------------------------ 08 */}
      <Section num="08" id="c8" title="색과 글꼴" desc="흰 바탕에 짙은 남색 글자, 초록 하나. 위험 색은 표기에만 씁니다. 글자와 배경 대비는 4.5:1 이상(사용할 수 없는 버튼 제외)." last>
        <div className={styles.stack28}>
          <div className={styles.swatches}>
            <Swatch tone="cInk" name="본문 남색">
              #141B2D
            </Swatch>
            <Swatch tone="cInk3" name="보조 글자">
              #636B7A
            </Swatch>
            <Swatch tone="cFill" name="채움 회색">
              #F2F4F6
            </Swatch>
            <Swatch tone="cAccent" name="초록 (주요 행동)">
              #00845C · 흰 글자 4.7:1
            </Swatch>
            <Swatch tone="cAccentSoft" name="초록 옅게">
              선택 · 완료 바탕
            </Swatch>
            <Swatch tone="cDemo" name="데모 표시">
              #FFF5D6 / #6E4E00
            </Swatch>
            <Swatch tone="cHi" name={RISK.high.label}>
              글자 #C9271C
            </Swatch>
            <Swatch tone="cMd" name={`${RISK.medium.label} · 주의`}>
              글자 #A84D00
            </Swatch>
            <Swatch tone="cLo" name={`${RISK.low.label} · 진행`}>
              글자 #2457C5
            </Swatch>
            <Swatch tone="cNa" name={RISK.unrated.label}>
              글자 #56606F
            </Swatch>
            <Swatch tone="cLine" name="구분선 · 원문 바탕">
              #EEF0F3
            </Swatch>
            <Swatch tone="cBg" name="바탕">
              #FFFFFF
            </Swatch>
          </div>
          <div className={styles.typeScale}>
            <span className={styles.typeLabel}>숫자 34 · 800</span>
            <span className={styles.tNum}>23건</span>
            <span className={styles.typeLabel}>화면 제목 30 · 800</span>
            <span className={styles.tTitle}>문서 분석</span>
            <span className={styles.typeLabel}>구역 20 · 800</span>
            <span className={styles.tSection}>주요 위험 사유</span>
            <span className={styles.typeLabel}>본문 15 · 400</span>
            <span className={styles.tBody}>원문 위치와 탐지 항목이 서로 연결됩니다.</span>
            <span className={styles.typeLabel}>보조 13 · 400</span>
            <span className={styles.tSub}>개인 여신거래 신청서 · 1쪽 · 전체 노출</span>
            <span className={styles.typeLabel}>고정폭 13</span>
            <span className={styles.tMono}>PII-ID-001 · 920314-2******</span>
          </div>
          <span className={styles.note13}>한글은 Pretendard, 규칙 ID · 마스킹 값 · 분석 ID는 IBM Plex Mono.</span>
        </div>
      </Section>

      {/* 실제 모달 — 오탐 표시(사유 선택 + 상세 사유) */}
      <Modal
        open={fpOpen}
        onClose={() => setFpOpen(false)}
        title="오탐으로 표시"
        subtitle="이 탐지 결과가 개인정보 · 중요정보가 아니라고 판단한 이유를 남깁니다."
        buttons={[
          { label: '취소', variant: 'secondary', onClick: () => setFpOpen(false) },
          { label: '오탐으로 표시', variant: 'primary', onClick: submitFp },
        ]}
      >
        <TargetCard />
        <RadioList
          legend="오탐으로 판단한 이유"
          options={FP_REASONS.map((r) => ({ value: r, label: r }))}
          value={fpReason}
          onChange={(r) => {
            setFpReason(r);
            setFpError('');
          }}
        />
        <TextField
          label="상세 사유"
          labelNote="(필수 · 검토 이력에 남습니다)"
          multiline
          rows={3}
          maxLength={500}
          showCount
          autoFocus
          placeholder="예: 은행 양식 관리번호로 개인 계좌번호가 아님"
          value={fpNote}
          onChange={(e) => {
            setFpNote(e.target.value);
            setFpError('');
          }}
          invalid={!!fpError}
        />
        <p className={styles.modalInfo}>오탐으로 표시해도 최초 AI 결과와 위험등급은 기록에 그대로 남습니다.</p>
        {fpError ? (
          <p role="alert" className={styles.modalError}>
            <Icon name="dg-i-alert" size={16} strokeWidth={2.1} />
            {fpError}
          </p>
        ) : null}
      </Modal>

      {/* 닫을 수 없는 상태 — 작업이 끝날 때까지 Esc·배경·닫기 버튼이 막힌다 */}
      <Modal
        open={busyOpen}
        onClose={() => setBusyOpen(false)}
        dismissible={!busy}
        width="md"
        title="결과 내보내기"
        subtitle="작업 중에는 닫을 수 없습니다. 2.4초 뒤 끝납니다."
        buttons={[
          { label: '닫기', variant: 'ghost', onClick: () => setBusyOpen(false), disabled: busy },
          { label: busy ? '만드는 중…' : '다시 내보내기', variant: 'primary', loading: busy, autoFocus: true, onClick: openBusy },
        ]}
      >
        <Banner shape="card" variant={busy ? 'running' : 'done'} title={busy ? '파일을 만들고 저장을 요청하고 있습니다…' : '내보내기 완료'} />
      </Modal>
    </div>
  );
}
