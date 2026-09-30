# Round 4 sample report

139 documents: 56 likely category 2, 42 likely category 3, and 41 random unseen documents.

Predictions select documents; human annotations determine final labels. The random component was not model-screened.

| Selection pool | Documents | Subdirectives | Words |
|---|---:|---:|---:|
| 2 | 56 | 375 | 84,312 |
| 3 | 42 | 240 | 52,550 |
| random | 41 | 86 | 23,445 |

Total: 701 subdirectives and 160,307 words. Median 3 subdirectives per document; maximum 29.
Round 3 displayed 239 subdirectives across the same 139-document count; round 4 has 2.93 times as many annotation units.

Screened 300 unseen candidates, plus 30 historical diagnostic documents.

## Composition

| Document type | Documents |
|---|---:|
| executive_order | 44 |
| proclamation | 52 |
| memorandum | 28 |
| letter | 15 |

| Administration | Documents |
|---|---:|
| George W. Bush | 9 |
| Joseph R. Biden, Jr. | 15 |
| Barack Obama | 14 |
| Donald J. Trump | 18 |
| William J. Clinton | 18 |
| Lyndon B. Johnson | 6 |
| George Bush | 8 |
| Gerald R. Ford | 6 |
| John F. Kennedy | 5 |
| Harry S Truman | 7 |
| Ronald Reagan | 14 |
| Dwight D. Eisenhower | 5 |
| Jimmy Carter | 9 |
| Richard Nixon | 5 |

## Screening limitations

Category 2 matched 5/8 model-positive chunks and recovered 5/11 human-positive chunks. Category 3 matched 16/21 model-positive chunks and recovered 16/19 human-positive chunks.
These are small, previously exposed diagnostic samples, not independent performance estimates.

Selection cycles through retrieval-mechanism, document-type, and administration cells, preferring fewer subdirectives and then fewer words within each cell. A three-document near-template cap reduces repetition; the audit records groups and exclusions.

The targeted component's model-predicted subdirective counts are {'0': 25, '1': 253, '2': 97, '3': 199, '4': 41}.

Do not interpret the enriched sample's overall category distribution as corpus prevalence. Retain stratum identities for post-annotation yield comparisons.
