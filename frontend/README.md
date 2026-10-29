# AxiomForge console

Next.js 16 / React 19 / Tailwind console for AxiomForge. It talks to the FastAPI backend (`NEXT_PUBLIC_API_URL`, default `http://127.0.0.1:8000`) and has Turkish and English interfaces, light and dark themes, and keyboard and screen reader support.

| Page | Purpose |
| --- | --- |
| `/` | Ask a question or paste an arXiv link, approve a plan, follow the run |
| `/campaigns`, `/campaign/[id]` | Multi-dataset replication campaigns: summary, charts, evidence ledger, cancel and retry |
| `/result/[threadId]` | Result of a single experiment run |
| `/research`, `/research/[id]` | Research agent sessions: start, follow, cancel, retry, read the hypotheses and their confirmation |

## Run

```bash
npm install
npm run dev        # http://localhost:3000 (use localhost, not 127.0.0.1)
```

The backend must be running; see the root `README.md` for the API, the worker and Docker.

If the API is protected with `API_KEY`, build the console with the same value in `NEXT_PUBLIC_API_KEY`. Variables are listed in the root `.env.example`.

## Test

```bash
npm test           # unit and component tests (Node test runner)
npx tsc --noEmit   # types
npm run lint
npm run build
npm run e2e        # Playwright; needs a build first. Set PW_CHANNEL=msedge to use a local Edge
```

The browser tests mock the API, so they need no backend. They include an axe accessibility scan in both themes.
