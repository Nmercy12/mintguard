# 🛡️ MintGuard — a free-mint safety auditor agent

**Agent Games by zkVerify — Wildcard track entry.**

Free-mint hunters get drained by malicious contracts: fake mints, honeypots,
hidden fees, and contracts their wallet can't even simulate. MintGuard takes a
chain + contract address and returns a structured **GO / CAUTION / BLOCK**
verdict with replayable on-chain evidence — before anyone signs anything.

- **Live demo:** https://mintguard-one.vercel.app
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
