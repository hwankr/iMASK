/* ==========================================================================
   그림 PDF 작성기 — 쪽마다 JPEG 한 장을 쪽 전체에 그린 PDF 를 바이트로 만든다. 순수 함수(브라우저 · Node 공통). 테스트 대상.
   - 쓰임: 실제 분석 '가린 PDF 내려받기'(src/components/detail/maskPdfBuild.ts) — 가린 쪽 그림만 담는다.
     글자 · 글꼴 · 주석 · 폼 · 첨부 · 메타데이터(/Info)를 넣지 않는다. 쪽 내용은 그림을 MediaBox 전체에 그리는 것뿐이다.
   - 구조: 머리 `%PDF-1.4`(UserUnit 을 쓴 쪽이 있으면 `%PDF-1.6`) + 이진 주석 줄, 1 Catalog · 2 Pages, 쪽마다 Page · 내용 스트림 · Image XObject
     (`/Filter /DCTDecode /ColorSpace /DeviceRGB /BitsPerComponent 8`), xref(정확한 바이트 오프셋, 한 줄 20바이트) ·
     trailer(`/Size /Root`) · `startxref` · `%%EOF`.
   - 바이트는 Uint8Array 조각을 이어 붙인다(글자는 모두 ASCII — 문자열 인코딩 사고가 없게). 숫자는 유한한 값만, 소수 셋째 자리까지.
   - 쪽 크기는 '보이는 크기'(pt)를 그대로 지킨다(pageGeometry): 한 변이 MAX_PAGE_PT(14400pt = 200 인치 — PDF 의 보통 쪽 한도)를
     넘으면 쪽에 `/UserUnit u`(PDF 1.6, u > 1 — 소수 셋째 자리, 올림)를 쓰고 MediaBox 를 보이는 크기 ÷ u(각 변 14400 이하)로 적는다.
     MediaBox × u 는 보이는 크기와 0.0005 × u pt 안에서 같다(u ≤ MAX_USER_UNIT 이면 0.05pt 이하). 14400 이하 쪽은 UserUnit 이 없다.
     3pt 미만 아주 작은 쪽도 그대로 적는다(크기를 지킨다 — pdf.js · Chrome 은 그 크기로 연다. 3pt 는 PDF 부록의 구현 한도 권고).
   - 잘못된 입력(0쪽 · 유한하지 않거나 0 이하인 쪽 크기 · 반올림하면 0 인 쪽 · u 가 MAX_USER_UNIT 을 넘는 터무니없이 큰 쪽 ·
     정수가 아닌 픽셀 크기 · 빈 JPEG · JPEG 머리 없음)은 고정 문구 Error 를 던진다(입력 내용을 문구에 담지 않음 —
     크기를 바꾼 파일을 내놓지 않는다).
   ========================================================================== */

/** 쪽 하나 — 보이는 쪽 크기(pt)와 그 쪽 전체에 그릴 JPEG */
export interface ImagePdfPage {
  /** 보이는 쪽 폭(pt, 1pt = 1/72 인치) — 14400 이하면 MediaBox 그대로, 넘으면 MediaBox × UserUnit */
  width: number;
  /** 보이는 쪽 높이(pt) */
  height: number;
  /** JPEG 바이트(RGB — 캔버스 toBlob('image/jpeg') 결과) */
  jpeg: Uint8Array;
  /** JPEG 픽셀 폭 */
  pixelWidth: number;
  /** JPEG 픽셀 높이 */
  pixelHeight: number;
}

/** 잘못된 입력 — 고정 문구 */
export const IMAGE_PDF_INVALID = '그림 PDF 를 만들 수 없는 입력입니다.';

/** MediaBox 한 변의 최대 크기(기본 사용자 공간 단위) — PDF 의 보통 쪽 한도(200 인치). 넘는 쪽은 UserUnit 으로 적는다 */
export const MAX_PAGE_PT = 14400;

/**
 * UserUnit 상한 — 보이는 쪽 한 변 최대 1,440,000pt(약 508m). 실제 서류 · 도면보다 훨씬 크고(대형 도면도 수십 m),
 * 이 안에서는 MediaBox 소수 셋째 자리 반올림 오차(0.0005 × u)가 0.05pt 이하라 '보이는 크기 ±1pt'를 넉넉히 지킨다.
 * 넘으면 잘못된 입력(전체 실패) — 크기를 줄인 파일을 내놓지 않는다.
 */
export const MAX_USER_UNIT = 100;

/** JPEG 픽셀 한 변의 최대 크기 — JPEG 형식 한도 */
const MAX_JPEG_SIDE = 65535;

const ascii = (s: string): Uint8Array => {
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i) & 0x7f;
  return out;
};

/** PDF 숫자 — 유한한 값만, 소수 셋째 자리까지(뒤 0 없음, 지수 표기 없음) */
export function pdfNum(v: number): string {
  if (!Number.isFinite(v)) throw new Error(IMAGE_PDF_INVALID);
  const r = Math.round(v * 1000) / 1000;
  if (Object.is(r, -0) || r === 0) return '0';
  const s = r.toFixed(3).replace(/\.?0+$/, '');
  return s;
}

/** 쪽 하나의 PDF 크기 — MediaBox 의 두 변(PDF 숫자)과 UserUnit(없으면 null) */
export interface PageGeometry {
  mediaWidth: string;
  mediaHeight: string;
  userUnit: string | null;
}

/**
 * 보이는 쪽 크기(pt) → MediaBox · UserUnit. 반올림한 두 변이 MAX_PAGE_PT 이하면 UserUnit 없이 그대로,
 * 넘으면 u = 올림(긴 변 ÷ 14400, 소수 셋째 자리)과 MediaBox = 보이는 크기 ÷ u(14400 이하로 자름).
 * 유한하지 않거나 0 이하 · 반올림하면 0 · u 가 MAX_USER_UNIT 을 넘으면 IMAGE_PDF_INVALID.
 */
export function pageGeometry(width: number, height: number): PageGeometry {
  const ok = (v: number) => typeof v === 'number' && Number.isFinite(v) && v > 0;
  if (!ok(width) || !ok(height)) throw new Error(IMAGE_PDF_INVALID);
  const round = (v: number) => Math.round(v * 1000) / 1000;
  if (Math.max(round(width), round(height)) <= MAX_PAGE_PT) {
    // 아주 작은 쪽은 반올림하면 0 이 될 수 있다 — 넓이 0 인 MediaBox 는 쓰지 않는다
    if (round(width) <= 0 || round(height) <= 0) throw new Error(IMAGE_PDF_INVALID);
    return { mediaWidth: pdfNum(width), mediaHeight: pdfNum(height), userUnit: null };
  }
  // 올림이라 긴 변 ÷ u ≤ 14400(소수 셋째 자리 u 는 PDF 숫자로 정확히 적힌다)
  const u = Math.ceil((Math.max(width, height) / MAX_PAGE_PT) * 1000) / 1000;
  if (!(u > 1) || u > MAX_USER_UNIT) throw new Error(IMAGE_PDF_INVALID);
  const side = (v: number): string => {
    const m = Math.min(MAX_PAGE_PT, v / u);
    if (round(m) <= 0) throw new Error(IMAGE_PDF_INVALID);
    return pdfNum(m);
  };
  return { mediaWidth: side(width), mediaHeight: side(height), userUnit: pdfNum(u) };
}

function validPage(p: ImagePdfPage | null | undefined): p is ImagePdfPage {
  if (!p) return false;
  const pxOk = (v: number) => Number.isInteger(v) && v > 0 && v <= MAX_JPEG_SIDE;
  if (!pxOk(p.pixelWidth) || !pxOk(p.pixelHeight)) return false;
  try {
    pageGeometry(p.width, p.height);
  } catch {
    return false;
  }
  // JPEG 머리(SOI = FF D8)가 있어야 한다 — 빈 바이트 · 다른 형식은 받지 않는다
  return p.jpeg instanceof Uint8Array && p.jpeg.length >= 2 && p.jpeg[0] === 0xff && p.jpeg[1] === 0xd8;
}

/**
 * 쪽들(원래 순서)을 그림 PDF 바이트로 만든다. 쪽이 없거나 잘못된 쪽이 하나라도 있으면 IMAGE_PDF_INVALID 를 던진다.
 */
export function buildImagePdf(pages: readonly ImagePdfPage[]): Uint8Array {
  if (!Array.isArray(pages) || pages.length === 0 || !pages.every(validPage)) throw new Error(IMAGE_PDF_INVALID);

  const chunks: Uint8Array[] = [];
  let length = 0;
  const put = (b: Uint8Array) => {
    chunks.push(b);
    length += b.length;
  };
  const text = (s: string) => put(ascii(s));

  // 객체 번호: 1 Catalog · 2 Pages · 쪽 i(0부터) = Page 3+3i · 내용 4+3i · 그림 5+3i
  const pageObj = (i: number) => 3 + 3 * i;
  const objCount = 2 + 3 * pages.length;
  const offsets: number[] = new Array(objCount + 1).fill(0);
  const begin = (n: number) => {
    offsets[n] = length;
    text(`${n} 0 obj\n`);
  };
  const end = () => text('endobj\n');

  const geometry = pages.map((p) => pageGeometry(p.width, p.height));
  // 머리 + 이진 주석 줄(128 이상 바이트 넷 — 전송 도구가 이진 파일로 다루게). UserUnit(PDF 1.6)을 쓴 쪽이 있으면 1.6
  text(geometry.some((g) => g.userUnit !== null) ? '%PDF-1.6\n' : '%PDF-1.4\n');
  put(new Uint8Array([0x25, 0xe2, 0xe3, 0xcf, 0xd3, 0x0a]));

  begin(1);
  text('<< /Type /Catalog /Pages 2 0 R >>\n');
  end();

  begin(2);
  text(`<< /Type /Pages /Kids [${pages.map((_, i) => `${pageObj(i)} 0 R`).join(' ')}] /Count ${pages.length} >>\n`);
  end();

  pages.forEach((p, i) => {
    const { mediaWidth: w, mediaHeight: h, userUnit } = geometry[i];
    // 그림은 MediaBox 전체(사용자 공간 단위 — UserUnit 이 있으면 그 배수 크기로 보인다)
    const content = ascii(`q\n${w} 0 0 ${h} 0 0 cm\n/Im0 Do\nQ\n`);
    const unit = userUnit === null ? '' : ` /UserUnit ${userUnit}`;

    begin(pageObj(i));
    text(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${w} ${h}]${unit} /Resources << /XObject << /Im0 ${pageObj(i) + 2} 0 R >> >> /Contents ${pageObj(i) + 1} 0 R >>\n`);
    end();

    begin(pageObj(i) + 1);
    text(`<< /Length ${content.length} >>\nstream\n`);
    put(content);
    text('\nendstream\n');
    end();

    begin(pageObj(i) + 2);
    text(
      `<< /Type /XObject /Subtype /Image /Width ${p.pixelWidth} /Height ${p.pixelHeight} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${p.jpeg.length} >>\nstream\n`,
    );
    put(p.jpeg);
    text('\nendstream\n');
    end();
  });

  // xref — 한 줄 정확히 20바이트(10자리 오프셋 · 5자리 세대 · 'n'/'f' · 공백 + LF)
  const xref = length;
  let table = `xref\n0 ${objCount + 1}\n0000000000 65535 f \n`;
  for (let n = 1; n <= objCount; n++) table += `${String(offsets[n]).padStart(10, '0')} 00000 n \n`;
  text(table);
  text(`trailer\n<< /Size ${objCount + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`);

  const out = new Uint8Array(length);
  let at = 0;
  for (const c of chunks) {
    out.set(c, at);
    at += c.length;
  }
  return out;
}
