// 목 데이터용 한국어 더미 문장 — 실제 책 본문을 흉내낸 문단들과
// OCR에서 흔히 섞여 들어오는 꼬리말(페이지 번호·책 제목) 패턴.

export const BOOK_TITLE = "고요한 계절";

export const SAMPLE_PARAGRAPHS: string[] = [
  "그해 겨울은 유난히 길었다. 마당의 감나무는 잎을 다 떨구고도 한참을 그대로 서 있었고, 할머니는 매일 아침 마루에 앉아 먼 산을 바라보곤 했다.",
  "나는 그 침묵이 무엇을 뜻하는지 오래도록 알지 못했다. 다만 그 곁에 앉아 있으면 이상하게 마음이 놓였다.",
  "봄이 오자 마을 전체가 다시 움직이기 시작했다. 냇가에는 물이 불어났고, 아이들은 신발을 벗어 던지고 첨벙거리며 뛰어다녔다.",
  "아버지는 그 무렵 도시로 나가 일을 구했다. 편지는 한 달에 한 번, 늘 같은 문장으로 끝났다. \"모두 건강히 지내라.\"",
  "우리는 그 문장을 몇 번이고 되뇌었다. 짧은 문장이었지만, 그 안에는 말하지 않은 것들이 훨씬 더 많이 담겨 있었다.",
  "여름이 되자 매미 소리가 온 동네를 뒤덮었다. 나는 평상에 누워 그 소리를 들으며 잠들곤 했다.",
  "할머니는 가끔 옛날이야기를 들려주었다. 전쟁 통에 겪은 일들, 그리고 그 안에서도 살아남은 사람들의 이야기였다.",
  "그 이야기들은 늘 끝이 흐릿했다. 마치 결말을 말하고 싶지 않다는 듯이, 할머니는 항상 중간에서 말을 멈추었다.",
  "가을이 깊어지면서 감나무에 다시 열매가 맺혔다. 붉게 익은 감을 따며 나는 처음으로 시간이 흐른다는 것을 실감했다.",
  "그리고 다시 겨울이 왔다. 모든 것이 제자리로 돌아온 듯했지만, 나는 이미 예전의 내가 아니었다.",
  "떠나기 전날 밤, 나는 마당에 나가 오래도록 감나무를 올려다보았다. 다음에 돌아올 때는 무엇이 달라져 있을지 알 수 없었다.",
  "기차역까지 배웅 나온 할머니는 아무 말도 하지 않았다. 그저 손을 흔들 뿐이었다. 그 손짓이 오래도록 기억에 남았다.",
];

// OCR 결과에 흔히 섞여 들어오는 꼬리말 패턴 (페이지 번호, 책 제목 등)
export const FOOTER_PATTERNS = [
  (page: number) => `- ${page} -`,
  (page: number) => `${BOOK_TITLE}  ${page}`,
  (_page: number) => `${BOOK_TITLE}`,
  (page: number) => `${page}페이지`,
];

export function makeParagraph(seed: number): string {
  return SAMPLE_PARAGRAPHS[seed % SAMPLE_PARAGRAPHS.length];
}

export function makeCorrectedParagraph(original: string): string {
  // 목적: 흔한 OCR 오탈자/띄어쓰기를 교정한 것처럼 보이는 사소한 변형
  return original
    .replace(/ㅡ/g, "-")
    .replace(/떄/g, "때")
    .replace(/됬/g, "됐")
    .replace(/  +/g, " ");
}

export function makePageText(pageNumber: number): string {
  const footer = FOOTER_PATTERNS[pageNumber % FOOTER_PATTERNS.length](pageNumber);
  const para1 = makeParagraph(pageNumber);
  const para2 = makeParagraph(pageNumber + 3);
  return `${para1}\n\n${para2}\n\n${footer}`;
}
