export interface DiffPart {
  type: "same" | "del" | "ins";
  text: string;
}

function diffSeq(ta: string[], tb: string[]): DiffPart[] {
  const n = ta.length;
  const m = tb.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = ta[i] === tb[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const parts: DiffPart[] = [];
  const push = (type: DiffPart["type"], text: string) => {
    const last = parts[parts.length - 1];
    if (last && last.type === type) last.text += text;
    else parts.push({ type, text });
  };
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (ta[i] === tb[j]) {
      push("same", ta[i]);
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      push("del", ta[i]);
      i++;
    } else {
      push("ins", tb[j]);
      j++;
    }
  }
  while (i < n) push("del", ta[i++]);
  while (j < m) push("ins", tb[j++]);
  return parts;
}

/** Word-level diff (LCS). Used only to mark changed words inside an already-aligned clause. */
export function diffWords(a: string, b: string): DiffPart[] {
  return diffSeq(a.split(/(\s+)/).filter(Boolean), b.split(/(\s+)/).filter(Boolean));
}

/**
 * Finer diff for tracked-change previews: words, whitespace and punctuation are separate tokens, and so are
 * digit runs. "AED 100,000" -> "AED 1,000,000" shows 100 struck, 1 added and ",000" added, not the whole number.
 */
export function diffTokens(a: string, b: string): DiffPart[] {
  const tokenize = (t: string) => t.match(/\d+|[\p{L}\p{M}]+|\s+|[^\s\d\p{L}\p{M}]/gu) ?? [];
  return diffSeq(tokenize(a), tokenize(b));
}
