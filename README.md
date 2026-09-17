# Chess Move Analyzer

Local Chess.com game analyzer powered by NiceGUI, Python, and Stockfish 18.

The recommended deployment path is Docker. The image builds the Python virtual
environment and Stockfish engine together, so the host machine only needs Docker.

## Docker Quick Start

Build and run the portable service:

```powershell
docker compose up --build
```

Open:

```text
http://localhost:8080
```

The analysis cache is stored in the Docker volume `chess_analysis_data`, mounted
inside the container at:

```text
/app/data
```

To stop the app:

```powershell
docker compose down
```

To remove the persisted cache as well:

```powershell
docker compose down -v
```

## Docker Build Options

The Dockerfile builds Stockfish from the official `sf_18` tag.

Optional build arguments:

```bash
docker build --build-arg STOCKFISH_TAG=sf_18 -t chess-move-analyzer:local .
```

By default, amd64 images compile `x86-64-avx2`, arm64 images compile `armv8`,
and other targets compile `general-64`. If the target CPU does not support AVX2,
override the Stockfish architecture:

```bash
docker build --build-arg STOCKFISH_ARCH=x86-64 -t chess-move-analyzer:local .
```

## Local Setup Without Docker

Docker does not need a local `engines/` folder. The scripts below are only for
local development outside Docker.

Windows PowerShell:

```powershell
.\scripts\install_stockfish_windows.ps1
uv --cache-dir .uv-cache pip install -e . --python .venv\Scripts\python.exe
uv --cache-dir .uv-cache run --no-sync python -m chess_move_analyzer
```

By default the local command binds the app to the LAN and attempts to announce
an mDNS name. Other devices on the same network can try:

```text
http://chess109.local:8080
```

If the selected port is not 8080, use the port printed by NiceGUI. Windows may
also ask for firewall permission for Python. If mDNS is blocked by the OS or by
another local mDNS responder, use the computer IP address with the same port.

Linux:

```bash
chmod +x scripts/install_stockfish_linux.sh
./scripts/install_stockfish_linux.sh
python -m venv .venv
. .venv/bin/activate
pip install -e .
python -m chess_move_analyzer
```

The local scripts install:

```text
engines/stockfish.exe   # Windows
engines/stockfish       # Linux
```

Alternatively, install Stockfish in `PATH` or set `STOCKFISH_PATH`.

## Configuration

Environment variables:

```text
CHESS_ANALYZER_HOST   Bind address. Default local value: 0.0.0.0.
CHESS_ANALYZER_PORT   Port. Default auto-selects 8080 or nearby free ports.
CHESS_ANALYZER_SHOW   Whether NiceGUI opens a browser window. Default: true.
CHESS_ANALYZER_MDNS   Enable local mDNS announcement. Default: true.
CHESS_ANALYZER_MDNS_NAME
                      Local mDNS hostname. Default: chess109.local.
STOCKFISH_PATH        Explicit Stockfish executable path.
```

The Docker image sets:

```text
CHESS_ANALYZER_HOST=0.0.0.0
CHESS_ANALYZER_PORT=8080
CHESS_ANALYZER_SHOW=false
STOCKFISH_PATH=/usr/local/bin/stockfish
```

## Scope

- Local NiceGUI interface.
- Public Chess.com game import by URL when available.
- Manual PGN fallback.
- Stockfish UCI analysis with fast, balanced, and deep profiles.
- MultiPV candidate lines.
- SQLite cache keyed by position, engine version, profile, and MultiPV.

## References

- Stockfish releases: <https://github.com/official-stockfish/Stockfish/releases>
- Stockfish downloads: <https://stockfishchess.org/download/>
