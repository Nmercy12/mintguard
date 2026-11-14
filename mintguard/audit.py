"""MintGuard audit engine.

Turns one ``(chain, address)`` into a structured safety verdict for a
free-mint hunter. Every claim in the report is backed by a public, replayable
on-chain read (or a public HTTPS API with no key). Nothing here is simulated
against a private node, and nothing is broadcast.

Verdict semantics — the question being answered is
"should a free-mint hunter mint this, right now?":
- GO       — free path exists, source verified, no blocking finding.
- CAUTION  — mintable, but something material is unknown, gated, or risky.
- BLOCK    — do not mint: not a contract, not free, sold out, closed,
             honeypot, or otherwise unsafe for this purpose.

Scoring (deterministic, documented; tightest hard cap wins):
- start 100
- no verified source .......... -25 (Sourcify: no match at all)
- source "match" only .......... -10 (not exact_match)
- EIP-1153 transient storage .. -15 (Binance-wallet writes revert; the
                                     per-function path via EOA/manual may
                                     still work — reported, not assumed)
- live owner .................. -5  (rules can still change)
- owner model unknown ......... -2
- paused ...................... -15
- mint price unknown .......... -10
- dry-run reverts unclearly .... -5
- reward token has no market .. -5  (the reward cannot be valued)
- track unclassifiable ........ -10
- NFT supply uncapped ......... -5
Hard caps (verdict BLOCK regardless of score):
- no code at the address, honeypot, not free, sold out, mint closed.
"""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from .keccak import selector
from .rpc import (
    CHAINS,
    PANCAKE_V2_FACTORY,
    WBNB,
    ZERO_ADDRESS,
    decode_address,
    decode_bool,
    decode_string,
    decode_uint,
    eth_block_number,
    eth_call,
    eth_get_code,
    eth_get_storage_at,
    http_get_json,
    rpc,
)

VERSION = "MintGuard/1.0"

# Function selectors we probe by name (computed with Keccak-256).
SEL = {
    "owner()": "0x8da5cb5b",
    "paused()": "0x5c975abb",
    "totalSupply()": "0x18160ddd",
    "maxSupply()": "0xd5abeb01",
    "MAX_SUPPLY()": None,  # computed below
    "name()": "0x06fdde03",
    "symbol()": "0x95d89b41",
    "ownerOf(uint256)": "0x6352211e",
    "tokenURI(uint256)": "0xc87b56dd",
    "PRICE()": None,
    "mintPrice()": None,
    "cost()": None,
    "mintOpen()": None,
    "freeLeft()": None,
    "freeUsedByWallet(address)": None,
    "TOKEN()": None,
    "mint(uint256)": "0xa0712d68",
    "mint()": "0x1249c58b",
    "getPair(address,address)": "0xe6a43905",
    "getReserves()": "0x0902f1ac",
}
for _sig in list(SEL):
    if SEL[_sig] is None:
        SEL[_sig] = selector(_sig)

PRICE_FNS = ["PRICE()", "mintPrice()", "cost()", "price()"]
FREE_FN_PREFIXES = ("free", "claim")
MINT_FNS = ("mint(", "freeMint", "claimMint", "publicMint")
EIP1967_IMPL = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"


def count_transient(code_hex):
    """Count real TSTORE (0x5c) / TLOAD (0x5d) opcodes, skipping PUSH data."""
    if not code_hex or code_hex in ("0x", "0x0"):
        return 0, 0, 0
    b = bytes.fromhex(code_hex[2:] if code_hex.startswith("0x") else code_hex)
    tstore = tload = 0
    i = 0
    while i < len(b):
        op = b[i]
        if op == 0x5C:
            tstore += 1
        elif op == 0x5D:
            tload += 1
        if 0x60 <= op <= 0x7F:  # PUSH1..PUSH32: skip immediate bytes
            i += 1 + (op - 0x5F)
        else:
            i += 1
    return tstore, tload, len(b)


def _addr_arg(address):
    return "0" * 24 + address.lower().replace("0x", "")


def _uint_arg(n):
    return format(n, "064x")


def fetch_sourcify(chain_id, address):
    """Source-verification status + ABI from Sourcify (no key).

    Returns {"match": "exact_match"|"match"|None, "abi": [...]|None}.
    """
    base = f"https://sourcify.dev/server/v2/contract/{chain_id}/{address.lower()}"
    out = {"match": None, "abi": None}
    data, err = http_get_json(base, timeout=12)
    if err is None and isinstance(data, dict):
        out["match"] = (
            data.get("stdJson", {}).get("match") or data.get("match")
        )
    data, err = http_get_json(base + "?fields=abi", timeout=12)
    if err is None and isinstance(data, dict) and isinstance(data.get("abi"), list):
        out["abi"] = data["abi"]
    return out


def fetch_dexscreener(address):
    """Token pairs from DexScreener (public, no key). Returns list or None."""
    data, err = http_get_json(
        f"https://api.dexscreener.com/latest/dex/tokens/{address.lower()}",
        timeout=10,
    )
    if err is not None or not isinstance(data, dict):
        return None
    pairs = data.get("pairs")
    if not pairs:
        return []
    out = []
    for p in pairs:
        liq = (p.get("liquidity") or {}).get("usd")
        out.append({
            "dex": p.get("dexId"),
            "pair": p.get("pairAddress"),
            "price_usd": p.get("priceUsd"),
            "liquidity_usd": liq,
            "volume_h24": (p.get("volume") or {}).get("h24"),
        })
    out.sort(key=lambda x: (x["liquidity_usd"] or 0), reverse=True)
    return out


def fetch_honeypot(chain_id, address):
    """Honeypot check (public, no key, BSC only). Best-effort: None = unknown."""
    if chain_id != 56:
        return None
    data, err = http_get_json(
        "https://api.honeypot.is/v2/IsHoneypot"
        f"?address={address.lower()}&chainID=56",
        timeout=10,
    )
    if err is not None or not isinstance(data, dict):
        return None
    try:
        sim = data.get("simulationResult") or {}
        hp = data.get("honeypotResult") or {}
        return {
            "is_honeypot": hp.get("isHoneypot"),
            "buy_tax": sim.get("buyTax"),
            "sell_tax": sim.get("sellTax"),
        }
    except Exception:
        return None


def abi_function_names(abi):
    if not abi:
        return []
    return [e.get("name") for e in abi
            if e.get("type") == "function" and e.get("name")]


def classify_track(fn_names, owner_of_works):
    """nft_mint | token | mining | unknown — from ABI shape + probes."""
    names = set(fn_names or [])
    has_mint = any(n.startswith("mint") or n.startswith("freeMint")
                   for n in names)
    has_owner_of = "ownerOf" in names or owner_of_works
    has_token_fns = bool({"transfer", "balanceOf", "totalSupply"} & names)
    has_mining = bool({"activate", "claim", "stake", "deposit"} & names) and \
        bool({"pendingReward", "accrued", "rewardPerToken", "nft", "token"} & names)
    if has_mining and not has_mint:
        return "mining"
    if has_mint and has_owner_of:
        return "nft_mint"
    if has_token_fns and not has_owner_of:
        return "token"
    if has_mint:
        return "nft_mint"
    if has_token_fns:
        return "token"
    return "unknown"


def _probe(chain, address, sig, args=""):
    """Single view call. Returns {"status","value","raw","reason"} with a
    decoded value (uint/address/bool/string/tuple as appropriate)."""
    data = SEL[sig] + args if sig in SEL else None
    if data is None:
        data = selector(sig) + args
    res = eth_call(chain, address, data)
    out = {"status": res["status"], "raw": res["raw"], "reason": res["reason"],
           "value": None}
    if res["status"] != "ok":
        return out
    raw = res["raw"]
    fname = sig.split("(")[0]
    if fname in ("owner", "TOKEN") or sig.startswith("ownerOf("):
        out["value"] = decode_address(raw)
    elif fname in ("paused", "mintOpen"):
        out["value"] = decode_bool(raw)
    elif fname in ("name", "symbol"):
        out["value"] = decode_string(raw)
    elif fname == "freeLeft":
        try:
            b = bytes.fromhex(raw[2:])
            out["value"] = [int.from_bytes(b[32 * i:32 * i + 32], "big")
                            for i in range(len(b) // 32)]
        except Exception:
            out["value"] = None
    else:
        out["value"] = decode_uint(raw)
    return out


def audit(chain, address):
    """Run the full audit. Returns the report dict (never raises)."""
    started = time.time()
    chain = (chain or "bsc").lower()
    cfg = CHAINS.get(chain)
    if cfg is None:
        return {"verdict": "BLOCK", "score": 0,
                "error": f"unsupported chain: {chain}",
                "supported_chains": sorted(CHAINS)}
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", address or ""):
        return {"verdict": "BLOCK", "score": 0,
                "error": f"invalid address: {address}"}
    address = "0x" + address[2:].lower() if address.startswith(("0x", "0X")) \
        else "0x" + address.lower()
    # Checksummed display is unnecessary; keep lowercase consistently.
    address = address.lower()
    chain_id = cfg["id"]

    report = {
        "agent": VERSION,
        "chain": chain,
        "chain_id": chain_id,
        "address": address,
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "block": None,
        "track": "unknown",
        "verdict": "CAUTION",
        "score": 0,
        "free": None,
        "free_gated": None,
        "paid_price_wei": None,
        "checks": {},
        "findings": [],
        "evidence": [],
        "limitations": [
            "Bytecode-level scan only: a selector in bytecode is not proof a "
            "feature is live; findings are confirmed against the verified "
            "ABI when source is available.",
            "EIP-1153 is a contract-level signal, not a per-function verdict: "
            "a flagged contract may still have working functions that never "
            "touch transient storage.",
            "No private RPCs, no paid APIs, no simulation against a fork — "
            "all reads are public endpoints at the pinned block.",
        ],
    }

    def note(level, code, message):
        report["findings"].append(
            {"level": level, "code": code, "message": message})

    # ---- Phase 1: independent reads, in parallel -------------------------
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {
            ex.submit(eth_block_number, chain): "block",
            ex.submit(eth_get_code, chain, address): "code",
            ex.submit(eth_get_storage_at, chain, address, EIP1967_IMPL): "proxy",
            ex.submit(fetch_sourcify, chain_id, address): "sourcify",
            ex.submit(fetch_dexscreener, address): "dex",
        }
        done = {}
        for f in as_completed(futs):
            try:
                done[futs[f]] = f.result()
            except Exception as e:  # noqa: BLE001 - one failed probe must not kill the audit
                done[futs[f]] = None
                note("info", "probe_error", f"{futs[f]} probe failed: {e}")

    report["block"] = done.get("block")
    code = done.get("code")
    if code is None:
        report["verdict"] = "BLOCK"
        report["score"] = 0
        note("critical", "rpc_unavailable",
             "Public RPCs did not answer; audit could not run. Retry later.")
        return report
    if code in ("0x", "0x0", ""):
        report["verdict"] = "BLOCK"
        report["score"] = 0
        report["checks"]["code"] = {"exists": False, "size_bytes": 0}
        note("critical", "no_code", "Address has no contract code.")
        return report

    # ---- Proxy resolution -------------------------------------------------
    impl = None
    proxy_slot = done.get("proxy")
    if proxy_slot:
        cand = decode_address(proxy_slot)
        if cand and cand != ZERO_ADDRESS and cand != address:
            impl = cand
    scan_target = impl or address
    tstore, tload, size = count_transient(
        code if scan_target == address else
        (eth_get_code(chain, impl) or "0x"))
    report["checks"]["code"] = {
        "exists": True, "size_bytes": size,
        "proxy": bool(impl), "implementation": impl,
        "scanned": scan_target,
    }
    report["evidence"].append(f"eth_getCode {address} @ block {report['block']}")

    # ---- EIP-1153 ---------------------------------------------------------
    eip1153_blocked = bool(tstore or tload)
    report["checks"]["eip1153"] = {
        "tstore": tstore, "tload": tload,
        "blocked_for_baw": eip1153_blocked,
        "scanned": scan_target,
    }
    if eip1153_blocked:
        note("warn", "eip1153",
             f"Transient storage present (TSTORE={tstore}, TLOAD={tload}) on "
             f"{scan_target}: Binance Agentic Wallet writes will revert in "
             "preview; EOA/manual paths may still work per-function.")

    # ---- Source verification + ABI ---------------------------------------
    src = done.get("sourcify") or {}
    match = src.get("match")
    abi = src.get("abi")
    report["checks"]["source"] = {
        "sourcify_match": match, "abi_available": bool(abi),
    }
    if match == "exact_match":
        pass
    elif match == "match":
        note("warn", "source_partial",
             "Source is a partial Sourcify match, not exact_match: the ABI "
             "was borrowed while bytecode may differ in constants.")
    else:
        note("warn", "source_unverified",
             "No verified source on Sourcify: mint mechanics cannot be "
             "confirmed from code; all findings are bytecode-level only.")

    fn_names = abi_function_names(abi)
    report["checks"]["abi_functions"] = fn_names[:60]

    # ---- Phase 2: view probes, in parallel -------------------------------
    probes = {}

    def run_probe(name, sig, args=""):
        probes[name] = _probe(chain, address, sig, args)

    with ThreadPoolExecutor(max_workers=8) as ex:
        jobs = [
            ("owner", "owner()"),
            ("paused", "paused()"),
            ("total_supply", "totalSupply()"),
            ("max_supply", "maxSupply()"),
            ("MAX_SUPPLY", "MAX_SUPPLY()"),
            ("name", "name()"),
            ("symbol", "symbol()"),
            ("mint_open", "mintOpen()"),
            ("free_left", "freeLeft()"),
            ("reward_token", "TOKEN()"),
        ]
        for name, sig in jobs:
            ex.submit(run_probe, name, sig)
        # Price functions, in priority order.
        for sig in PRICE_FNS:
            ex.submit(run_probe, "price_" + sig, sig)
        # ownerOf(1) tells us NFT-vs-token even without an ABI.
        ex.submit(run_probe, "owner_of_1", "ownerOf(uint256)", _uint_arg(1))

    owner_of_works = probes.get("owner_of_1", {}).get("status") == "ok"
    track = classify_track(fn_names, owner_of_works)
    report["track"] = track

    # ---- Owner / pause / supply ------------------------------------------
    owner = probes["owner"]
    if owner["status"] == "ok":
        report["checks"]["owner"] = {"address": owner["value"],
                                     "renounced": owner["value"] == "0x" + "0" * 40}
        if report["checks"]["owner"]["renounced"]:
            note("info", "owner_renounced", "owner() is the zero address: "
                 "onlyOwner functions are inert.")
        else:
            note("info", "owner_live",
                 f"Live owner {owner['value']}: contract rules can still change.")
    else:
        report["checks"]["owner"] = {"address": None,
                                     "renounced": None,
                                     "status": owner["status"]}
        note("info", "owner_unknown",
             "No owner() value: ownership model cannot be confirmed from "
             "standard probes (may use a signer/registry instead).")

    if probes["paused"]["status"] == "ok" and probes["paused"]["value"]:
        note("warn", "paused", "Contract is currently paused.")
    report["checks"]["paused"] = probes["paused"]["value"]

    ts = probes["total_supply"]["value"]
    ms = probes["max_supply"]["value"]
    if ms is None:
        ms = probes["MAX_SUPPLY"]["value"]
    report["checks"]["supply"] = {"total_supply": ts, "max_supply": ms}
    if ts is not None and ms:
        report["checks"]["supply"]["sold_out"] = ts >= ms
    if track == "nft_mint" and ms is None:
        note("info", "supply_uncapped",
             "No maxSupply found: supply may be uncapped.")

    name = probes["name"]["value"]
    symbol = probes["symbol"]["value"]
    if name or symbol:
        report["checks"]["identity"] = {"name": name, "symbol": symbol}

    # ---- Mint price / free path ------------------------------------------
    price_wei = None
    for sig in PRICE_FNS:
        v = probes.get("price_" + sig, {}).get("value")
        if isinstance(v, int):
            price_wei = v
            report["checks"]["price_function"] = sig
            break
    report["paid_price_wei"] = price_wei

    free_fns = [n for n in fn_names
                if n.lower().startswith("free") or n.lower().startswith("claim")]
    report["checks"]["free_functions"] = free_fns
    mint_open = probes["mint_open"]["value"]
    report["checks"]["mint_open"] = mint_open
    if mint_open is False:
        note("warn", "mint_closed", "mintOpen() is false: the mint window "
             "is closed right now.")

    if track == "nft_mint":
        if free_fns:
            report["free"] = True
            # Signature-gated if the free function takes a signature/bytes arg.
            report["free_gated"] = any(
                "bytes" in str(e.get("inputs", "")) for e in (abi or [])
                if (e.get("name") or "").lower().startswith("free")) or \
                any(n in ("freeMintX", "freeMintWithSig", "freeMintAllowlist")
                    for n in free_fns)
            fl = probes["free_left"]["value"]
            if isinstance(fl, list) and len(fl) >= 1:
                report["checks"]["free_left"] = fl
        elif price_wei == 0:
            report["free"] = True
            report["free_gated"] = False
        elif price_wei is None:
            report["free"] = None
            note("info", "price_unknown",
                 "No price function answered: free vs paid cannot be "
                 "confirmed from standard probes.")
        else:
            report["free"] = False

    # ---- Dry-run: mint with zero value --------------------------------------
    # Find the mint entry in the ABI and dry-run the shape it actually takes.
    dry = None
    mint_entry = next((e for e in (abi or [])
                       if e.get("type") == "function"
                       and e.get("name") == "mint"), None)
    if track == "nft_mint" and mint_entry is not None:
        inputs = [i.get("type") for i in mint_entry.get("inputs", [])]
        if inputs == ["uint256"]:
            dry = eth_call(chain, address,
                           SEL["mint(uint256)"] + _uint_arg(1), value=0)
            report["checks"]["dry_run_mint1_zero_value"] = {
                "status": dry["status"], "reason": dry["reason"]}
        elif inputs == []:
            dry = eth_call(chain, address, SEL["mint()"], value=0)
            report["checks"]["dry_run_mint_zero_value"] = {
                "status": dry["status"], "reason": dry["reason"]}
        else:
            report["checks"]["dry_run"] = {
                "status": "skipped",
                "reason": f"mint takes ({','.join(inputs)}); no safe "
                          "zero-value dry-run shape."}
        if dry is not None:
            if dry["status"] == "ok":
                note("info", "dry_run_free",
                     "Dry-run mint with 0 value succeeded: this mint path "
                     "is free at zero value.")
            elif dry["status"] == "revert":
                if price_wei:
                    note("info", "dry_run_revert",
                         "Dry-run mint with 0 value reverted as expected: "
                         f"the paid gate is enforced (price {price_wei} wei).")
                else:
                    note("info", "dry_run_revert",
                         f"Dry-run mint with 0 value reverted: {dry['reason']}")

    # ---- Market / honeypot -------------------------------------------------
    dex = done.get("dex")
    report["checks"]["market"] = {"pairs": dex if dex is not None else "unknown"}
    reward_token = probes["reward_token"]["value"]
    reward_pairs = None
    if reward_token and reward_token != "0x" + "0" * 40:
        reward_pairs = fetch_dexscreener(reward_token)
        report["checks"]["reward_token"] = {
            "address": reward_token, "pairs": reward_pairs}
    if track == "token":
        hp = fetch_honeypot(chain_id, address)
        report["checks"]["honeypot"] = hp
        if hp and hp.get("is_honeypot"):
            note("critical", "honeypot",
                 "Honeypot check flags this token: selling may be blocked.")
        elif hp and (hp.get("sell_tax") or 0) > 25:
            note("critical", "sell_tax",
                 f"Sell tax {hp['sell_tax']}% is punitive.")
    if track == "nft_mint" and reward_token and reward_pairs == []:
        note("info", "reward_unvalued",
             "Reward token has no DEX pair yet: the mint reward cannot be "
             "valued from market data.")

    # ---- Score + verdict ---------------------------------------------------
    score = 100
    hard_block = None

    if match is None:
        score -= 25
    elif match == "match":
        score -= 10
    if eip1153_blocked:
        score -= 15
    if owner["status"] == "ok" and not report["checks"]["owner"]["renounced"]:
        score -= 5
    elif owner["status"] != "ok":
        score -= 2
    if probes["paused"]["value"]:
        score -= 15
    if track == "nft_mint" and price_wei is None and not free_fns:
        score -= 10
    if dry and dry["status"] == "revert" and price_wei in (None, 0):
        score -= 5
    if track == "nft_mint" and reward_token and reward_pairs == []:
        score -= 5
    if track == "unknown":
        score -= 10
    if track == "nft_mint" and ms is None:
        score -= 5

    if track == "nft_mint":
        if report["checks"]["supply"].get("sold_out"):
            hard_block = "sold_out: totalSupply has reached maxSupply."
        elif mint_open is False:
            hard_block = "mint_closed: mintOpen() is false."
        elif report["free"] is False:
            hard_block = ("not_free: no free-mint path found; paid price is "
                          f"{price_wei} wei.")
    hp = report["checks"].get("honeypot") or {}
    if hp.get("is_honeypot"):
        hard_block = "honeypot: selling is blocked."
    elif isinstance(hp.get("sell_tax"), (int, float)) and hp["sell_tax"] > 25:
        hard_block = f"sell_tax: {hp['sell_tax']}% sell tax."

    if hard_block:
        score = min(score, 45)
        report["verdict"] = "BLOCK"
        note("critical", "block", hard_block)
    elif score >= 85:
        report["verdict"] = "GO"
    elif score >= 55:
        report["verdict"] = "CAUTION"
    else:
        report["verdict"] = "BLOCK"
    report["score"] = max(0, min(100, score))
    report["elapsed_seconds"] = round(time.time() - started, 2)
    return report


def audit_json(chain, address):
    return json.dumps(audit(chain, address), indent=2)
