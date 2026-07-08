// 페이지 파일명 마지막 숫자를 기준으로 자연 정렬한다.
// 예: page-2.jpg < page-10.jpg (문자열 정렬로는 반대 순서가 됨)
export function lastNumber(filename: string): number {
  const match = filename.match(/(\d+)(?!.*\d)/);
  return match ? parseInt(match[1], 10) : Number.MAX_SAFE_INTEGER;
}

export function naturalSortByFilename<T extends { filename: string }>(
  items: T[]
): T[] {
  return [...items].sort((a, b) => lastNumber(a.filename) - lastNumber(b.filename));
}
