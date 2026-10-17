# Round 2 disagreement analysis

This analysis uses the primary `code` field. Code meanings are: `0` outside scope, `1` discretionary/internal, `2` dictated agency outcome, `3` self-executing, and `4` unclear/mixed. The annotator order below is Claire / KyleM / Thomas Weil.

## Document-level directives

There are 26 document-level disagreements: 4 where all three chose different codes and 22 two-to-one splits.

### All three chose different codes

| Document | Codes | Subject/theme |
| --- | --- | --- |
| EO2 | 3 / 1 / 4 | Amendment to the White House Fellows program; direct legal amendment versus internal administration versus mixed |
| EO3 | 3 / 1 / 2 | Equal-employment program and federal contracting requirements |
| M4 | 3 / 4 / 0 | Approval of the U.S.–Russia peaceful nuclear-energy agreement |
| M5 | 2 / 3 / 1 | Federal support for governors’ National Guard response to COVID-19 |

These are the clearest high-ambiguity cases: they span legal effect, internal implementation, and policy authority rather than reflecting a simple boundary dispute.

### Two-to-one splits by recurring theme

#### Executive administration, agency organization, and regulatory direction

The recurring split is usually Claire = `3` versus KyleM and Thomas Weil = `1`:

`EO1`, `EO6`, `EO11`, `EO13`, `EO18`, `EO19`, `EO21`, `EO22`, `EO28`, `EO32`

These documents establish committees or succession arrangements, direct agencies to reconsider or implement policy, regulate agency activity, or impose operational requirements. The theme is a boundary between “the directive itself has legal/self-executing effect” and “the directive primarily directs internal executive administration.”

Related exceptions in this theme:

- `EO17`: Claire and KyleM = `1`; Thomas Weil = `3`.
- `EO30`: Claire and KyleM = `3`; Thomas Weil = `1`.
- `EO8`: Claire and Thomas Weil = `0`; KyleM = `3` — a holiday/office-closure order that may be read as ceremonial or as directly operative.
- `L27`, `P1`: Claire = `1`; KyleM and Thomas Weil = `0` — advisory or commemorative material near the outside-scope/internal-management boundary.

#### Presidential letters involving foreign affairs, reporting, or emergency action

Most of these are Claire and KyleM = `0`; Thomas Weil = `3`:

`L1`, `L3`, `L6`, `L8`, `L22`

The common feature is a letter transmitting a report, recognizing a foreign government, describing an international matter, or reporting an emergency-related action. The disagreement appears to be whether the letter’s operative legal context should count even when the document itself is primarily communicative or reportorial.

Other letter splits:

- `L20`: Claire = `0`; KyleM and Thomas Weil = `3` — a trade/emigration waiver determination.
- `L11`: Claire and Thomas Weil = `0`; KyleM = `2` — congressional notification of a defense-funding reallocation.

#### Emergency, national-security, and high-policy actions

- `M5`: all three different; the National Guard/COVID response combines statutory authority, presidential policy, agency/state implementation, and emergency facts.
- `M4`: all three different; treaty/agreement approval combines foreign affairs, nuclear policy, and formal presidential approval.
- `EO6`: Claire = `3`; KyleM and Thomas Weil = `1`; the succession order raises the self-executing-versus-internal succession distinction.

## Numbered sub-directives

There are 64 sub-directive disagreements: 14 all-different cases and 50 two-to-one splits.

### All three chose different codes

- `EO2#1`, `EO2#2`, `EO2#3`: White House Fellows program amendments — `3/0/4` or `3/1/4`.
- `EO3#2`, `EO3#3`: equal-employment program requirements — `3/1/2`.
- `EO6#2`, `EO11#2`, `EO30#7`: succession, appointment, or agency-administration provisions — `3/0/1`.
- `M4#1`: nuclear-energy agreement approval — `3/4/0`.
- `M5#2`, `M5#4`: National Guard/COVID response — `2/3/1`.
- `M5#3`: National Guard/COVID response — `2/0/1`.
- `P53#9`: proclamation provision — `3/2/0`.
- `EO30#10`: agency/employment provision — `3/1/0`.

### Repeated two-to-one patterns

- Claire = `3`, KyleM and Thomas Weil = `1`: `EO1#3`, `EO3#4`, `EO9#3`, `EO10#3`, `EO13#5`, `EO18#4`, `EO19#1`, `EO21#1`, `EO22#4`, `EO28#1`, `EO28#2`, `EO32#6`, `P53#10`.
- Claire and KyleM = `0`, Thomas Weil = `3`: `L1#1`, `L3#1`, `L22#1`, `P53#1`, `P53#5`.
- Claire and Thomas Weil = `0`, KyleM = `3`: `EO8#1`.
- Claire = `0`, KyleM and Thomas Weil = `3`: `M1#1`, `M8#1`, `L20#1`, `L20#2`, `P53#8`.
- Claire and KyleM = `0`, Thomas Weil = `1`: `EO23#1`, `EO25#1`, `P21#2`, `P53#2`, `P53#3`.
- Claire and KyleM = `1`, Thomas Weil = `3`: `EO17#1`.
- Claire and KyleM = `1`, Thomas Weil = `0`: `EO4#1`, `EO24#6`, `EO30#9`.
- Claire and KyleM = `3`, Thomas Weil = `1`: `EO13#4`.
- Claire and Thomas Weil = `1`, KyleM = `3`: `EO30#5`.
- Claire and Thomas Weil = `2`, KyleM = `0`: `L24#1`.
- Claire and Thomas Weil = `2`, KyleM = `1`: `EO26#2`.
- Claire and Thomas Weil = `3`, KyleM = `0`: `EO26#3`, `EO33#4`.
- Claire and KyleM = `2`, Thomas Weil = `1`: `EO32#2`, `P53#11`.
- Claire and Thomas Weil = `0`, KyleM = `2`: `P18#1`.
- Claire and Thomas Weil = `0`, KyleM = `1`: `EO25#4`, `EO25#5`.
- Claire = `1`, KyleM = `0`, Thomas Weil = `0`: `P1#2`.
- Claire = `3`, KyleM = `0`, Thomas Weil = `0`: `P30#1`.

## Main themes

1. **Self-executing effect versus internal administration.** This is the dominant pattern, especially in executive orders establishing bodies, assigning succession, directing agencies, or requiring operational compliance.
2. **Communicative/reportorial documents versus operative legal action.** Letters are repeatedly split between outside scope (`0`) and self-executing (`3`), particularly where a letter transmits a report but also records a determination, recognition, waiver, or emergency action.
3. **Mixed authority in emergency and foreign-policy actions.** The nuclear agreement and COVID/National Guard memorandum generate all-different judgments because several authority types appear in the same document.
4. **Proclamations and ceremonial or commemorative material.** Proclamation provisions, office closures, and anniversary material produce `0/1/3` boundary disputes, suggesting uncertainty about when a formal presidential instrument is legally operative versus expressive or administrative.
5. **Segment-level context sensitivity.** Several documents have agreement at the document level but disagreement in individual numbered chunks, especially EO13, EO25, EO26, EO30, EO32, EO33, and P53. The disagreement is therefore often about the scope of a particular clause, not the document as a whole.
