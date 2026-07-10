# OAuth Session Reliability QA

Date: 2026-07-10

## Scope

This record verifies the C.2 OAuth session reliability milestone. Live testing used a dedicated, isolated QA library. It did not read from, copy, or modify the user's normal prompt library.

## Automated checks

- `python -m pytest tests/test_openai_codex_native.py tests/test_frontend_static.py -q -p no:cacheprovider`
  - Passed: `101 passed, 1 skipped, 1 warning`
  - The warning is the existing Starlette `TestClient` / httpx deprecation warning.
- `npm run build`
  - Passed: TypeScript type-check and Vite production build completed.

## Live OAuth generation

- Confirmed the existing local OAuth session reported authenticated, available, ready, and able to generate before the test.
- Submitted one benign test prompt through the desktop generation UI in the isolated QA library.
- The job progressed from `Generating...` to a rendered result with the normal result actions.
- Rechecked provider status after completion: it remained authenticated, available, ready, and able to generate. No re-login or recovery prompt appeared.

## Visual QA

| Surface | Result |
| --- | --- |
| Desktop (1274px) | Generation workspace showed the prompt, ready state, rendered result, and result actions without horizontal overflow or overlap. |
| Mobile (390px) | Generation controls and result use the expected vertical scroll flow. Result actions remained reachable, and no horizontal overflow was present (`scrollWidth === clientWidth`). |
| Existing first-run and Config checks | The first-run library state and Config drawer were inspected previously on desktop and mobile; controls did not cover content and mobile width had no horizontal overflow. |

## Privacy and data handling

- This document intentionally omits account identifiers, local paths, tokens, authorization URLs, device codes, generated artifact names, and screenshots.
- The live test used only a benign geometric image request in the isolated QA library.

## Remaining environment note

The full local suite retains pre-existing Windows-specific platform failures outside this milestone's scope. GitHub Ubuntu CI remains the authoritative full-suite gate for the branch.
