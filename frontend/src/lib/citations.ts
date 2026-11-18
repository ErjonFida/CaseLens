/**
 * The chat stream is plain markdown, so a source arrives only as text like
 * "(*Scoutcam Services Agreement.pdf*, Page 1)". Only the user's own filenames
 * are matched, so prose that merely mentions a page is left alone.
 */

export interface Citation {
  filename: string;
  page: number;
  /** The text the citation supports: its sentence, up to the citation. */
  claim: string;
}

const escapeRegExp = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const stem = (filename: string) => filename.replace(/\.[^.]+$/, '');
// encodeURIComponent leaves parentheses alone, and either one would end the
// markdown link early.
const encode = (s: string) => encodeURIComponent(s).replace(/\(/g, '%28').replace(/\)/g, '%29');

/** The sentence before `end`, without markdown emphasis or an unclosed "(". */
function claimBefore(text: string, end: number): string {
  let s = text.slice(0, end).split('\n').pop()!;
  s = s.split(/(?<=[.!?])\s+(?=["“(A-Z])/).pop()!;
  const open = s.lastIndexOf('(');
  if (open > s.lastIndexOf(')')) s = s.slice(0, open);
  return s.replace(/[*_]/g, '').replace(/^\s*(?:[-+]|\d+\.)\s+/, '').trim().slice(-300);
}

export function linkCitations(markdown: string, documents: string[]): string {
  if (documents.length === 0) return markdown;
  const byStem = new Map(documents.map((d) => [stem(d).toLowerCase(), d]));
  const names = [...byStem.keys()].sort((a, b) => b.length - a.length).map(escapeRegExp).join('|');
  // The name, maybe with its extension, then the page: "Page 3", "page 3",
  // "pages 3-4", "p. 3". Italics or bold may wrap the name or the whole cite.
  const cite = new RegExp(
    `[*_]{0,2}(${names})(?:\\.[a-z0-9]{2,4})?[*_]{0,2}\\s*,?\\s*(?:pages?|pp?\\.)\\s*(\\d+)[*_]{0,2}`,
    'gi'
  );
  const linked = markdown.replace(cite, (_match, name: string, page: string, offset: number, whole: string) => {
    const filename = byStem.get(name.toLowerCase())!;
    const href = `cite:${encode(filename)}/${page}?${encode(claimBefore(whole, offset))}`;
    return `[${stem(filename)} · p. ${page}](${href})`;
  });
  // "(chip)", "(chip; chip)" and "(Source: chip)" read better as bare chips.
  const chip = String.raw`\[[^\]]*\]\(cite:[^)]*\)`;
  const label = String.raw`(?:[*_]{0,2}(?:sources?|see)\s*:?\s*)?`;
  return linked.replace(new RegExp(String.raw`\(\s*${label}(${chip}(?:[\s,;]+${chip})*)\s*\)`, 'gi'), '$1');
}

export function parseCitation(href: string): Citation | null {
  if (!href.startsWith('cite:')) return null;
  const [path, claim = ''] = href.slice('cite:'.length).split('?');
  const slash = path.lastIndexOf('/');
  const page = Number(path.slice(slash + 1));
  if (slash < 0 || !Number.isInteger(page)) return null;
  return { filename: decodeURIComponent(path.slice(0, slash)), page, claim: decodeURIComponent(claim) };
}

/** Each page a linked answer cites, once, in the order it is first cited. */
export function citationsIn(linkedMarkdown: string): Citation[] {
  const byPage = new Map<string, Citation>();
  for (const [, href] of linkedMarkdown.matchAll(/\]\((cite:[^)]*)\)/g)) {
    const c = parseCitation(href);
    const key = c && `${c.filename}\n${c.page}`;
    if (c && key && !byPage.has(key)) byPage.set(key, c);
  }
  return [...byPage.values()];
}

/** Quoted phrases in a claim, which the source panel highlights in the passage. */
export function quotesIn(claim: string): string[] {
  // Straight quotes pair up left to right, so the odd pieces are the quoted
  // ones; a regex would pair the end of "Term" with the start of the next quote.
  const straight = claim.split('"').filter((_, i) => i % 2 === 1);
  const curly = [...claim.matchAll(/“([^”]+)”/g)].map((m) => m[1]);
  return [...straight, ...curly]
    .map((q) => q.trim())
    .filter((q) => q.length >= 12)
    .sort((a, b) => b.length - a.length);
}
