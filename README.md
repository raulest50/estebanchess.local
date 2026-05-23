# Chess Move Analyzer

Local Chess.com game analyzer powered by Stockfish and Python.

## Quick start

```powershell
uv --cache-dir .uv-cache pip install -e . --python .venv\Scripts\python.exe
uv --cache-dir .uv-cache run --no-sync python -m chess_move_analyzer
```

Put a Stockfish 18 Windows binary at:

```text
engines/stockfish.exe
```

Alternatively set:

```powershell
$env:STOCKFISH_PATH = "C:\path\to\stockfish.exe"
```

The app stores local cache data in:

```text
data/analysis.sqlite
```

By default the app tries port `8080` and then nearby free ports. To force a port:

```powershell
$env:CHESS_ANALYZER_PORT = "8765"
uv --cache-dir .uv-cache run --no-sync python -m chess_move_analyzer
```

## Scope

- Local NiceGUI interface.
- Public Chess.com game import by URL when available.
- Manual PGN fallback.
- Stockfish UCI analysis with fast, balanced, and deep profiles.
- SQLite cache keyed by position, engine version, profile, and MultiPV.
