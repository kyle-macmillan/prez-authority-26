# Work status

## Completed

- Located the finalized Round 2 sub-directive export in remote commit `df5ab70`.
- Verified its 289 sub-directive labels and the code distribution.
- Joined the labels to the current canonical Flash profiles.
- Established the direct evaluation cohort: 172 aligned targets in 62 directives.
- Identified and documented exclusions: 24 gold chunks with no Flash-function
  target, three unmatched Flash segments, and two directives without aligned
  targets.
- Confirmed Tigerteam is reachable and serves `qwen3.8:27b-32k` through Ollama.
- Locked the experiment design: full cleaned Flash profile as context, marked
  Flash function group as target, condensed Codes 0–4 codebook, thinking on,
  three seeded runs, no web search, and resumable live monitoring.
- Implemented the self-contained `prepare`, `run`, `status`, and `evaluate`
  CLI, together with prompt-redaction and JSON-response unit tests.
- Prepared and validated 172 blind requests and a separate gold mapping using
  the authoritative temporary-clone export. The exclusion manifest records 24
  Flash-target misses, three unmatched Flash segments, and two directives with
  no aligned target (plus 93 labels whose directives are absent from the local
  profile snapshot).
- Completed a Tigerteam smoke run: all three seeded classifications of one
  target returned valid structured responses (118.7s, 22.6s, and 39.1s).
- Expanded and passed six unit tests covering redaction, alignment count,
  response-cache resume behavior, JSON parsing, consensus tie handling, and
  metrics.

## In progress

- Run the resumable 516-call Tigerteam benchmark. The completed smoke responses
  are reused from cache, so only the remaining calls are sent.
- Per the user's direction, unattended requests time out after 10 minutes;
  the status command remains available but is not continuously polled.

## Remaining

1. Finish all 516 target/seed calls.
2. Compute seed-level and consensus metrics, inspect failures, and write the
   final report and error table under `outputs/`.
