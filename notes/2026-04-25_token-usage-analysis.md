# Token Usage Analysis — Session 2fc156c7
*April 25, 2026*

## Session Totals

| Metric | Tokens |
|--------|--------|
| Total input (incl. cache reads) | 96,085,879 |
| Total output | 531,355 |
| Grand total | **96,617,234** |
| API calls made | 451 |

---

## Top 10 API Calls by Token Count

| Total | In | Out | Trigger |
|------:|---:|----:|---------|
| 415,230 | 414,924 | 306 | (tool call continuation) |
| 414,862 | 412,877 | 1,985 | "Ok - lets make a note in refactor..." |
| 414,862 | 412,877 | 1,985 | (tool call continuation) |
| 412,742 | 412,674 | 68 | (tool call continuation) |
| 412,616 | 409,253 | 3,363 | "It is still a little bumpy..." (the piano MIDI output paste) |
| 412,616 | 409,253 | 3,363 | (tool call continuation) |
| 412,616 | 409,253 | 3,363 | (tool call continuation) |
| 395,854 | 394,941 | 913 | (tool call continuation) |
| 395,854 | 394,941 | 913 | (tool call continuation) |
| 394,854 | 394,010 | 844 | (tool call continuation) |

---

## Why Usage Burns Fast in Long Sessions

The 96M token figure is **dominated by cache reads**, not new input. Claude Code uses prompt caching aggressively — but the cache is re-read on every API call. By the time this session's context grew to ~412K tokens, every single API call was paying to re-read that full context from cache. With 451 API calls, that multiplies fast.

### What made this session expensive

1. **Long conversation context.** The session covered a full day's work — plan mode, multiple file reads, many edits, long code outputs. Every message added to the permanent context.

2. **The MIDI output paste.** Pasting the ~200-line MIDI note trace added ~4,000 tokens permanently to the context. The response it triggered was 3,363 output tokens (also large). Every subsequent API call re-read both.

3. **Multiple tool calls per response.** Reads, edits, and Bash calls each add a round-trip. With ~4.7 tool calls per response on average (451 calls / ~96 turns), each user message generated multiple API calls, each re-reading the full context.

---

## Tips for Next Session

| Tip | Why |
|-----|-----|
| Paste only the last 20 lines of long outputs | The bottom of a traceback or log is the actionable part; the top is noise that permanently grows the context |
| Share just the error message, not the full terminal dump | Same reason — context growth is the enemy |
| Start a new session after a major milestone | Resets context to near-zero; cache misses briefly but recovers quickly |
| Use plan mode only when planning | Plan mode adds overhead (extra system prompt); switch to normal mode for implementation |
| Prefer short confirmation messages | "Ok, test passed" is cheaper than pasting the full output |
