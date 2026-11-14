"""Public JSON-RPC + HTTPS client for MintGuard.

Standard library only. No API keys, no keyed endpoints — every URL here is a
public, unauthenticated endpoint. Transport tries ``curl`` first (the most
reliable path on flaky egress), then falls back to :mod:`urllib`.

Return conventions:
- ``rpc()`` returns ``(result, error)`` where ``error`` is None on success and
  a dict ``{"kind": ..., "detail": ...}`` otherwise. ``kind`` is one of:
  ``"revert"`` (the node executed the call and it reverted — a real answer),
  ``"rpc-error"`` (the node returned a non-revert JSON-RPC error),
  ``"transport"`` (every endpoint failed — retryable, not an answer).
  Callers MUST treat "revert" as evidence, not as a failure.
"""

import json
import subprocess
import urllib.error
import urllib.request

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

CHAINS = {
    "bsc": {
        "id": 56,
        "name": "BNB Smart Chain",
        "rpcs": [
            "https://bsc-dataseed.binance.org",
            "https://bsc-dataseed1.defibit.io",
            "https://bsc-rpc.publicnode.com",
            "https://bsc-mainnet.public.blastapi.io",
        ],
    },
    "eth": {
        "id": 1,
        "name": "Ethereum",
        "rpcs": ["https://ethereum.publicnode.com"],
    },
    "base": {
        "id": 8453,
        "name": "Base",
        "rpcs": ["https://base-mainnet.public.blastapi.io"],
    },
    "robinhood": {
        "id": 4663,
        "name": "Robinhood Chain",
        "rpcs": ["https://rpc.mainnet.chain.robinhood.com"],
    },
}

# EIP-1967 implementation slot.
IMPLEMENTATION_SLOT = (
    "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
)

WBNB = {
    "bsc": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
    "eth": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    "base": "0x4200000000000000000000000000000000000006",
}

PANCAKE_V2_FACTORY = "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73"


def _curl(args, timeout):
    """Run curl; return (stdout, ok). Never raises."""
    try:
        r = subprocess.run(
            ["curl", "-s", "--retry", "1", "--retry-delay", "1",
             "--retry-all-errors", "--max-time", str(timeout)] + args,
            capture_output=True, text=True, timeout=timeout + 10,
        )
        return r.stdout, r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return "", False


def http_get_json(url, timeout=8):
    """GET a URL and parse JSON. Returns (data, error_str)."""
    body, ok = _curl([url], timeout)
    if ok:
        try:
            return json.loads(body), None
        except Exception:
            pass
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")), None
    except Exception as e:  # noqa: BLE001 - transport is best-effort
        return None, f"GET {url}: {e}"


def http_post_json(url, payload, timeout=8):
    """POST a JSON body and parse the JSON reply. Returns (data, error_str)."""
    raw = json.dumps(payload)
    body, ok = _curl(
        ["-X", "POST", "-H", "Content-Type: application/json", "-d", raw, url],
        timeout,
    )
    if ok:
        try:
            return json.loads(body), None
        except Exception:
            pass
    try:
        req = urllib.request.Request(
            url, data=raw.encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")), None
    except Exception as e:  # noqa: BLE001 - transport is best-effort
        return None, f"POST {url}: {e}"


def rpc(chain, method, params, timeout=5, attempts=3):
    """One JSON-RPC call against the chain's public endpoints.

    Rotates endpoints across attempts. Returns ``(result, error)``.
    """
    cfg = CHAINS.get(chain)
    if cfg is None:
        return None, {"kind": "transport", "detail": f"unknown chain: {chain}"}
    last_err = None
    for i in range(attempts):
        url = cfg["rpcs"][i % len(cfg["rpcs"])]
        data, err = http_post_json(
            url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            timeout=timeout,
        )
        if err is not None:
            last_err = err
            continue
        if not isinstance(data, dict):
            last_err = f"bad reply: {str(data)[:120]}"
            continue
        if "result" in data and data["result"] is not None:
            return data["result"], None
        rpc_err = data.get("error") or {}
        code = rpc_err.get("code")
        msg = rpc_err.get("message", "")
        # Code 3 = execution reverted: the node answered; the call reverted.
        if code == 3 or "revert" in str(msg).lower():
            return None, {"kind": "revert", "detail": str(msg)[:300]}
        return None, {"kind": "rpc-error",
                      "detail": f"{code}: {str(msg)[:200]}"}
    return None, {"kind": "transport", "detail": str(last_err)[:300]}


def eth_block_number(chain):
    result, err = rpc(chain, "eth_blockNumber", [])
    if err is not None:
        return None
    try:
        return int(result, 16)
    except Exception:
        return None


def eth_get_code(chain, address):
    """Runtime bytecode hex, or None on transport failure."""
    result, err = rpc(chain, "eth_getCode", [address, "latest"])
    return result if err is None else None


def eth_get_storage_at(chain, address, slot):
    result, err = rpc(chain, "eth_getStorageAt", [address, slot, "latest"])
    return result if err is None else None


def eth_call(chain, to, data, value=0, from_address=ZERO_ADDRESS):
    """Simulated call (read-only, never broadcast).

    Returns ``{"status": ..., "raw": hex|None, "reason": str|None}`` where
    status is "ok" (returned data), "empty" (0x — function almost certainly
    absent), "revert" (the call reverted — reason captured when the node
    gives one), or "transport" (no endpoint answered).
    """
    tx = {"to": to, "data": data, "from": from_address}
    if value:
        tx["value"] = hex(value)
    result, err = rpc(chain, "eth_call", [tx, "latest"])
    if err is None:
        if not result or result in ("0x", "0x0"):
            return {"status": "empty", "raw": result, "reason": None}
        return {"status": "ok", "raw": result, "reason": None}
    if err["kind"] == "revert":
        return {"status": "revert", "raw": None, "reason": err["detail"]}
    return {"status": "transport", "raw": None, "reason": err["detail"]}


def decode_uint(raw):
    if not raw or raw in ("0x", "0x0"):
        return None
    try:
        return int(raw, 16)
    except Exception:
        return None


def decode_address(raw):
    if not raw or raw in ("0x", "0x0"):
        return None
    try:
        n = int(raw, 16)
    except Exception:
        return None
    if n == 0:
        return "0x0000000000000000000000000000000000000000"
    return "0x" + format(n, "040x")


def decode_bool(raw):
    v = decode_uint(raw)
    return None if v is None else bool(v)


def decode_string(raw):
    """ABI-encoded string, or None."""
    if not raw or raw in ("0x", "0x0"):
        return None
    try:
        b = bytes.fromhex(raw[2:] if raw.startswith("0x") else raw)
        if len(b) < 64:
            return None
        ln = int.from_bytes(b[32:64], "big")
        return b[64:64 + ln].decode("utf-8", "replace")
    except Exception:
        return None
