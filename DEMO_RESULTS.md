# MintGuard — demo audit results

Real audits run against live BSC mainnet on **2026-11-14** (all times UTC).
Nothing here is fabricated: every number below comes from the audit report
itself, produced by `python3 -m mintguard <address> --chain bsc` at the
pinned block shown. Re-run any of them to reproduce the verdict.

| Contract | Track | Verdict | Score | Block | Took |
|---|---|---|---|---|---|
| DRIFTWIRE `0x485b…44b0` | nft_mint | **GO** | 93 | 133571423 | 10.05s |
| ONLYAI Mining `0x4948…484e` | mining | **CAUTION** | 80 | 133571444 | 9.97s |
| WBNB `0xbb4c…095c` | token | **GO** | 88 | 133571467 | 11.08s |

## 1. DRIFTWIRE — GO 93/100 (known-good free mint)

`0x485be9daa4620fcee4e2baed7cc85ea57acb44b0` — BSC 56, block 133571423.

- **Identity:** DRIFTWIRE / DRIFT. Supply 1,462 / 5,555 (`MAX_SUPPLY()`), not sold out.
- **EIP-1153:** CLEAN — TSTORE=0, TLOAD=0, 17,979 bytes. Binance-wallet writes can be attempted.
- **Source:** Sourcify `exact_match`, ABI available.
- **Mint:** `mintOpen()` true. Paid price `PRICE()` = 0.0015 BNB. **Free path exists:** `freeMintX` / `freeMintXWithRef` (signature-gated — needs an X/Twitter signature), `freeLeft()` = [539, 200] free mints remaining.
- **Dry-run:** `mint(1)` with 0 value reverts as expected — the paid gate is enforced (custom error `0xb23bee05…`).
- **Reward:** `TOKEN()` = WIRE `0x07683f74…0f41`; DexScreener reports **no pair yet**, so the reward cannot be valued from market data.
- **Owner:** no `owner()` function — access control runs through `xSigner`/`REGISTRY`, not a standard owner.
- **Deductions:** owner model unknown −2, reward unvalued −5 → 93. No hard cap fired.

Manual cross-check (outside the agent, same day): `claimable(baw wallet)` =
10,000 WIRE exactly, matching the known 10,000 WIRE reward for DRIFTWIRE #624.

## 2. ONLYAI Mining — CAUTION 80/100 (transient storage, live owner)

`0x49489165f9F4DaF87f683A9023496D764FD7484E` — BSC 56, block 133571444.

- **Track:** mining/staking contract (`activate()`, `claim()`, `pendingReward()`), not an NFT mint. No name/symbol/totalSupply — correctly classified, not forced into the mint track.
- **EIP-1153:** BLOCKED — TSTORE=0, **TLOAD=2**, 5,711 bytes. Binance-wallet writes revert in preview. The report states the honest nuance: this is a contract-level signal, not a per-function verdict — `activate()`/`claim()` were previously observed working via other paths.
- **Source:** Sourcify `exact_match`, ABI available.
- **Owner:** live, `0xb42c7313f40acd7c08c24cd5ffac898c85de8cc6`, not renounced.
- **Deductions:** transient storage −15, live owner −5 → 80. No hard cap fired.

## 3. WBNB — GO 88/100 (control: a plain token, not a mint)

`0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c` — BSC 56, block 133571467.

- **Track:** token (BEP-20). Correctly *not* treated as a mint: no mint functions, no `ownerOf`.
- **Identity:** Wrapped BNB / WBNB. totalSupply ≈ 1,568,037 WBNB (live, changes as people wrap/unwrap).
- **EIP-1153:** CLEAN — TSTORE=0, TLOAD=0, 3,124 bytes.
- **Source:** Sourcify `match` only (not `exact_match`) — the ABI was borrowed while bytecode may differ in constants.
- **Honeypot:** honeypot.is says **not a honeypot**, buy tax 0%, sell tax 0%.
- **Market:** top pair PancakeSwap `0x16b9…0daE`, price ≈ $597.88, liquidity ≈ $35.07M, 24h volume ≈ $4.74M.
- **Deductions:** source partial −10, owner model unknown −2 → 88. No hard cap fired.

## What the demo proves

- The agent distinguishes a **real free mint** (DRIFTWIRE: free path found in the ABI, not guessed from a price function) from a **mining contract** (ONLYAI) and a **plain token** (WBNB) — track classification comes from ABI shape + probes, not from the address.
- It catches the **EIP-1153** signal with a correct disassembly (PUSH data skipped) and reports it as a wallet-compatibility finding with the per-function caveat, not as a scam verdict.
- It reads the **actual mint mechanics from the verified ABI** (DRIFTWIRE's `freeMintX` vs paid `mint`), including the signature gate and the remaining free quota — instead of assuming "PRICE() > 0 means not free".
- Every verdict is **replayable**: the report carries the block number, the chain, and the evidence for each check. Re-run the same command at a later block and the numbers move only if the chain state moved.

## How to reproduce

```bash
git clone https://github.com/Nmercy12/mintguard.git
cd mintguard
python3 -m mintguard 0x485be9daa4620fcee4e2baed7cc85ea57acb44b0 --chain bsc
python3 -m mintguard 0x49489165f9F4DaF87f683A9023496D764FD7484E --chain bsc
python3 -m mintguard 0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c --chain bsc
# or start the demo server: python3 server.py  ->  http://127.0.0.1:8000/
```

Reference only, not investment advice.
