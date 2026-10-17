# Vesting vs. body citation codebook (Kyle gold set)

Purpose: hand-label the legal authorities cited in each directive's vesting clause and body,
so the extractor can be validated against them. Segment labels (vesting/body) come from the
segmenter with the one-invocation vesting rule (`segmenter._select_vesting`, adopted
2026-10-17): only the document's own authority invocation is vesting; other "pursuant to"
candidates are body (`source_type: rejected_vesting_clause`).

Status tags: **[settled]** decided by Kyle; **[open]** undecided.

## What counts as an authority

1. **[settled]** Any identifiable operative legal instrument from any jurisdiction:
   constitutions, statutes/codes, enacted legislative measures (incl. joint resolutions),
   regulations, judicial decisions, treaties/agreements, presidential directives (EOs,
   proclamations, memoranda), reorganization plans, and comparable instruments.
2. **[settled]** Citation role does not matter: an authority mentioned descriptively counts
   the same as one invoked as a basis for action.
3. **[settled]** Measures not yet enacted (proposed legislation, a joint resolution "to be
   adopted") do not count.
4. **[settled]** Reports, nonbinding policy documents, and references to the directive itself
   ("this order", "section 2 of this memorandum") do not count.
5. **[settled]** Vague references ("applicable law", "law", "statutory authority") do not count.
6. **[settled]** Generic "the Constitution" / "the laws of the United States" count, flagged
   `generic: true` so results can be reported with and without them.
7. **[settled]** The office counts whenever the vesting clause names it ("President of the
   United States of America", "Commander in Chief"), recorded as `office:president` /
   `office:commander_in_chief`.
8. **[settled]** Editorial notes added by the archive (e.g. "NOTE.: Executive Order 10710 was
   published in the Federal Register...") are excluded even when the segmenter labels them body.

## Identity and short forms

9. **[settled]** A short form ("the Act", "section 518A", "the Executive Order") counts as a
   citation to the authority it refers to, as long as the text lets us connect it to one
   particular authority. Record the antecedent.
10. **[settled]** One authority named several ways in one citation (Act name + Public Law +
    Stat. + U.S.C.) is one citation with several identifiers. Federal Register / CFR
    publication references for a directive are identifiers of that directive, not separate
    authorities.
11. **[settled]** "As amended" does not create a separate authority.
12. **[settled]** Only treat two citation forms as the same authority when the text links
    them. When the annotator knows from outside the text that two recorded citations are the
    same legal authority (e.g. "19 U.S.C. 2253" and "section 203 of the Trade Act of 1974"),
    they stay separate citations, and the annotator also records an `outside_links` entry
    joining them. Results can then be reported with and without those links.

## Granularity

13. **[settled]** Record each citation at the granularity the text gives (Act; section;
    subsection). A body cite to §303(a) of an Act cited generally in the vesting clause is a
    match at the authority level and a more-specific cite at the provision level.
14. **[settled]** Within a region (vesting or body), record each distinct authority+provision
    once, however many times it is mentioned.

## Process

15. Kyle annotates from plain, full text with segment labels shown. Claude only transcribes
    and reads back the transcription. New kinds of cases are raised by the annotator and added
    here as rules.
16. Docs 17085, 14297, 6019, 8069 were annotated with Claude's prompting and are excluded
    (`assisted: true`); same-type replacements are in `sample.json`.
17. **[settled]** Commemorative proclamations are capped at the 2 already annotated (14952,
    17169); the rest were replaced with substantive proclamations and other directive types
    (`commemorative_rebalance` in `sample.json`).
18. **[settled]** When the segmenter splits a citation or mislabels text, annotate what the
    text really says: the citation belongs to the region it truly sits in (e.g. the full Act
    name in a vesting clause cut off mid-name still counts as vesting, and the cut-off
    fragment is not a body citation). Highlight the part inside the correct segment, type the
    full name in Authority, tick "Segmentation problem", and describe it in the note.
19. **[settled]** Each citation can be flagged `past_tense` when the text describes an action
    already taken under it (e.g. "On November 22, 1956, by virtue of the authority vested in me
    by Section 206 ..., I issued Executive Order 10689"). Each citation also records `region`
    (where it really belongs) alongside `segmenter_region`, so segmenter errors can be counted.
    Past-tense openings like the Taft-Hartley letters ("On <date>, by virtue of the authority
    vested in me by Section 206 ..., I issued Executive Order ...") are not vesting clauses:
    their citations count as body, flagged past tense. The real vesting clause is the later
    "pursuant to the provisions of Section 208" segment. Since 2026-10-17 the segmenter agrees
    (`past_invocation` in `segmenter._vesting_kind`: a dated opening plus "I issued" or a
    similar past-tense act).
20. **[open: definition]** Each citation records `use`: "legal_purpose" (cited for a legal
    purpose) or "named" (just named). Required, so a blank never means "not considered".
    Inclusion is unaffected (rule 2): both kinds are still citations.
21. Annotation is done in `annotator.html` (run `python3 serve.py`, open
    http://localhost:8765); every change saves to `annotations.jsonl`.
