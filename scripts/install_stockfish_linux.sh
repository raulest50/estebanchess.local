#!/usr/bin/env bash
set -euo pipefail

version="${STOCKFISH_VERSION:-sf_18}"
url="${STOCKFISH_URL:-https://github.com/official-stockfish/Stockfish/releases/download/${version}/stockfish-ubuntu-x86-64-avx2.tar}"
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
engines_dir="${root_dir}/engines"
tmp_dir="$(mktemp -d)"

cleanup() {
    rm -rf "${tmp_dir}"
}
trap cleanup EXIT

mkdir -p "${engines_dir}"

echo "Downloading Stockfish 18 from ${url}"
curl -L "${url}" -o "${tmp_dir}/stockfish.tar"
tar -xf "${tmp_dir}/stockfish.tar" -C "${tmp_dir}"

stockfish_bin="$(find "${tmp_dir}" -type f -name 'stockfish*' -perm -u=x | head -n 1)"
if [ -z "${stockfish_bin}" ]; then
    stockfish_bin="$(find "${tmp_dir}" -type f -name 'stockfish*' | head -n 1)"
fi

if [ -z "${stockfish_bin}" ]; then
    echo "Could not find a Stockfish binary in the downloaded archive." >&2
    exit 1
fi

install -m 0755 "${stockfish_bin}" "${engines_dir}/stockfish"
echo "Installed ${engines_dir}/stockfish"
