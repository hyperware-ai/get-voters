#!/usr/bin/env python3
"""
Summarize DelegateChanged events on gHYPR and list non-self delegations.
"""

from __future__ import annotations

import argparse
import csv
import sys

from web3 import Web3

GHYPR_ADDRESS = "0x00000000004a50Daa1B759C47Ebf4239163aE5be"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

DELEGATE_CHANGED_SIGNATURE = "DelegateChanged(address,address,address)"


def _connect_rpc(rpc_url: str) -> Web3:
    if rpc_url.startswith("ws://") or rpc_url.startswith("wss://"):
        return Web3(Web3.LegacyWebSocketProvider(rpc_url))
    return Web3(Web3.HTTPProvider(rpc_url))


def _topic_to_address(topic: object) -> str | None:
    if isinstance(topic, bytes):
        topic_hex = topic.hex()
    elif isinstance(topic, str):
        topic_hex = topic[2:] if topic.startswith("0x") else topic
    else:
        return None
    if len(topic_hex) < 40:
        return None
    address = "0x" + topic_hex[-40:]
    if address == ZERO_ADDRESS:
        return None
    try:
        return Web3.to_checksum_address(address)
    except ValueError:
        return None


def _scan_delegate_changes(
    w3: Web3,
    contract_address: str,
    from_block: int,
    to_block: int,
    chunk_size: int,
) -> tuple[dict[str, str], set[str]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    delegates_by_account: dict[str, tuple[int, int, str]] = {}
    seen_accounts: set[str] = set()
    current = from_block
    checksum = Web3.to_checksum_address(contract_address)
    topic0 = Web3.keccak(text=DELEGATE_CHANGED_SIGNATURE).hex()
    while current <= to_block:
        end_chunk = min(current + chunk_size - 1, to_block)
        print(f"{current}-{end_chunk}", file=sys.stderr)
        logs = w3.eth.get_logs(
            {
                "address": checksum,
                "fromBlock": current,
                "toBlock": end_chunk,
                "topics": [topic0],
            }
        )
        for log in logs:
            log_topics = log.get("topics", [])
            if len(log_topics) < 4:
                continue
            delegator = _topic_to_address(log_topics[1])
            to_delegate = _topic_to_address(log_topics[3])
            if not delegator or not to_delegate:
                continue
            seen_accounts.add(delegator)
            block_number = int(log.get("blockNumber", 0))
            log_index = int(log.get("logIndex", 0))
            current_entry = delegates_by_account.get(delegator)
            if current_entry and (block_number, log_index) <= (
                current_entry[0],
                current_entry[1],
            ):
                continue
            delegates_by_account[delegator] = (block_number, log_index, to_delegate)
        next_block = end_chunk + 1
        if next_block <= current:
            raise RuntimeError("Chunking stalled; check from_block/chunk_size values")
        current = next_block
    latest_delegatees = {
        delegator: entry[2] for delegator, entry in delegates_by_account.items()
    }
    return latest_delegatees, seen_accounts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize DelegateChanged on gHYPR and list non-self delegations."
    )
    parser.add_argument(
        "--rpc",
        required=True,
        help="RPC URL (http/https) or WebSocket URL (ws/wss)",
    )
    parser.add_argument(
        "--from-block",
        type=int,
        default=36_283_831,
        help="Start block for log scanning fallback (default: 36_283_831)",
    )
    parser.add_argument(
        "--to-block",
        type=int,
        default=None,
        help="End block for log scanning fallback (default: latest)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=10_000,
        help="Block range chunk size for log scanning (default: 10_000)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="-",
        help="Output CSV file (default: stdout)",
    )
    args = parser.parse_args()

    w3 = _connect_rpc(args.rpc)
    if not w3.is_connected():
        print("Error: Could not connect to RPC", file=sys.stderr)
        return 1

    latest_block = w3.eth.block_number
    to_block = latest_block if args.to_block is None else args.to_block
    print("Fetching DelegateChanged events...", file=sys.stderr)
    try:
        latest_delegatees, seen_accounts = _scan_delegate_changes(
            w3, GHYPR_ADDRESS, args.from_block, to_block, args.chunk_size
        )
        if not latest_delegatees and args.chunk_size > 10_000:
            print(
                "No events found; retrying with chunk size 10_000",
                file=sys.stderr,
            )
            latest_delegatees, seen_accounts = _scan_delegate_changes(
                w3, GHYPR_ADDRESS, args.from_block, to_block, 10_000
            )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    total_addresses = len(seen_accounts)
    print(f"Found {total_addresses} addresses that called DelegateChanged", file=sys.stderr)
    if not latest_delegatees:
        print("No DelegateChanged events found", file=sys.stderr)
        return 1

    if args.output == "-":
        outfile = sys.stdout
    else:
        outfile = open(args.output, "w", newline="")

    writer = csv.DictWriter(outfile, fieldnames=["delegator", "delegatee"])
    writer.writeheader()

    non_self_count = 0
    for delegator, delegatee in sorted(latest_delegatees.items()):
        if delegatee.lower() == delegator.lower():
            continue
        non_self_count += 1
        writer.writerow({"delegator": delegator, "delegatee": delegatee})
    print(
        f"Non-self delegations: {non_self_count} (from {total_addresses} total)",
        file=sys.stderr,
    )

    if args.output != "-":
        outfile.close()
        print(f"Written to {args.output}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
