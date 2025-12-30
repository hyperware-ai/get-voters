# get-voters

Fetch all votes with reasons for a DAO proposal and output as CSV.

Uses OpenZeppelin Governor standard interface.

## Usage

```bash
uvx -n --from . get-voters --rpc URL --proposal-id ID
```

### Options

- `--rpc` (required): RPC URL (http/https) or WebSocket URL (ws/wss)
- `--proposal-id` (required): Proposal ID to fetch votes for
- `--dao`: DAO Governor address (default: 0x000000000048395579c3C60f2F8Cb2DECa457550)
- `-o, --output`: Output file (default: stdout)

## Output

CSV format with columns:

- `address`: Voter address (checksummed)
- `reason`: Vote reason text
- `weight`: Voting weight
