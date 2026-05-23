# Chess Move Analyzer

Local Chess.com game analyzer powered by NiceGUI, Python, and Stockfish 18.

The recommended deployment path is Docker. The image builds the Python virtual
environment and Stockfish engine together, so the host machine only needs Docker.

## Docker Quick Start

Build and run the portable service:

```powershell
docker compose up --build app
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

## Linux mDNS Profile

On Linux hosts, the compose file includes an optional mDNS profile that attempts
to publish the app as:

```text
http://estebanchess.local:8080
```

Run it with host networking:

```bash
docker compose --profile mdns-linux up --build app-mdns-linux
```

This profile starts `dbus` and `avahi-daemon` inside the container and publishes
an HTTP service for `estebanchess.local`. This is mainly intended for Linux
because Docker Desktop on Windows and macOS does not expose container multicast
networking in the same reliable way. On Docker Desktop, use `localhost:8080`
unless you configure name resolution on the host.

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
CHESS_ANALYZER_HOST   Bind address. Default local value: 127.0.0.1.
CHESS_ANALYZER_PORT   Port. Default auto-selects 8080 or nearby free ports.
CHESS_ANALYZER_SHOW   Whether NiceGUI opens a browser window. Default: true.
STOCKFISH_PATH        Explicit Stockfish executable path.
ENABLE_MDNS           Set to 1/true/on to start container mDNS support.
MDNS_HOSTNAME         Hostname prefix for mDNS. Default: estebanchess.
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
- Docker host networking: <https://docs.docker.com/engine/network/drivers/host/>
