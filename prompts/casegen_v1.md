You write test data. You are given the hunks of a git diff, each with an id like [h1].

Write 2 to 5 short claims that a developer might say out loud when describing this change, in a natural spoken style ("I added ...", "I removed ...").

Rules:
- Every claim must be TRUE according to the diff. Mention real file, function or variable names from it.
- Each claim lists the hunk ids that show it.
- Together the claims must cover every hunk.
- Use plain verbs like added, removed, renamed, increased, decreased where they fit.

Reply with JSON only:
{"claims": [{"text": "I added ...", "hunk_ids": ["h1"]}]}
