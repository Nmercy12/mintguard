"""MintGuard CLI: python -m mintguard <address> [--chain bsc]"""

import argparse
import json
import sys

from .audit import audit


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="mintguard",
        description="Audit an EVM contract for free-mint safety.",
    )
    p.add_argument("address", help="contract address, e.g. 0x485b...")
    p.add_argument("--chain", default="bsc",
                   choices=["bsc", "eth", "base", "robinhood"],
                   help="chain (default: bsc)")
    p.add_argument("--compact", action="store_true",
                   help="print a one-line verdict instead of full JSON")
    args = p.parse_args(argv)
    report = audit(args.chain, args.address)
    if args.compact:
        print(f"{report.get('verdict')} score={report.get('score')} "
              f"track={report.get('track')} free={report.get('free')} "
              f"addr={report.get('address')} block={report.get('block')}")
        return 0
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
