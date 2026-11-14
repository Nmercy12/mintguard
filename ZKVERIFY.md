# MintGuard — zkVerify angle (optional, Agent Games Wildcard submission)

## The checkable claim

MintGuard's core claim is deliberately boring — and that is the point:

> **"This contract's audit verdict is reproducible from public data."**

Every report MintGuard returns carries everything needed to re-derive it:

- the **chain and address** audited,
- the **block number** the reads were pinned to,
- the **exact check results** (bytecode size and TSTORE/TLOAD counts, Sourcify
  match status, owner/pause/supply values, price-function answers, dry-run
  outcome, market data),
- and the **deterministic scoring rubric** (`mintguard/audit.py`, documented
  in the module docstring).

Anyone can re-run the same public reads at the same block and must get the
same verdict — or the discrepancy itself is evidence that something changed
or that the agent is wrong. That is a checkable claim in the zkVerify sense:
a statement about the world with a defined verification procedure, even
before any proof system is involved.

## What zkVerify would add (future work — NOT implemented)

Two directions would strengthen the claim, and both are honest future work,
not present capability:

1. **zkTLS attestation of the evidence.** The reads MintGuard relies on are
   HTTPS responses (Sourcify, DexScreener, public RPCs). A zkTLS proof could
   turn "the agent says Sourcify returned exact_match" into "here is a proof
   that, at this time, Sourcify's HTTPS response for this address said
   exact_match" — without revealing anything else. That is exactly the
   "prove what your agent saw on the web" direction in the Wildcard brief.
2. **A Groth16 proof of correct verdict computation.** The scoring rubric is
   a small deterministic function over the evidence. Compiling it to a circuit
   (Circom) would let the agent attach a proof that "this verdict follows
   from this evidence under the published rubric" — verifiable on zkVerify
   mainnet, so a third party never has to trust the agent's server.

## What is NOT claimed

- **No proof reference exists today.** MintGuard ships no zkVerify proof, no
  `vk_hash`, no attestation. The submission form's zkVerify field is optional
  precisely because agents without zkVerify remain eligible — and inventing a
  proof reference would be fraud, not a feature.
- **Reproducibility is not the same as truth.** Re-running the reads proves
  the verdict follows from the evidence; it does not prove the evidence
  itself is complete (e.g. a hidden mint path inside verified source is a
  limitation of the checks, documented in the README).

## Why this framing

The Wildcard track rewards a *useful* agent with a *clear* explanation of
what it can and cannot do. MintGuard's verifiability story is therefore
stated as it is: reproducible today, provable tomorrow, with the exact
upgrade path named and no proof faked in the meantime.
