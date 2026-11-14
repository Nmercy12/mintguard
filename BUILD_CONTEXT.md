# MintGuard — build context (Agent Games Wildcard submission)

## How the agent works

```
POST /audit {chain, address}
  └─> mintguard.audit.audit()
        ├─ Phase 1 (parallel): eth_blockNumber, eth_getCode,
        │   EIP-1967 implementation slot, Sourcify match, Sourcify ABI,
        │   DexScreener pairs
        ├─ Proxy resolution: if the EIP-1967 slot holds an implementation,
        │   the *implementation* bytecode is what gets scanned
        ├─ EIP-1153 scan: proper disassembly that skips PUSH1–PUSH32 data,
        │   so 0x5c/0x5d bytes inside push data are never miscounted
        ├─ Phase 2 (parallel): owner(), paused(), totalSupply(),
        │   maxSupply()/MAX_SUPPLY(), name(), symbol(), price functions,
        │   mintOpen(), freeLeft(), TOKEN(), ownerOf(1)
        ├─ Track classification from the verified ABI + probes
        ├─ Dry-run: eth_call of the ABI's real mint shape with 0 value
        ├─ Market: DexScreener for the contract + its reward token;
        │   honeypot.is for token-track contracts (best-effort)
        └─ Score + verdict (deterministic rubric, hard caps)
  └─> JSON report: verdict, score, track, free/paid, checks, findings,
      evidence, block number, elapsed time
```

One engine, three front-ends: the CLI (`python -m mintguard`), the local dev
server (`server.py`, stdlib `http.server`), and the Vercel serverless function
(`api/audit.py`, same code, `BaseHTTPRequestHandler`). The demo page
(`public/index.html`) is dependency-free HTML/JS that calls the endpoint.

## Key decisions

- **Standard library only — no dependencies.** The agent needs Keccak-256
  (for function selectors), JSON-RPC, and HTTPS. All three are implemented in
  ~250 lines of pure Python (`mintguard/keccak.py` is a from-scratch
  Keccak-f1600, verified against the empty-string vector and four known
  selectors). Zero install friction, zero supply-chain risk, and the Vercel
  function needs no build step.
- **Public endpoints only.** BSC/Ethereum/Base/Robinhood public RPCs,
  Sourcify, DexScreener, honeypot.is — all unauthenticated, no keys. This is
  a deliberate constraint: the public repo must never contain a keyed RPC URL
  (the author's own keyed endpoint stays out of the repo entirely). The cost
  is that a check reports `unknown` when a public endpoint is down, instead of
  failing the audit — and says so.
- **curl first, urllib fallback.** On the author's VM, Python's urllib
  intermittently fails on chunked responses while curl retries cleanly, so the
  transport tries curl (subprocess) first and falls back to stdlib. Both paths
  are exercised in the same code on Vercel (Amazon Linux ships curl).
- **Parallel probes, sequential phases.** The ~20 reads are independent inside
  each phase, so they run in a thread pool (typically ~10s total). The dry-run
  and the reward-token market lookup depend on phase-2 results, so they run
  after. An audit that slow is documented honestly rather than hidden.
- **ABI-driven mint discovery, not selector guessing.** When source is
  verified, the agent reads the actual ABI: it finds the real price function
  (`PRICE()` vs `mintPrice()` vs `cost()`), the real free functions
  (`freeMintX`, …), and the real mint shape for the dry-run. A contract whose
  free mint is signature-gated is reported as "free — signature-gated", not
  as "paid" just because `PRICE() > 0`. This is the single most important
  design choice: it is what separates MintGuard from a checklist that calls
  every paid-price contract a scam.
- **EIP-1153 is a compatibility finding, not a scam verdict.** The detector is
  contract-level, and the author proved (in real hunting) that a flagged
  contract can still have working functions that never touch transient
  storage. The report says exactly that, every time.
- **"Unknown" is a first-class answer.** A missing function returns empty, a
  revert returns a reason, a dead endpoint returns a transport error — the
  three are never conflated, and an unanswered question costs points instead
  of being assumed clean.

## Where the expertise comes from

The checks are not textbook — each one exists because a real mint failed on
it during months of free-mint hunting on BSC with the Binance Agentic Wallet:

- The EIP-1153 scanner was built after a whole class of new mints reverted
  in preview with the same generic error; the bytecode scan now runs *before*
  any preview is attempted.
- The proxy-resolution step exists because a minimal-proxy stub once scored
  "blocked" while its implementation was clean (the flag bytes were in the
  metadata hash, not in executable code).
- The ABI-driven price/free logic exists because contracts like DRIFTWIRE
  have *both* a paid `mint()` and a signature-gated free mint — and only the
  ABI tells you which is which.
- The dry-run exists because "the site says free" has been wrong before.

## What the agent cannot do (yet)

- Full source-code review: it reads the ABI and probes behavior; it does not
  do line-by-line analysis of verified source (e.g. hidden mint paths inside
  `mint`, or `setBaseURI` mutability after reveal). Those are documented
  limitations, not silent gaps.
- Holder-concentration analysis (needs archive Transfer logs — a premium-RPC
  feature, out of scope for a no-key agent).
- Real-time monitoring: it audits one address on demand; there is no watcher,
  no alerting, no background job.

## Verification

- `tests/test_audit.py` — 9 offline unit tests (Keccak vectors, PUSH-aware
  disassembly, track classification). `python3 -m unittest discover -s tests`.
- `DEMO_RESULTS.md` — three live audits with pinned blocks, reproducible with
  one command each.
