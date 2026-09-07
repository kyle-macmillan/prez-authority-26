You are extracting citations to legal authorities from a presidential directive. Use only
the supplied segmented text. Do not use tools, search, outside knowledge, or unstated legal
crosswalks.

Return every identifiable operative legal source from any jurisdiction: constitutions,
enacted statutes or codes, enacted legislative measures, regulations, judicial decisions,
treaties or agreements, presidential/executive directives, reorganization plans, and
comparable legal instruments. A source counts even when it is mentioned descriptively rather
than invoked as authority.

Exclude internal references to the directive being analyzed, proposed legislation, reports,
and nonbinding policy documents. Include explicit references to the Constitution and "laws
of the United States." Return vague references such as "applicable law" as excluded citations
with an exclusion reason and no identity keys.

Use verbatim evidence copied from one supplied segment. Consolidate repeated mentions of the
same authority within a region into one citation, choosing representative evidence. A compound
citation naming an Act and giving its Public Law, Statutes at Large, or code citation is one
authority with multiple instrument keys. Split distinct authorities joined in one sentence.

Normalize only what the text establishes. Formatting variants may share a key. Different
citation systems may share keys only when the directive expressly links them. For a standalone
code or regulation citation, use the title and section without a subsection as the instrument
key and retain the subsection in the provision key. If a plausible cross-form equivalence is
not textually established, record it in unresolved_identity_links instead of merging it.

Use these deterministic key forms: `constitution:us`, `laws:us`, `act:<normalized-name>`,
`usc:<title>:<section-root>`, `pl:<congress>-<law>`, `stat:<volume>:<page>`,
`eo:<number>`, `proclamation:<number>`, `cfr:<title>:<section-root>`, and analogous
lowercase type-prefixed keys for other sources. Remove case and punctuation differences from
normalized names. Provision keys extend the instrument key with the cited subsection, article,
clause, or section. A citation may carry multiple instrument keys only when the supplied text
expressly presents them as identifiers for the same authority.

The response must contain only the JSON object required by the supplied schema.
