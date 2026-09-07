You are coding one statutory authority cited in the formal vesting clause of one or more nonceremonial presidential directives. Judge the cited statutory provision itself as it existed on each observed directive date. Do not infer authority from the directive's action or from general presidential supervision.

Return one date-bounded classification for every statutory version needed to cover all OBSERVED_DATES or the complete OBSERVED_DATE_RANGE when a long date list has been compressed. Use the supplied text when it is historically applicable. You may use web search to locate or verify official historical text. Prefer the Office of the Law Revision Counsel, Congress.gov, GovInfo, and official Statutes at Large. Do not use shell, filesystem, MCP, computer-use, or other tools.

Presidential function fields are multi-label:

- `presidential_authorization`: the provision affirmatively permits, empowers, or assigns the President to act, including permission to delegate an assigned presidential function.
- `presidential_required_duty`: the provision unconditionally requires the President to perform a legal function, such as submitting a report or publishing a notice. Track this field, but a required duty alone is not a delegation for the headline measure.
- `presidential_condition_precedent`: the provision assigns the President a legal predicate the President must perform before an action can occur, such as making a finding, determination, certification, designation, or approval. A factual limit, deadline, cap, or prohibition that does not assign a predicate act to the President is not a condition-precedent function.
- `standalone_presidential_constraint`: the provision limits or prohibits presidential conduct without affirmatively authorizing an action or assigning the President a predicate function. A constraint alone is not a delegation.

Derive `classification` exactly as follows:

- `delegation` when `presidential_authorization` or `presidential_condition_precedent` is true.
- `nondelegation` when both are false and the statutory text is sufficiently specific and verifiable. This includes required-duty-only and constraint-only provisions, definitions, findings, policy, agency-only authority, substantive schedules or standards, and background law.
- `too_broad` when the citation identifies an Act, title, chapter, range, `et seq.` scope, or contextual reference that does not isolate a reliably classifiable legal provision. Do not use `too_broad` merely because research is difficult.
- `cannot_verify` when the citation is specific enough in principle but the controlling historical provision or its identity cannot be established from reliable sources.

For a pinpoint subsection, use its parent provision and directly incorporated cross-references only as necessary to resolve its grammar, actor, function, or legal conditions. Do not import unrelated presidential powers from elsewhere in a section or statute. If a provision both authorizes action and imposes conditions, set every applicable field true.

Each version interval must include every observed date to which that answer applies and intervals must not overlap. Quote a short operative statutory excerpt, not language from the presidential directive. For `too_broad` or `cannot_verify`, the excerpt may be empty. Give direct official source URLs; never invent a source or quotation. Return only JSON matching the required schema.
