import chess
import chess.pgn
import chess.engine
import chess.svg
import io
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

ENGINES = {
    "stockfish": {
        "path": "/opt/homebrew/bin/stockfish",
        "limit": chess.engine.Limit(time=0.3),
    },
    "lc0": {
        "path": "/opt/homebrew/bin/lc0",
        "limit": chess.engine.Limit(nodes=800),
    },
}

PIECE_VALUES = {
    chess.PAWN: 100, chess.KNIGHT: 300, chess.BISHOP: 310,
    chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0,
}


def analyze_game(pgn_text: str, engine_name: str = "stockfish") -> dict:
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    board = game.board()
    headers = dict(game.headers)
    moves_data = []

    engine_cfg = ENGINES[engine_name]
    engine = chess.engine.SimpleEngine.popen_uci(engine_cfg["path"])
    limit = engine_cfg["limit"]

    prev_score = _eval(engine, board, limit)
    prev_cp = _eval_cp(prev_score)
    prev_move_was_bad = False

    for i, move in enumerate(game.mainline_moves()):
        san = board.san(move)
        is_white = (i % 2 == 0)
        move_number = i // 2 + 1
        sign = 1 if is_white else -1

        multi = engine.analyse(board, limit, multipv=2)
        top_move = multi[0]["pv"][0]
        top_cp = _eval_cp(multi[0]["score"].white())
        second_cp = _eval_cp(multi[1]["score"].white()) if len(multi) >= 2 else top_cp

        is_top = (move == top_move)
        is_sacrifice = _is_sacrifice(board, move, is_white)

        gap = (top_cp - second_cp) * sign
        mover_eval = prev_cp * sign

        board.push(move)

        actual_score = _eval(engine, board, limit)
        actual_cp = _eval_cp(actual_score)

        cp_loss = (top_cp - actual_cp) * sign

        classification = _classify(
            cp_loss=cp_loss,
            gap=gap,
            is_top=is_top,
            is_sacrifice=is_sacrifice,
            is_competitive=-200 < mover_eval < 200,
            prev_was_bad=prev_move_was_bad,
        )

        prev_move_was_bad = cp_loss >= 150
        prev_cp = actual_cp

        svg = chess.svg.board(board, lastmove=move, size=400)
        moves_data.append({
            "move_number": move_number,
            "is_white": is_white,
            "san": san,
            "score_cp": actual_cp,
            "score_display": _fmt_score(actual_score),
            "classification": classification,
            "svg": svg,
        })

    engine.quit()
    return {"headers": headers, "moves": moves_data}


def _eval(engine, board, limit):
    info = engine.analyse(board, limit)
    return info["score"].white()


def _eval_cp(score):
    """Clamp to ±1500cp so Lc0's inflated WDL-based centipawns don't break classification."""
    return max(-1500, min(1500, score.score(mate_score=1500)))


def _is_sacrifice(board: chess.Board, move: chess.Move, is_white: bool) -> bool:
    moving_piece = board.piece_at(move.from_square)
    captured_piece = board.piece_at(move.to_square)

    moving_val = PIECE_VALUES.get(moving_piece.piece_type, 0) if moving_piece else 0
    captured_val = PIECE_VALUES.get(captured_piece.piece_type, 0) if captured_piece else 0

    board.push(move)
    is_hanging = board.is_attacked_by(not is_white, move.to_square)
    board.pop()

    return is_hanging and moving_val > captured_val + 50


def _classify(cp_loss, gap, is_top, is_sacrifice, is_competitive, prev_was_bad):
    """
    Chess.com-style move classification:
      Brilliant: sacrifice + only/best move + competitive position
      Great:     only good move (all alternatives much worse)
      Best:      matches engine's #1 choice
      Excellent: very close to engine's best (≤10cp loss)
      Good:      decent, small loss (≤30cp)
      Inaccuracy: notable loss (≤100cp)
      Miss:      failed to punish opponent's mistake (replaces inaccuracy)
      Mistake:   significant loss (≤200cp)
      Blunder:   severe loss (>200cp)
    """
    if cp_loss >= 200:
        return "blunder"
    if cp_loss >= 100:
        return "mistake"
    if cp_loss >= 50:
        return "miss" if prev_was_bad else "inaccuracy"

    only_good_move = gap >= 150

    if cp_loss <= 10 and only_good_move and is_sacrifice and is_competitive:
        return "brilliant"
    if cp_loss <= 10 and only_good_move:
        return "great"
    if is_top:
        return "best"
    if cp_loss <= 10:
        return "excellent"
    if cp_loss <= 30:
        return "good"
    return "good"


def _fmt_score(score):
    mate = score.mate()
    if mate is not None:
        return f"M{mate}" if mate > 0 else f"M{mate}"
    return f"{score.score() / 100:+.2f}"


@app.route("/")
def index():
    return render_template("index.html")



@app.route("/engines")
def engines():
    return jsonify(list(ENGINES.keys()))


@app.route("/analyze", methods=["POST"])
def analyze():
    pgn_text = request.json["pgn"]
    engine_name = request.json.get("engine", "stockfish")
    result = analyze_game(pgn_text, engine_name)
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True, port=5050)
