# Jev chess experiments — model `jev-latest`

## Move selection vs Stockfish (depth 12), realistic middlegame positions

| method | state | n | mean cp loss | median | % best move | % top-3 | % blunders ≥200cp | random-move baseline cp loss | mean confidence |
|---|---|---|---|---|---|---|---|---|---|
| Choice over all legal moves | ascii | 30 | 409 | 522 | 20 | 27 | 57 | 403 | 0.315 |
| Choice over all legal moves | fen | 30 | 533 | 614 | 13 | 17 | 73 | 403 | 0.211 |
| Choice over all legal moves | rich | 30 | 144 | 58 | 27 | 50 | 20 | 403 | 0.387 |
| Choice over all legal moves | tactical | 30 | 90 | 26 | 37 | 57 | 13 | 403 | 0.496 |
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

## Full games (Choice over legal moves)

| opponent | Jev plays | state | code filter | Jev result | termination | moves | Jev mean cp loss | Jev % best | Jev blunders |
|---|---|---|---|---|---|---|---|---|---|
| greedy | white | tactical | no | **win** | checkmate | 40 | 195 | 30 | 4 |
| greedy | black | tactical | no | **win** | checkmate | 32 | 59 | 28 | 3 |
| mix25 | white | tactical | no | **win** | checkmate | 5 | 4.2 | 80 | 0 |
| mix25 | black | tactical | no | **win** | checkmate | 38 | 257 | 21 | 10 |
| mix50 | white | tactical | no | **win** | checkmate | 33 | 198 | 54 | 6 |
| mix50 | black | tactical | no | **win** | checkmate | 31 | 397 | 29 | 10 |
| mix75 | white | tactical | no | **win** | checkmate | 33 | 180 | 33 | 4 |
| mix75 | black | tactical | no | **win** | checkmate | 28 | 341 | 14 | 7 |
| random | white | rich | no | **win** | checkmate | 23 | 90 | 22 | 2 |
| random | black | tactical | no | **win** | checkmate | 7 | 87 | 29 | 1 |
| sf0 | white | rich | no | loss | checkmate | 36 | 308 | 19 | 9 |
| sf0 | white | tactical | yes | loss | checkmate | 46 | 469 | 15 | 16 |
| sf0 | white | tactical | yes | **win** | checkmate | 38 | 186 | 37 | 10 |
| sf0 | white | tactical | no | loss | checkmate | 44 | 242 | 16 | 8 |
| sf0 | white | tactical | no | loss | adjudicated at -559 cp | 60 | 217 | 33 | 12 |

**vs greedy** (tactical, Jev white): `1. e4 a5 2. Nf3 f6 3. Nc3 b6 4. Bc4 g5 5. Bd5 Nh6 6. Bxa8 f5 7. Nxg5 fxe4 8. Ngxe4 Bg7 9. Qh5+ Kf8 10. Qf3+ Kg8 11. Bd5+ e6 12. Bc4 Bxc3 13. Nxc3 Bb7 14. Qxb7 Nf7 15. O-O c6 16. Qa8 Qe8 17. Qb7 h5 18. Qxb6 Qc8 19. Qxa5 Rh7 20. Bd3 d5 21. Bxh7+ Kxh7 22. Qa7 Kg7 23. Qd4+ Kh7 24. Qf4 Qd7 25. Qxb8 Qe7 26. Qc8 Nh6 27. Qxc6 e5 28. Nxd5 e4 29. Nxe7 Kg7 30. Qxe4 Kf7 31. Qg6+ Kxe7 32. Qxh6 Kd8 33. Qxh5 Ke7 34. Re1+ Kf8 35. Qh8+ Kf7 36. Qh7+ Kf8 37. Qe7+ Kg8 38. Qe8+ Kh7 39. Re7+ Kh6 40. d3#`

**vs greedy** (tactical, Jev black): `1. b4 Nc6 2. Ba3 Nf6 3. f4 e5 4. fxe5 Nxe5 5. Bc1 Bxb4 6. Nh3 O-O 7. Rg1 Bc5 8. d4 Bb4+ 9. c3 Neg4 10. cxb4 Nxh2 11. Qc2 Nxf1 12. Rxf1 Nd5 13. Qxc7 Nxc7 14. Rxf7 Kxf7 15. a4 Qh4+ 16. Kf1 Qxd4 17. Na3 Qxa1 18. Ng1 Qxc1+ 19. Kf2 Qxa3 20. e4 Qxb4 21. e5 Qxa4 22. g4 Qxg4 23. e6+ Kxe6+ 24. Nf3 Qxf3+ 25. Ke1 Qh1+ 26. Ke2 Qe4+ 27. Kd1 Rf1+ 28. Kd2 Rf2+ 29. Kc3 Rc2+ 30. Kb3 Qd3+ 31. Ka4 Rc4+ 32. Ka5 Qa3#`

**vs mix25** (tactical, Jev white): `1. e4 Nc6 2. Nf3 b5 3. Bxb5 g5 4. Nxg5 f5 5. Qh5#`

**vs mix25** (tactical, Jev black): `1. h4 Nf6 2. Rh2 Ng4 3. g3 Nxh2 4. Bg2 Nc6 5. d4 Ng4 6. d5 Nce5 7. a4 Nc4 8. e4 Nce5 9. f4 Nf6 10. fxe5 d6 11. Qf3 dxe5 12. Bd2 Bg4 13. Qb3 Qb8 14. Qb5+ Bd7 15. Qd3 Ng4 16. Na3 Bxa4 17. Bh3 Qc8 18. Qc4 Qd7 19. Qb5 Bxb5 20. Nxb5 Qxb5 21. Ra5 Qxb2 22. Ra6 bxa6 23. Ne2 Qxc2 24. Bc1 Qxe4 25. Bg2 Qxg2 26. h5 Qxd5 27. Nf4 exf4 28. gxf4 Qxh5 29. Kd2 O-O-O+ 30. Kc2 Qc5+ 31. Kb1 Qb6+ 32. Bb2 Rd1+ 33. Ka2 Qa5+ 34. Ba3 Qd2+ 35. Bb2 Qxf4 36. Bxg7 Bxg7 37. Ka3 Ra1+ 38. Kb3 Qa4#`

**vs mix50** (tactical, Jev white): `1. e4 c5 2. d4 Nf6 3. dxc5 Nxe4 4. Qd4 d5 5. cxd6 Nxd6 6. Nf3 Nc6 7. Qd5 f5 8. Qc5 Bd7 9. Ne5 Qc8 10. Nxd7 Qxd7 11. Nc3 e5 12. Qd5 a6 13. Qc5 Rc8 14. Nd5 Nd4 15. Nb6 Qe7 16. Nxc8 Qh4 17. Nxd6+ Bxd6 18. Qxd6 Qxh2 19. Rxh2 Kf7 20. Qc7+ Kf6 21. Qxb7 Rc8 22. Qxc8 Kf7 23. Rxh7 Ne6 24. Bxa6 Kg6 25. Qxe6+ Kxh7 26. Qxf5+ Kh8 27. Qxe5 Kg8 28. Qe8+ Kh7 29. Qh5+ Kg8 30. Qe8+ Kh7 31. Bd3+ g6 32. Qxg6+ Kh8 33. Qh7#`

**vs mix50** (tactical, Jev black): `1. e4 Nf6 2. e5 Nd5 3. Ke2 Nf4+ 4. Kf3 Ne6 5. d4 Nc6 6. Nd2 Nexd4+ 7. Kg4 Nxe5+ 8. Kg5 Ne6+ 9. Kf5 Nd4+ 10. Kg5 f6+ 11. Kf4 Ng6+ 12. Ke4 d5+ 13. Ke3 Nf5+ 14. Ke2 Nf4+ 15. Ke1 Nd4 16. Qh5+ Nxh5 17. Ndf3 Nxc2+ 18. Kd2 Nxa1 19. b3 d4 20. Nxd4 Qxd4+ 21. Ke2 Nf4+ 22. Kf3 Qd1+ 23. Ke4 Qxf1 24. Kd4 Qxc1 25. Ne2 Nxe2+ 26. Kd3 Qxh1 27. Ke3 Qxg2 28. b4 Qxh2 29. Kd2 Qxf2 30. Kd1 Nc3+ 31. Kc1 Qc2#`

**vs mix75** (tactical, Jev white): `1. e4 a6 2. Nf3 c5 3. d4 cxd4 4. Nxd4 f5 5. Nxf5 h5 6. Nh4 Nf6 7. e5 Rh7 8. exf6 exf6 9. Bd3 g6 10. Bxg6+ Rf7 11. Bxf7+ Kxf7 12. Qxh5+ Kg8 13. Qg6+ Bg7 14. O-O f5 15. Nxf5 Qf8 16. Nh6+ Kh8 17. Nf7+ Kg8 18. Ne5 d6 19. Nf3 Qf5 20. Qxf5 Nc6 21. Qd5+ Kf8 22. Qxd6+ Ke8 23. Qg6+ Kd8 24. Qxg7 Rb8 25. Qh8+ Kc7 26. Qh7+ Bd7 27. Bf4+ Kb6 28. Qxd7 Rd8 29. Bc7+ Kc5 30. Bxd8 Kc4 31. Nbd2+ Kb4 32. Qxb7+ Ka4 33. Qb3#`

**vs mix75** (tactical, Jev black): `1. c4 d5 2. Qa4+ Qd7 3. Qa3 dxc4 4. Qc5 b5 5. g4 Qxg4 6. Nc3 Qd7 7. Na4 bxa4 8. Bg2 Ba6 9. Qa5 Nc6 10. e3 Nxa5 11. f4 Bb7 12. Be4 Bxe4 13. f5 Bxh1 14. Ne2 Qxf5 15. Nf4 g5 16. Nh5 Qh3 17. Kd1 Qxh5+ 18. Kc2 Qxh2 19. Kd1 Qg1+ 20. Kc2 Be4+ 21. d3 cxd3+ 22. Kc3 Qe1+ 23. Kd4 d2 24. Kxe4 dxc1=R 25. Rxc1 Qxc1 26. Kd4 Qxb2+ 27. Kd5 Qxa2+ 28. Kc5 Qc4#`

**vs random** (rich, Jev white): `1. e4 e6 2. Nf3 d6 3. Bb5+ Nc6 4. O-O Ke7 5. Nc3 Na5 6. Nd5+ exd5 7. exd5 h5 8. Re1+ Kf6 9. Re6+ fxe6 10. dxe6 Rh7 11. e7 c5 12. exd8=Q+ Kf5 13. Qxf8+ Kg4 14. Qxg8 g5 15. Qxh7 Rb8 16. Ne1+ Kh4 17. Nf3+ Kg4 18. Ne1+ Kf4 19. Qhxh5 b6 20. d3+ Kf5 21. Qdf3+ Ke6 22. Bxg5 a6 23. Qe8#`

**vs random** (tactical, Jev black): `1. Nc3 Nf6 2. h3 Nc6 3. Nb1 Nd4 4. c4 d5 5. f3 dxc4 6. Rh2 Qd6 7. Na3 Qg3#`

**vs sf0** (rich, Jev white): `1. e4 Nc6 2. Nf3 g6 3. Bc4 Bg7 4. O-O d6 5. Bxf7+ Kxf7 6. Ng5+ Ke8 7. Nf3 Bg4 8. Ng5 Qd7 9. Qe1 h6 10. Nf3 a6 11. Nh4 g5 12. Ng6 Rh7 13. Qe3 Nd4 14. c3 Ne6 15. Qg3 Nf6 16. Qe3 Bh5 17. Nf4 Nxf4 18. Qd4 b5 19. Qb4 a5 20. Qd4 c5 21. Qe3 d5 22. Qxc5 Ne2+ 23. Kh1 dxe4 24. Rd1 Rc8 25. Qe3 Bf8 26. Re1 Qd3 27. Rxe2 Bxe2 28. Qa7 Qc4 29. Qxa5 e5 30. Qb6 Kf7 31. Qb7+ Ke8 32. Qb6 Kf7 33. Qb7+ Kg8 34. Qb6 Rf7 35. Qe3 Bh5 36. Qb6 Qf1#`

**vs sf0** (tactical, filter, Jev white): `1. e4 e5 2. Nf3 Nc6 3. Nc3 Nge7 4. Nd5 a5 5. Nxe7 Kxe7 6. Ng5 Ke8 7. Qh5 Qe7 8. Nxh7 Kd8 9. Bd3 Nb4 10. a3 Na6 11. O-O d6 12. Bxa6 Rxa6 13. Rd1 g5 14. Qxg5 Rxh7 15. Qxe7+ Bxe7 16. Re1 Rh4 17. g3 Rh5 18. Rd1 d5 19. exd5 Rh3 20. Kg2 Rf6 21. Re1 Rh5 22. Rh1 e4 23. c4 Bg4 24. Re1 Bf3+ 25. Kg1 c6 26. dxc6 b6 27. Rf1 a4 28. Re1 Kc8 29. Rf1 b5 30. cxb5 Bc5 31. b4 axb3 32. Bb2 Rd6 33. Bc3 Be2 34. Rfb1 Rf5 35. Rxb3 Bxf2+ 36. Kg2 Ba7 37. Re1 Rf2+ 38. Kg1 Bb6 39. Rc1 Rf5+ 40. Kg2 Rf2+ 41. Kh1 f6 42. Kg1 Rf3+ 43. Kg2 Rf2+ 44. Kh3 f5 45. Kh4 Bd8+ 46. Kh3 Rh6#`

**vs sf0** (tactical, filter, Jev white): `1. e4 Nc6 2. Nf3 d6 3. Nc3 e5 4. Bc4 Be6 5. Bxe6 fxe6 6. O-O Qf6 7. Nb5 Qd8 8. d4 Qd7 9. d5 exd5 10. exd5 Nce7 11. Nc3 Ng6 12. Ng5 h6 13. Ne6 Rc8 14. Nxf8 Kxf8 15. Qf3+ Ke8 16. Qe4 N8e7 17. Qb4 c6 18. dxc6 Rxc6 19. Qa5 Nh4 20. Qxa7 Qg4 21. Qb8+ Nc8 22. g3 h5 23. Qxb7 Ne7 24. Qa8+ Kd7 25. Qxh8 Rc8 26. Qh7 Rh8 27. Qxh8 Qh3 28. gxh4 Qg4+ 29. Kh1 Nd5 30. Nxd5 Ke6 31. Nc7+ Kd7 32. Bg5 Qe4+ 33. f3 Qe2 34. Qxg7+ Kc8 35. Rac1 d5 36. Nxd5 Qxf1+ 37. Rxf1 e4 38. Qc7#`

**vs sf0** (tactical, Jev white): `1. e4 d6 2. Bb5+ Nd7 3. Bxd7+ Kxd7 4. Qg4+ e6 5. Nf3 b6 6. O-O Nf6 7. Qf4 h6 8. e5 Ba6 9. exf6 g5 10. Qd4 c5 11. d3 cxd4 12. Nxd4 Qb8 13. Rd1 b5 14. Nf3 e5 15. Re1 Kc7 16. Nc3 Kb7 17. Nd5 g4 18. Ne3 Qc8 19. Nh4 Kb8 20. Nhf5 h5 21. Ne7 Qd7 22. N7f5 Bc8 23. Ng7 Qc6 24. Ngf5 a6 25. Ne7 Qb6 26. Nxc8 Kxc8 27. Nd5 Qa7 28. Be3 Qb7 29. Nb6+ Kc7 30. Nxa8+ Kb8 31. Nb6 Bh6 32. Reb1 Qc6 33. Rc1 h4 34. g3 d5 35. gxh4 d4 36. Bg5 Bxg5 37. hxg5 Qf3 38. Nd7+ Kb7 39. Nxe5 Qh3 40. Nxf7 Rh5 41. Nd8+ Kc8 42. Nc6 g3 43. Nxd4 Qxh2+ 44. Kf1 Qxf2#`

**vs sf0** (tactical, Jev white): `1. e4 c5 2. d4 Nf6 3. dxc5 e6 4. Qd4 Nc6 5. Qc4 b5 6. cxb6 Bb4+ 7. c3 Bd6 8. bxa7 O-O 9. Qa4 Rxa7 10. Be3 Bc5 11. Bxc5 Rxa4 12. Bxf8 Rxe4+ 13. Kd2 Qb6 14. f3 Rd4+ 15. cxd4 Ne4+ 16. fxe4 Qxb2+ 17. Ke3 Qxa1 18. Ba3 Qxb1 19. Bd3 Qxa2 20. Bd6 h6 21. g3 Qb2 22. d5 Qb6+ 23. Kd2 Qa5+ 24. Kc2 Qa2+ 25. Kc3 Qa1+ 26. Kc4 Qa6+ 27. Kc3 Qa1+ 28. Kb3 Nd4+ 29. Kc4 Ba6+ 30. Kc5 Qc3+ 31. Kb6 Qb3+ 32. Kxa6 Qxd3+ 33. Kb7 Qb1+ 34. Kc7 Qc1+ 35. Kxd7 Qc4 36. dxe6 Qb5+ 37. Ke7 Qg5+ 38. Kd7 fxe6 39. Be7 Qc1 40. Kd6 Qc6+ 41. Ke5 Qc3 42. Kd6 Qd2 43. Ke5 h5 44. Kd6 Qc3 45. Ke5 Kf7 46. Bd8 Ke8 47. Bb6 Nb5+ 48. Kxe6 Qc4+ 49. Kf5 Qf1+ 50. Kg6 Qf7+ 51. Kh7 h4 52. gxh4 g5+ 53. Kh6 gxh4 54. Kg5 Nc3 55. Kxh4 Qf4+ 56. Kh5 Qxe4 57. Nf3 Qxf3+ 58. Kh6 Qb7 59. Re1+ Kd7 60. Bd4 Qf3`

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
| A_move_choice_tactical | tactical | 2,223 |
| B_move_scores | rich | 8,334 |
| D_perception | ascii | 1,138 |
| E_mate_in_one_ascii | ascii | 1,768 |
| E_mate_in_one_fen | fen | 732 |
| E_mate_in_one_rich | rich | 2,549 |
| F_eval_score | ascii | 961 |
