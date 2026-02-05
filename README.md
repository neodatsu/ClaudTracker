# ClaudTracker

A local usage tracker for Claude Code sessions.

## What It Does

ClaudTracker reads the local JSONL session files created by **Claude Code** (the CLI tool) and provides:

- Token usage statistics (input, output, cache read/write)
- Estimated API cost equivalent
- Per-project breakdown
- 7-day usage history
- Colorful terminal dashboard

## Limitations

**Important: Understand what this tool can and cannot track.**

| What IS tracked | What is NOT tracked |
|-----------------|---------------------|
| Claude Code sessions on **this machine only** | Usage on other computers/devices |
| Local JSONL files in `~/.claude/projects/` | **claude.ai website usage** |
| Terminal-based Claude Code interactions | Claude iOS/Android app usage |
| | Claude Desktop app (different storage) |

### Key Points

1. **Local files only**: ClaudTracker reads files stored in `~/.claude/projects/` on the machine where it runs. If you use Claude Code on multiple computers, each machine only sees its own usage.

2. **Claude Code only**: The claude.ai website does **not** create local JSONL files. This tool cannot track your web-based Claude conversations.

3. **Estimates, not billing**: The cost shown is an *equivalent API cost* based on token counts and published pricing. It does not reflect your actual subscription billing.

## Installation

```bash
git clone https://github.com/neodatsu/ClaudTracker.git
cd ClaudTracker

python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows

pip install -r requirements.txt

cp .env.example .env
```

## Configuration

Edit `.env`:

```bash
# Anthropic API key (optional, for API connection test)
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here

# Your Claude AI subscription plan (free, pro, max, max200)
CLAUDE_PLAN=pro
```

## Usage

```bash
source venv/bin/activate
python claudtracker.py
```

### Sample Output

```
╔══════════════════════════════════════════════════════════════╗
║   CLAUDE USAGE TRACKER    v2.0                               ║
╚═══════════════════════════════════════════ 2026-02-05 09:03 ═╝

╭──── Sessions ────╮╭──── Messages ────╮╭─── Tool Calls ───╮╭──── Cost ────╮
│ 56               ││ 3 906            ││ 3 319            ││ $231.80      │
│ 5 projects       ││ sent             ││ tool calls       ││ API equiv.   │
╰──────────────────╯╰──────────────────╯╰──────────────────╯╰──────────────╯

╭─────────── Tokens & Costs ───────────╮╭─────────── Top 5 Projects ──────────╮
│ Type        │      Tokens │ API Cost ││ Project      │  Tokens │ Messages  │
│ Input       │     229 630 │  $0.69   ││ itercraft    │ 260 118 │     3662  │
│ Output      │      35 118 │  $0.53   ││ experiment   │   2 188 │      129  │
│ Cache Read  │ 474 981 690 │ $142.49  ││ ClaudTracker │   1 081 │       47  │
│ Cache Write │  23 489 747 │  $88.09  ││ finClaud     │     815 │       32  │
│ TOTAL       │ 498 736 185 │ $231.80  ││ mcp          │     546 │       36  │
╰──────────────────────────────────────╯╰──────────────────────────────────────╯
```

## Features

| Feature | Description |
|---------|-------------|
| JSONL Parsing | Reads Claude Code session files |
| Multi-project | Stats broken down by project |
| History | Saves usage snapshots over time |
| API Test | Verifies Anthropic API connection |
| 2026 Pricing | Cost estimates based on current rates |
| Rich Dashboard | Colorful terminal UI with panels |

## Project Structure

```
ClaudTracker/
├── claudtracker.py    # Main script
├── .env.example       # Configuration template
├── .env               # Your config (not versioned)
├── .gitignore         # Git ignore rules
├── requirements.txt   # Python dependencies
└── usage_history.json # Local history (not versioned)
```

## Requirements

- Python 3.8+
- Claude Code installed (`~/.claude/` must exist)

## License

MIT
