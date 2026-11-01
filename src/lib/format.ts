/* 형식 도우미 — 프로토타입 공통 도우미(Main.dc.html 834–841줄) 그대로. */

/** 두 자리로 채운다. 7 → '07' */
export function pad2(n: number | string): string {
  return String(n).padStart(2, '0');
}

/** 지금 시각 'YYYY-MM-DD HH:mm' */
export function nowStr(date: Date = new Date()): string {
  const d = date;
  return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()) + ' ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes());
}

/** 'YYYY-MM-DD HH:mm…' → 'YYYY.MM.DD HH:mm'. 값이 없으면 '-' */
export function fmtDT(s: string | null | undefined): string {
  return s ? String(s).slice(0, 16).replace(/-/g, '.') : '-';
}

/** 바이트 → '412KB' · '1.2MB'. 1MB 미만은 KB(최소 1KB). 값이 없으면 '-' */
export function fmtSize(b: number | null | undefined): string {
  if (b == null) return '-';
  if (b < 1048576) return Math.max(1, Math.round(b / 1024)) + 'KB';
  return (b / 1048576).toFixed(1) + 'MB';
}

/** n 을 a 이상 b 이하로 자른다 */
export function clamp(n: number, a: number, b: number): number {
  return Math.max(a, Math.min(b, n));
}

/** 문자열의 UTF-8 바이트 수 */
export function utf8Len(s: string): number {
  try {
    return new TextEncoder().encode(s).length;
  } catch {
    return String(s).length;
  }
}
