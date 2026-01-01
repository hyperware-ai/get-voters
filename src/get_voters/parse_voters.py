#!/usr/bin/env python3
"""Convert get-voters CSV output to vesting CSV format."""

from __future__ import annotations

import argparse
import csv
import sys
from typing import Iterable


def _parse_weight(raw: str, address: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid weight for {address}: {raw}") from exc


def convert_rows(
    rows: Iterable[dict[str, str]], incentive_total: int
) -> Iterable[list[str]]:
    parsed_rows: list[tuple[str, int]] = []
    total_weight = 0
    for row in rows:
        address = (row.get("address") or "").strip()
        weight_raw = (row.get("weight") or "").strip()
        if not address:
            continue
        if weight_raw == "":
            raise ValueError(f"Missing weight for {address}")
        weight = _parse_weight(weight_raw, address)
        if weight == 0:
            continue
        parsed_rows.append((address, weight))
        total_weight += weight

    if total_weight <= 0:
        raise ValueError("Total weight must be positive")

    amounts: list[int] = []
    for _, weight in parsed_rows:
        amounts.append((weight * incentive_total) // total_weight)

    distributed = sum(amounts)
    remainder = incentive_total - distributed
    if remainder < 0:
        raise ValueError("Distributed amount exceeds incentive total")
    if remainder > 0:
        min_index = min(range(len(amounts)), key=amounts.__getitem__)
        amounts[min_index] += remainder

    for (address, _), amount in zip(parsed_rows, amounts):
        yield ["4", address, str(amount), "True"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert get-voters CSV to vesting CSV format.",
    )
    parser.add_argument("input_csv", help="Path to get-voters CSV file")
    parser.add_argument(
        "incentive_total",
        type=int,
        help="Total incentive amount to distribute (integer, wei)",
    )
    args = parser.parse_args()

    with open(args.input_csv, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        writer = csv.writer(sys.stdout, lineterminator="\n")
        try:
            for out_row in convert_rows(reader, args.incentive_total):
                writer.writerow(out_row)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
