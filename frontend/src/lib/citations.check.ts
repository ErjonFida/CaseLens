// Run with: node src/lib/citations.check.ts
import assert from 'node:assert/strict';
import { citationsIn, linkCitations, parseCitation, quotesIn } from './citations.ts';

const docs = ['Scoutcam Services Agreement.pdf', 'OFG Bancorp Outsourcing Agreement.pdf'];
const href = (md: string) => md.match(/\]\((cite:[^)]*)\)/)?.[1] ?? '';

// The live demo's answer format: italic filename, ", Page N", in parentheses.
const answer =
  'Section 3 provides that the term commences "on the date hereof (the \'Effective Date\')" ' +
  '(*Scoutcam Services Agreement.pdf*, Page 1).';
const linked = linkCitations(answer, docs);
assert.match(linked, /^Section 3 .*\)" \[Scoutcam Services Agreement · p\. 1\]\(cite:[^)]*\)\.$/);
const c = parseCitation(href(linked))!;
assert.equal(c.filename, 'Scoutcam Services Agreement.pdf');
assert.equal(c.page, 1);
assert.equal(c.claim, 'Section 3 provides that the term commences "on the date hereof (the \'Effective Date\')"');
assert.deepEqual(quotesIn(c.claim), ["on the date hereof (the 'Effective Date')"]);

// A short quoted word before the quote must not shift the pairing.
assert.deepEqual(quotesIn('Section 3 ("Term") says the term "shall commence on the date hereof (the “Effective Date”)"'), [
  'shall commence on the date hereof (the “Effective Date”)',
  'Effective Date',
]);

// Italics around the whole cite, as the demo also answers.
assert.match(linkCitations('Dated April 1, 2019 (*Scoutcam Services Agreement.pdf, Page 1*).', docs), /2019 \[[^\]]*\]\(cite:[^)]*\)\.$/);

// A "Source:" label inside the parenthesis, as the demo also answers.
assert.match(linkCitations('Notice is required. (*Source: Scoutcam Services Agreement.pdf, Page 9*)', docs), /required\. \[[^\]]*\]\(cite:[^)]*\)$/);

// No extension, lower-case "page", bold, two sources in one parenthesis.
const two = linkCitations('Both apply (**OFG Bancorp Outsourcing Agreement**, page 9; Scoutcam Services Agreement.pdf, p. 2).', docs);
assert.equal((two.match(/cite:/g) ?? []).length, 2);
assert.ok(!two.includes('(['), 'the wrapping parenthesis is dropped');

// The sources list: each page once, in first-cited order.
const repeated = linkCitations(
  'A (Scoutcam Services Agreement.pdf, Page 2). B (OFG Bancorp Outsourcing Agreement.pdf, Page 9). C (Scoutcam Services Agreement.pdf, Page 2).',
  docs
);
assert.deepEqual(citationsIn(repeated).map((s) => `${s.filename} ${s.page}`), [
  'Scoutcam Services Agreement.pdf 2',
  'OFG Bancorp Outsourcing Agreement.pdf 9',
]);

// Unknown files and pages without a filename stay text; so does everything with no documents.
const plain = 'See the Acme Agreement, Page 4, and page 2 of the schedule.';
assert.equal(linkCitations(plain, docs), plain);
assert.equal(linkCitations(answer, []), answer);
assert.equal(parseCitation('https://example.com'), null);

console.log('citations: ok');
