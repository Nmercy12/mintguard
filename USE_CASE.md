# MintGuard — use case (Agent Games Wildcard submission)

## The problem

Free mints are the cheapest way into new crypto projects — and one of the
easiest ways to get drained. A "free mint" page can hide:

- **A contract that takes your mint fee and delivers nothing** (unbounded
  `withdraw()` before any reveal, no refund function).
- **A honeypot token** — you can mint/buy, but you can never sell.
- **A paid mint dressed as free** — the site says "free", the contract's
  `PRICE()` says 0.0015 BNB.
- **A contract your wallet cannot even simulate** — Binance Agentic Wallet's
  preview simulator does not support EIP-1153 transient storage, so every
  write to such a contract reverts before it is even sent.
- **A contract that is not a mint at all** — a staking/mining contract or a
  plain token, framed as a drop.

Today, checking any of this means hand-running a dozen RPC calls, reading
verified source, and knowing which selectors to probe. Most hunters either
skip the checks (and get drained) or waste their wallet's preview quota on
contracts that were never going to work.

## Who the agent helps

- **Free-mint hunters** on EVM chains (BSC first, plus Ethereum, Base,
  Robinhood Chain) — they paste an address and get a verdict before signing.
- **Agent ID / Binance Agentic Wallet users** in particular: the EIP-1153
  check answers in seconds a question that otherwise costs a failed preview
  and a wasted slot.
- **Anyone handed a contract address** in a chat, on X, or on a mint page who
  wants a second opinion grounded in on-chain reads, not in the project's
  marketing copy.

## What the agent actually does

Input: `{chain, address}`. Output: a JSON report with

- **Verdict: GO / CAUTION / BLOCK** and a 0–100 score (deterministic rubric,
  documented in `mintguard/audit.py`).
- **Track:** `nft_mint`, `token`, `mining`, or `unknown` — classified from the
  verified ABI + probes, so a mining contract is never judged as a mint.
- **Free vs paid, proven from the contract:** price functions, free-mint
  functions found in the ABI, `mintOpen()`, `freeLeft()`, and a zero-value
  dry-run `eth_call` of the real `mint` function (read-only — nothing is
  broadcast).
- **Evidence for every finding:** EIP-1153 opcode counts with the exact
  bytecode scanned, Sourcify match status, owner/pause state, supply,
  reward-token market data, honeypot/tax signals — all pinned to a block
  number so anyone can re-run the same reads and get the same verdict.

The agent is a **web service** (`POST /audit`) plus a **demo page** (a form
that calls it and renders the verdict). It is also a **CLI**
(`python3 -m mintguard 0x... --chain bsc`). Same engine everywhere.

## What it does NOT do

- It never signs, broadcasts, or moves funds. The only "transaction" it runs
  is a read-only `eth_call` simulation.
- It does not claim a contract is "safe" in general — only that, for a
  free-mint hunter, the contract looks as advertised (or does not).
- It does not invent evidence: a check that cannot be answered from public
  data is reported as `unknown`, with the reason, and costs points instead of
  being assumed clean.

## Proof it works

[DEMO_RESULTS.md](DEMO_RESULTS.md) — three real audits on BSC mainnet
(2026-11-14): a known-good free mint (DRIFTWIRE → GO 93), a transient-storage
mining contract (ONLYAI Mining → CAUTION 80), and a plain token control
(WBNB → GO 88). Each is reproducible with one command.
