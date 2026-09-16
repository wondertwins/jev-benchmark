# Jev chess experiments — model `jev-latest`

## Move selection vs Stockfish (depth 12), realistic middlegame positions

| method | state | n | mean cp loss | median | % best move | % top-3 | % blunders ≥200cp | random-move baseline cp loss | mean confidence |
|---|---|---|---|---|---|---|---|---|---|
| Choice over all legal moves | ascii | 30 | 409 | 522 | 20 | 27 | 57 | 403 | 0.315 |
| Choice over all legal moves | fen | 30 | 533 | 614 | 13 | 17 | 73 | 403 | 0.211 |
| Choice over all legal moves | rich | 30 | 144 | 58 | 27 | 50 | 20 | 403 | 0.387 |
| Score per move, argmax | rich | 30 | 197 | 58 | 17 | 30 | 27 | 403 | 0.517 |
| Choice piece → Choice square | rich | 30 | 217 | 58 | 20 | 33 | 33 | 403 | 0.488 |

B: mean Spearman correlation between Jev's per-move scores and Stockfish move values: **0.464** (0 = no relationship, 1 = identical ranking).

C: choosing the piece first already locks in a mean cp loss of **104.2** (best move available with that piece).

## Mate-in-one puzzles (Choice over legal moves; '#' hidden as '+')

| state | n | found mate | random baseline | prob. mass on mating moves |
|---|---|---|---|---|
| ascii | 25 | 0.28 | 0.031 | 0.184 |
| fen | 25 | 0.24 | 0.031 | 0.12 |
| rich | 25 | 0.24 | 0.031 | 0.202 |

## Board perception (Nouls on ASCII board, n=55)

| question | accuracy @0.5 | Brier | positive rate | majority baseline |
|---|---|---|---|---|
| in_check | 0.945 | 0.055 | 0 | 1 |
| mate_in_one | 0.6 | 0.208 | 0.455 | 0.545 |
| free_capture | 0.564 | 0.227 | 0.527 | 0.527 |
| own_piece_hanging | 0.582 | 0.214 | 0.4 | 0.6 |
| can_castle | 0.8 | 0.106 | 0.255 | 0.745 |
| more_material (Choice white/black/equal) | 0.655 | – | – | – |

## Position evaluation (7-level Score vs Stockfish depth 14, n=55)

- Spearman vs Stockfish centipawns: **0.639**
- Exact bucket accuracy: 0.273; within one bucket: 0.418
- Who-is-better accuracy (white / equal / black): 0.564 (always-'equal' baseline 0.273)

## Full games (Jev = White, rich state, Choice over legal moves)

| opponent | result | termination | plies | Jev mean cp loss | Jev % best | Jev blunders | final eval (cp, white) |
|---|---|---|---|---|---|---|---|
| random | 1-0 | CHECKMATE | 45 | 90 | 22 | 2 | – |
| sf0 | 0-1 | CHECKMATE | 72 | 308 | 19 | 9 | – |

**vs random**: `1. e4 e6 2. Nf3 d6 3. Bb5+ Nc6 4. O-O Ke7 5. Nc3 Na5 6. Nd5+ exd5 7. exd5 h5 8. Re1+ Kf6 9. Re6+ fxe6 10. dxe6 Rh7 11. e7 c5 12. exd8=Q+ Kf5 13. Qxf8+ Kg4 14. Qxg8 g5 15. Qxh7 Rb8 16. Ne1+ Kh4 17. Nf3+ Kg4 18. Ne1+ Kf4 19. Qhxh5 b6 20. d3+ Kf5 21. Qdf3+ Ke6 22. Bxg5 a6 23. Qe8#`

**vs sf0**: `1. e4 Nc6 2. Nf3 g6 3. Bc4 Bg7 4. O-O d6 5. Bxf7+ Kxf7 6. Ng5+ Ke8 7. Nf3 Bg4 8. Ng5 Qd7 9. Qe1 h6 10. Nf3 a6 11. Nh4 g5 12. Ng6 Rh7 13. Qe3 Nd4 14. c3 Ne6 15. Qg3 Nf6 16. Qe3 Bh5 17. Nf4 Nxf4 18. Qd4 b5 19. Qb4 a5 20. Qd4 c5 21. Qe3 d5 22. Qxc5 Ne2+ 23. Kh1 dxe4 24. Rd1 Rc8 25. Qe3 Bf8 26. Re1 Qd3 27. Rxe2 Bxe2 28. Qa7 Qc4 29. Qxa5 e5 30. Qb6 Kf7 31. Qb7+ Ke8 32. Qb6 Kf7 33. Qb7+ Kg8 34. Qb6 Rf7 35. Qe3 Bh5 36. Qb6 Qf1#`

## Does confidence predict blunders? (rich-state Choice, n=30)

- confidence < 0.25: n=12, mean cp loss 173, blunders 3, best-move 25%
- confidence ≥ 0.25: n=18, mean cp loss 125, blunders 3, best-move 28%
- Spearman(confidence, cp loss) = -0.243 (negative = higher confidence, smaller loss)

## Model comparison on the best configuration (rich state)

| model | A: mean cp loss | A: median | A: % best | A: % top-3 | A: % blunders | E: mate found |
|---|---|---|---|---|---|---|
| jev-latest | 144.2 | 58.0 | 26.7 | 50.0 | 20.0 | 0.24 |
| jev-preview | 129.4 | 60.0 | 23.3 | 50.0 | 16.7 | 0.24 |

## Input tokens per request

| experiment | state | mean input tokens |
|---|---|---|
| A_move_choice_ascii | ascii | 1,388 |
| A_move_choice_fen | fen | 698 |
| A_move_choice_rich | rich | 2,111 |
| B_move_scores | rich | 8,334 |
| D_perception | ascii | 1,138 |
| E_mate_in_one_ascii | ascii | 1,768 |
| E_mate_in_one_fen | fen | 732 |
| E_mate_in_one_rich | rich | 2,549 |
| F_eval_score | ascii | 961 |
