"""Experiments testing TypeSafe's Jev (System One) model on chess judgments.

Code owns the board, legality, and ground truth (python-chess + Stockfish).
Jev supplies typed judgments: Choice over legal moves, Score per move,
Noul perception checks, and Score position evaluation.
"""
