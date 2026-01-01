#!/usr/bin/env python3
"""
Fetch all votes with reasons for a DAO proposal and output as CSV.

Uses OpenZeppelin Governor standard interface.
"""

import argparse
import csv
import sys
from web3 import Web3

# Default DAO address on Base
DEFAULT_DAO_ADDRESS = "0x000000000048395579c3C60f2F8Cb2DECa457550"

# OpenZeppelin Governor ABI (minimal subset needed)
GOVERNOR_ABI = [
    {
        "inputs": [{"name": "proposalId", "type": "uint256"}],
        "name": "proposalSnapshot",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "proposalId", "type": "uint256"}],
        "name": "proposalDeadline",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# Vote event signatures (both have the same data layout)
# event VoteCast(address indexed voter, uint256 proposalId, uint8 support, uint256 weight, string reason)
# event VoteCastWithReason(address indexed voter, uint256 proposalId, uint8 support, uint256 weight, string reason)
VOTE_CAST_TOPIC = Web3.keccak(
    text="VoteCast(address,uint256,uint8,uint256,string)"
)
VOTE_CAST_WITH_REASON_TOPIC = Web3.keccak(
    text="VoteCastWithReason(address,uint256,uint8,uint256,string)"
)


def _find_block_at_or_after_timestamp(w3: Web3, target_ts: int, latest_block: int) -> int:
    """Binary search the first block whose timestamp is >= target_ts."""
    low = 0
    high = latest_block

    while low < high:
        mid = (low + high) // 2
        mid_ts = w3.eth.get_block(mid).timestamp
        if mid_ts < target_ts:
            low = mid + 1
        else:
            high = mid

    return low


def _find_block_at_or_before_timestamp(w3: Web3, target_ts: int, latest_block: int) -> int:
    """Binary search the last block whose timestamp is <= target_ts."""
    low = 0
    high = latest_block

    while low < high:
        mid = (low + high + 1) // 2
        mid_ts = w3.eth.get_block(mid).timestamp
        if mid_ts <= target_ts:
            low = mid
        else:
            high = mid - 1

    return low


def get_proposal_block_range(
    w3: Web3, dao_address: str, proposal_id: int
) -> tuple[int, int, bool]:
    """Get the voting start and end blocks for a proposal."""
    dao = w3.eth.contract(address=Web3.to_checksum_address(dao_address), abi=GOVERNOR_ABI)

    start_block = dao.functions.proposalSnapshot(proposal_id).call()
    end_block = dao.functions.proposalDeadline(proposal_id).call()

    latest_block = w3.eth.block_number
    latest_ts = w3.eth.get_block(latest_block).timestamp
    deadline_in_future = False

    # Some governors use timestamps instead of block numbers (clock-based voting).
    if start_block > latest_block or end_block > latest_block:
        start_ts = start_block
        end_ts = end_block

        if start_ts > latest_ts:
            start_block = latest_block
        else:
            start_block = _find_block_at_or_after_timestamp(w3, start_ts, latest_block)

        if end_ts > latest_ts:
            end_block = latest_block
            deadline_in_future = True
        else:
            end_block = _find_block_at_or_before_timestamp(w3, end_ts, latest_block)

    return start_block, end_block, deadline_in_future


def decode_vote_log(log, proposal_id: int) -> dict | None:
    """Decode a VoteCast or VoteCastWithReason log entry."""
    # Topic 1: voter address (indexed)
    voter = "0x" + log["topics"][1].hex()[-40:]

    # Decode non-indexed data: proposalId, support, weight, reason
    data = log["data"]
    if isinstance(data, str):
        data = bytes.fromhex(data[2:])

    # proposalId is uint256 (32 bytes)
    log_proposal_id = int.from_bytes(data[0:32], "big")

    # Skip if not our proposal
    if log_proposal_id != proposal_id:
        return None

    # support is uint8 but padded to 32 bytes
    support = int.from_bytes(data[32:64], "big")

    # weight is uint256 (32 bytes)
    weight = int.from_bytes(data[64:96], "big")

    # reason is dynamic string: offset at bytes 96-128, then length and data
    reason_offset = int.from_bytes(data[96:128], "big")
    reason_length = int.from_bytes(data[reason_offset : reason_offset + 32], "big")
    reason = data[reason_offset + 32 : reason_offset + 32 + reason_length].decode(
        "utf-8", errors="replace"
    )

    # Only include votes that have a reason
    if not reason.strip():
        return None

    return {
        "address": Web3.to_checksum_address(voter),
        "reason": reason,
        "weight": weight,
    }


def get_votes_with_reason(
    w3: Web3, dao_address: str, proposal_id: int, from_block: int, to_block: int
) -> list[dict]:
    """Fetch all VoteCast and VoteCastWithReason events for a proposal."""
    votes = []
    seen = set()  # Dedupe by address

    # Query each event type separately for better RPC compatibility
    for topic in [VOTE_CAST_TOPIC, VOTE_CAST_WITH_REASON_TOPIC]:
        chunk_size = 10000
        current_block = from_block

        while current_block <= to_block:
            end_chunk = min(current_block + chunk_size - 1, to_block)

            logs = w3.eth.get_logs(
                {
                    "address": Web3.to_checksum_address(dao_address),
                    "topics": [topic],
                    "fromBlock": current_block,
                    "toBlock": end_chunk,
                }
            )

            for log in logs:
                vote = decode_vote_log(log, proposal_id)
                if vote and vote["address"] not in seen:
                    seen.add(vote["address"])
                    votes.append(vote)

            current_block = end_chunk + 1

    return votes


def main():
    parser = argparse.ArgumentParser(
        description="Fetch votes with reasons for a DAO proposal"
    )
    parser.add_argument(
        "--dao",
        default=DEFAULT_DAO_ADDRESS,
        help=f"DAO Governor address (default: {DEFAULT_DAO_ADDRESS})",
    )
    parser.add_argument(
        "--rpc",
        required=True,
        help="RPC URL (http/https) or WebSocket URL (ws/wss)",
    )
    parser.add_argument(
        "--proposal-id",
        required=True,
        type=int,
        help="Proposal ID to fetch votes for",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="-",
        help="Output file (default: stdout)",
    )

    args = parser.parse_args()

    # Connect to RPC
    if args.rpc.startswith("ws://") or args.rpc.startswith("wss://"):
        w3 = Web3(Web3.LegacyWebSocketProvider(args.rpc))
    else:
        w3 = Web3(Web3.HTTPProvider(args.rpc))

    if not w3.is_connected():
        print("Error: Could not connect to RPC", file=sys.stderr)
        sys.exit(1)

    # Get proposal block range
    print(f"Fetching proposal {args.proposal_id} info...", file=sys.stderr)
    try:
        start_block, end_block, deadline_in_future = get_proposal_block_range(
            w3, args.dao, args.proposal_id
        )
    except Exception as e:
        print(f"Error fetching proposal info: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Voting block range: {start_block} - {end_block}", file=sys.stderr)
    current_block = w3.eth.block_number
    if deadline_in_future or current_block < end_block:
        print(
            (
                "WARNING: CURRENT BLOCK IS BEFORE THE PROPOSAL DEADLINE BLOCK.\n"
                f"Current block: {current_block}\n"
                f"Deadline block: {end_block}\n"
                "Results may be incomplete until the proposal closes."
            ),
            file=sys.stderr,
        )

    # Fetch votes with reason
    print("Fetching votes with reasons...", file=sys.stderr)
    votes = get_votes_with_reason(w3, args.dao, args.proposal_id, start_block, end_block)
    print(f"Found {len(votes)} votes with reasons", file=sys.stderr)
    zero_weight_votes = [vote for vote in votes if vote.get("weight") == 0]
    if zero_weight_votes:
        print(
            f"WARNING: {len(zero_weight_votes)} vote(s) have weight 0",
            file=sys.stderr,
        )
    reason_counts = {}
    for vote in votes:
        reason = vote.get("reason")
        if reason is None:
            continue
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    duplicate_reasons = [reason for reason, count in reason_counts.items() if count > 1]
    if duplicate_reasons:
        print(
            f"WARNING: {len(duplicate_reasons)} duplicate reason(s) detected",
            file=sys.stderr,
        )

    # Output CSV
    if args.output == "-":
        outfile = sys.stdout
    else:
        outfile = open(args.output, "w", newline="")

    writer = csv.DictWriter(outfile, fieldnames=["address", "reason", "weight"])
    writer.writeheader()
    writer.writerows(votes)

    if args.output != "-":
        outfile.close()
        print(f"Written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
