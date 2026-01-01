#!/usr/bin/env python3
"""Generate bulk chat prompt messages from voters CSV and merkle JSON."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from typing import Any


def format_terse_number(value: str) -> str:
    try:
        num = float(value.replace(",", ""))
    except ValueError:
        return value
    if math.isnan(num):
        return value

    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}m"
    if num >= 1_000:
        return f"{num / 1_000:.1f}k"
    if num >= 100:
        return f"{num:.1f}"
    if num >= 10:
        return f"{num:.1f}"
    return f"{num:.1f}"


def format_hypr_amount(wei_value: str | None) -> str:
    if wei_value is None:
        return "-"
    try:
        wei = int(wei_value)
    except ValueError:
        return wei_value
    if wei == 0:
        return "0.0"
    digits = str(wei).rjust(19, "0")
    whole = digits[:-18].lstrip("0") or "0"
    frac = digits[-18:].rstrip("0")
    numeric = f"{whole}.{frac}" if frac else whole
    return format_terse_number(numeric)


def load_merkle_entries(path: str) -> dict[str, dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError("Merkle JSON missing entries list")
    by_address: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        address = str(entry.get("address", "")).strip()
        if not address:
            continue
        by_address[address.lower()] = entry
    return by_address


def row_node(row: dict[str, str], fieldnames: list[str] | None) -> str:
    if "reason" in row:
        return row.get("reason", "").strip()
    if fieldnames and len(fieldnames) >= 2:
        return row.get(fieldnames[1], "").strip()
    return ""


def build_message(
    *,
    quarter: str,
    dindex: str,
    index: int,
    address: str,
    amount: str,
    merkleproof: str,
) -> str:
    amount_readable = format_hypr_amount(amount)
    return (
        f"Thank you for participating in {quarter} HYPR DAO governance. As a show of our DAOs appreciation, you have earned {amount_readable} HYPR from the quarterly voting incentives. To claim your incentives, please follow the link below, which will open the HYPR DAO app and provide a Claim button once you have connected the wallet you used to vote.\n\n"
        "WARNING: Please confirm this message is coming from dao.hypr and that the app that is opened is the HYPR DAO app before clicking the Claim button! If you have questions about the security of your claim, please message dao.hypr.\n\n"
        f"hw://hypr-dao:hypr-dao:ware.hypr/claim?dindex={dindex}&index={index}&kind=4&receiver={address}&amount={amount}&isclaimable=true&merkleproof={merkleproof}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a node->message JSON for bulk chat prompts.",
    )
    parser.add_argument("voters_csv", help="Path to get-voters CSV")
    parser.add_argument("merkle_json", help="Path to merkle generator JSON")
    parser.add_argument("--quarter", required=True, help="Quarter label used in message")
    parser.add_argument("--dindex", required=True, help="Distributor index for claim links")
    args = parser.parse_args()

    entries_by_address = load_merkle_entries(args.merkle_json)

    messages: dict[str, str] = {}
    missing_addresses: list[str] = []

    with open(args.voters_csv, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        for row in reader:
            address = (row.get("address") or "").strip()
            node = row_node(row, fieldnames)
            if not address or not node:
                continue
            entry = entries_by_address.get(address.lower())
            if entry is None:
                missing_addresses.append(address)
                continue
            amount = str(entry.get("amount", "")).strip()
            index = entry.get("index")
            proof = entry.get("proof")
            if amount == "" or index is None or not isinstance(proof, list):
                missing_addresses.append(address)
                continue
            merkleproof = ",".join(str(item).strip() for item in proof if str(item).strip())
            message = build_message(
                quarter=args.quarter,
                dindex=str(args.dindex),
                index=int(index),
                address=str(entry.get("address", address)).strip(),
                amount=amount,
                merkleproof=merkleproof,
            )
            messages[node] = message

    if missing_addresses:
        unique = sorted(set(missing_addresses))
        print("Missing merkle entries for addresses:", file=sys.stderr)
        for addr in unique:
            print(f"- {addr}", file=sys.stderr)
        return 1

    json.dump(messages, sys.stdout, ensure_ascii=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
