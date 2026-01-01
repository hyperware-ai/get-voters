# get-voters

Fetch all votes with reasons for a DAO proposal and output as CSV.

Uses OpenZeppelin Governor standard interface.

## Usage

```bash
uvx -n --from . get-voters --rpc URL --proposal-id ID
```

```bash
uvx -n --from . parse-voters 251231-first-vote.csv > vesting_b.csv
```

```bash
uvx -n --from . make-bulk-chat-prompt 251231-first-vote.csv /home/nick/git/protocol/script/merkle_tree_generator/251001-6mo-36mo-locked-hypr.json --quarter "Q4 2025" --dindex 1 > bulk_messages.json
```

### Options

- `--rpc` (required): RPC URL (http/https) or WebSocket URL (ws/wss)
- `--proposal-id` (required): Proposal ID to fetch votes for
- `--dao`: DAO Governor address (default: 0x000000000048395579c3C60f2F8Cb2DECa457550)
- `-o, --output`: Output file (default: stdout)
 - `--quarter` (required for `make-bulk-chat-prompt`): Quarter label used in message
 - `--dindex` (required for `make-bulk-chat-prompt`): Distributor index for claim links

## Output

CSV format with columns:

- `address`: Voter address (checksummed)
- `reason`: Vote reason text
- `weight`: Voting weight

`parse-voters` outputs CSV rows with fields `kind,address,amount,isClaimable`.

`make-bulk-chat-prompt` outputs JSON mapping each voter node (second column of get-voters output) to a claim message.
