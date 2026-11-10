# Official submission helpers

Retrieved read-only on 2026-11-10 from the course website's public GitHub repository.
These files implement the official form's score validation, artifact URL encryption,
and GitHub issue formatting. They are submission tooling, never imported by the agent.

- `arena.1b5f9fa2d0c3.mjs`: https://raw.githubusercontent.com/xudongwu-0/xudongwu-0.github.io/main/courses/dase7506/assets/arena.1b5f9fa2d0c3.mjs
- `projects.96a85432df3c.mjs`: https://raw.githubusercontent.com/xudongwu-0/xudongwu-0.github.io/main/courses/dase7506/assets/projects.96a85432df3c.mjs
- `mp3.7f58aab1fef1.mjs`: https://raw.githubusercontent.com/xudongwu-0/xudongwu-0.github.io/main/courses/dase7506/assets/mp3.7f58aab1fef1.mjs
- `student-id-public.pem`: https://raw.githubusercontent.com/xudongwu-0/xudongwu-0.github.io/main/courses/dase7506/data/student-id-public.pem

The PEM is the instructor's public encryption key, not a credential or private key.
The script uses Node.js 20+ built-in APIs and does not send requests or create issues.
`payload.json` and `issue-body.md` contain encrypted artifact URLs exactly as the
official browser form does. A prepared handoff is not a saved submission.

After the final immutable source ZIP is published:

```text
node scripts/prepare_submission.mjs --score outputs/test-score.json --code-url HTTPS_IMMUTABLE_ZIP --student-id STUDENT_ID --output-dir submission-handoff
```

Create an issue in `xudongwu-0/xudongwu-0.github.io` with the generated title and body.
Preserve the official complete test-score JSON byte-for-byte.
