# Pandora

> *Open the box. See what's inside. Decide what stays.*

A sleek terminal UI for macOS that reveals every process running on your machine. Built with [Textual](https://textual.textualize.io/) for a beautiful, keyboard-driven experience.

## Installation

```bash
pip install -e .
# or
pipx install -e .
```

## Usage

```bash
pandora
```

## What's Inside the Box

```
┌─────────────────────────────────────────────────────────────┐
│ Pandora - macOS Process Manager                             │
├─────────────────────────────────────────────────────────────┤
│ Apps: 47 │ CPU: 23.4% │ Memory: 12.3 GB / 16 GB             │
├─────────────────────────────────────────────────────────────┤
│    Name                 PID       CPU%     Memory    Status │
│ ● Chrome              1234      12.3%    1.2 GB    running  │
│ ● Slack               5678       2.1%    456 MB    running  │
│ ● VS Code             9012       8.5%    890 MB    running  │
│ ● Spotify             3456       1.2%    234 MB    running  │
│ ...                                                         │
├─────────────────────────────────────────────────────────────┤
│ q Quit │ k Kill │ K Force Kill │ r Refresh │ / Search      │
└─────────────────────────────────────────────────────────────┘
```

## Controls

| Key | Action |
|-----|--------|
| `q` | Close the box |
| `k` | Kill process (graceful) |
| `K` | Force kill (no mercy) |
| `r` | Refresh |
| `/` | Search |
| `j` / `↓` | Navigate down |
| `↑` | Navigate up |
| `Escape` | Clear search |

## Status Indicators

- `●` Green — All good
- `●` Yellow — High CPU (>50%)
- `●` Red — Memory hungry (>1GB)

## Requirements

- macOS
- Python 3.10+

## License

MIT
