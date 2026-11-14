# 🛡️ MintGuard — a free-mint safety auditor agent

**Agent Games by zkVerify — Wildcard track entry.**

Free-mint hunters get drained by malicious contracts: fake mints, honeypots,
hidden fees, and contracts their wallet can't even simulate. MintGuard takes a
chain + contract address and returns a structured **GO / CAUTION / BLOCK**
verdict with replayable on-chain evidence — before anyone signs anything.

- **Live demo:** https://mintguard.vercel.app *(deploy pending — see below)*
- **Endpoint:** `POST /audit` → `{"chain": "bsc", "address": "0x..."}` → JSON verdict
- **Demo results:** [DEMO_RESULTS.md](DEMO_RESULTS.md) — three real audits, nothing fabricated

## What it checks

| Check | How | Why it matters |
|---|---|---|
| Contract exists | `eth_getCode` | "Mint" pages sometimes point at EOAs or dead addresses |
| Proxy resolution | EIP-1967 implementation slot | Never judge a proxy by its stub bytecode |
| EIP-1153 transient storage | Proper disassembly (PUSH data skipped) | Binance Agentic Wallet writes revert on TSTORE/TLOAD contracts |
| Source verification | Sourcify (`exact_match` vs `match` vs none) + ABI | Mint mechanics must come from real code, not a website |
| Track classification | ABI shape + `ownerOf` probe | A mining contract is not a mint; a token is not a mint |
| Owner / pause | `owner()`, `paused()` | Live owners can still change the rules |
| Mint price & free path | Price functions + free-mint functions from the ABI, `mintOpen()`, `freeLeft()` | "Free" is proven from the contract, not claimed by a banner |
| Dry-run mint | `eth_call` of `mint(1)` with 0 value (read-only, never broadcast) | Proves the price gate is actually enforced |
| Supply | `totalSupply()` / `maxSupply()` | Sold out is a fact, not a feeling |
| Market & honeypot | DexScreener pairs, honeypot.is (tokens, best-effort) | The reward is only worth something if it can be sold |

Verdict: **GO ≥ 85**, **CAUTION 55–84**, **BLOCK < 55**, with hard blocks for
no-code, honeypot, not-free, sold-out, and closed mints. The scoring rubric is
documented in `mintguard/audit.py` — deterministic, no vibes.

## Try it

```bash
# CLI (no server needed)
python3 -m mintguard 0x485be9daa4620fcee4e2baed7cc85ea57acb44b0 --chain bsc

# Local demo server (same engine as the deployed endpoint)
python3 server.py
# open http://127.0.0.1:8000/  —  POST /audit works there too

# HTTP
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"chain":"bsc","address":"0x485be9daa4620fcee4e2baed7cc85ea57acb44b0"}' \
  http://127.0.0.1:8000/audit | python3 -m json.tool
```

Supported chains: `bsc` (56), `eth` (1), `base` (8453), `robinhood` (4663).

## Deploy (Vercel, free)

No secrets, no env vars, no build step — the repo is standard-library-only Python.

1. In the Vercel dashboard: **Add New → Project → Import** this repo.
2. Framework preset: **Other**. Root directory: repo root. Deploy.
3. The demo page is served from `public/index.html`; the agent is the
   serverless function `api/audit.py` (also reachable as `POST /audit` via the
   rewrite in `vercel.json`).

**One honest caveat:** an audit fans out ~20 public reads (RPC + Sourcify +
DexScreener) and typically takes **~10 seconds**. Vercel's Hobby plan caps
functions at 10s, so an audit can occasionally time out there — use a plan
with a longer function timeout (Pro/Fluid, 60s) or any host without a 10s cap.
The local server has no such limit, and the demo page shows the elapsed time.

## Layout

```
mintguard/            the audit engine (stdlib only)
  keccak.py           pure-Python Keccak-256 (selector computation)
  rpc.py              public JSON-RPC + HTTPS client (curl first, urllib fallback)
  audit.py            checks, scoring, verdict
  __main__.py         CLI
api/audit.py          Vercel serverless function (same engine)
public/index.html     demo page (no dependencies)
server.py             local dev server (same engine)
tests/                offline unit tests (no network)
```

## Honest limitations

- **Bytecode-level, not a full code review.** A selector in bytecode is not proof a feature is live; findings are confirmed against the verified ABI when source is available, and marked `unknown` otherwise.
- **EIP-1153 is contract-level, not per-function.** A flagged contract may still have working functions that never touch transient storage. MintGuard reports the flag and the caveat; it does not claim every function is broken.
- **Public endpoints only.** No keyed RPCs, no paid APIs. If a public endpoint is down, that check reports `unknown` instead of failing the audit — and says so.
- **Read-only.** MintGuard never signs, never broadcasts, never moves funds. The dry-run is an `eth_call` simulation.
- **Not financial advice.** A GO verdict means "the contract looks as advertised for a free mint", not "this will make money".

## Who it helps

Free-mint hunters on EVM chains — especially Agent ID / Binance Agentic Wallet
users, whose wallet simulator rejects EIP-1153 contracts outright. The agent
was built from real hunting experience: every check exists because a real mint
failed on it (see [BUILD_CONTEXT.md](BUILD_CONTEXT.md)).

## Submission (Agent Games — Wildcard)

- **Agent link:** this repo (+ demo link above)
- **Public endpoint:** `POST https://mintguard.vercel.app/audit`
- **Use case:** [USE_CASE.md](USE_CASE.md)
- **Build context:** [BUILD_CONTEXT.md](BUILD_CONTEXT.md)
- **zkVerify angle (optional):** [ZKVERIFY.md](ZKVERIFY.md) — the checkable claim is reproducibility; no proof exists yet and none is claimed.

Reference only, not investment advice. MIT licensed.
