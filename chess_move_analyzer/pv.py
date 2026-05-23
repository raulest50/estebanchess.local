from __future__ import annotations

import chess


def pv_board_at(
    fen_before: str,
    pv_uci: list[str],
    pv_index: int,
) -> tuple[chess.Board, chess.Move | None]:
    board = chess.Board(fen_before)
    last_move: chess.Move | None = None
    if pv_index < 0:
        return board, None

    for uci in pv_uci[: pv_index + 1]:
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise ValueError(f"Illegal PV move {uci} for position {board.fen()}")
        board.push(move)
        last_move = move
    return board, last_move

