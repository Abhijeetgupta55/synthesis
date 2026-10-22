# smartci backtest: networkx

Profile base `abf2feda22`, 263 test files, 240 s summed test time. Set: both. Adapter used: True. Simulated from real measured durations (see `backtest.py`).

## mined (n = 18)

| Ordering | Median s to 1st failure [95% CI] | Mean APFDc | smartci win/tie/loss | smartci time ÷ baseline (median) [CI] |
|---|---|---|---|---|
| coverage_first | 0.52 [0.12, 19.11] | 0.910 | 4/9/5 | 1.00 [1.00, 1.03] |
| smartci | 0.72 [0.21, 3.42] | 0.936 | – | – |
| changed_files_first | 1.20 [0.16, 2.20] | 0.983 | 1/10/7 | 1.00 [1.00, 1.19] |
| fastest_first | 68.66 [43.78, 78.70] | 0.757 | 17/0/1 | 0.01 [0.01, 0.03] |
| default | 114.93 [69.51, 194.81] | 0.552 | 18/0/0 | 0.01 [0.00, 0.02] |
| random | 150.10 [132.79, 158.05] | 0.512 | 17/0/1 | 0.00 [0.00, 0.02] |

Best simple baseline: **coverage_first**. Recommendation: smartci does not clearly beat 'coverage_first' here; use coverage_first (or keep smartci only if its median is lower and you accept the uncertainty).

Losses vs coverage_first (5): f4c159f2b7e71993fee5c98ed54dbe5c1ae6ad30, e9eac8a7e04df0b9cdcff8ed1682b3971678f4ed, 2aecdbdd18210c38dc2b9fe32da3825bf30a3c33, 56c7b0d0b6141ec0ffa6a9ebb5494417120b7f50, 083e47255d7087340e97ec13d256e9241ec25e77

## mutant (n = 300)

| Ordering | Median s to 1st failure [95% CI] | Mean APFDc | smartci win/tie/loss | smartci time ÷ baseline (median) [CI] |
|---|---|---|---|---|
| changed_files_first | 0.08 [0.06, 0.11] | 0.910 | 41/214/45 | 1.00 [1.00, 1.00] |
| smartci | 0.08 [0.07, 0.11] | 0.991 | – | – |
| coverage_first | 0.08 [0.07, 0.12] | 0.988 | 43/196/61 | 1.00 [1.00, 1.00] |
| fastest_first | 23.84 [21.78, 29.17] | 0.887 | 298/0/2 | 0.01 [0.01, 0.01] |
| default | 125.52 [69.47, 138.14] | 0.519 | 296/1/3 | 0.00 [0.00, 0.00] |
| random | 142.28 [136.19, 146.90] | 0.505 | 300/0/0 | 0.00 [0.00, 0.00] |

Best simple baseline: **changed_files_first**. Recommendation: smartci does not clearly beat 'changed_files_first' here; use changed_files_first (or keep smartci only if its median is lower and you accept the uncertainty).

Losses vs changed_files_first (45): m42-networkx.generators.community.py-435-35-arith, m42-networkx.algorithms.cycles.py-391-24-constant, m42-networkx.drawing.layout.py-1169-14-constant, m42-networkx.algorithms.flow.gomory_hu.py-173-34-compare, m42-networkx.drawing.nx_pylab.py-1992-32-constant, m42-networkx.algorithms.isomorphism.tree_isomorphism.py-56-23-arith, m42-networkx.algorithms.isomorphism.vf2pp.py-854-57-compare, m42-networkx.algorithms.isomorphism.isomorphvf2.py-762-11-compare, m42-networkx.algorithms.regular.py-38-19-compare, m42-networkx.algorithms.shortest_paths.weighted.py-867-38-compare, m42-networkx.generators.random_graphs.py-109-8-constant, m42-networkx.readwrite.text.py-263-13-constant, m42-networkx.algorithms.centrality.betweenness.py-468-11-compare, m42-networkx.drawing.layout.py-1699-17-constant, m42-networkx.algorithms.connectivity.connectivity.py-349-56-arith, m42-networkx.utils.rcm.py-139-71-constant, m42-networkx.algorithms.similarity.py-1171-15-compare, m42-networkx.drawing.nx_pylab.py-667-53-constant, m42-networkx.readwrite.text.py-824-18-compare, m42-networkx.drawing.nx_pylab.py-203-35-constant, m42-networkx.algorithms.tree.branchings.py-174-15-compare, m42-networkx.algorithms.distance_measures.py-717-25-compare, m42-networkx.algorithms.isomorphism.tree_isomorphism.py-179-32-compare, m42-networkx.algorithms.cycles.py-948-30-compare, m42-networkx.algorithms.tree.branchings.py-592-25-constant, m42-networkx.algorithms.similarity.py-1927-18-arith, m42-networkx.algorithms.similarity.py-914-20-constant, m42-networkx.generators.geometric.py-996-19-constant, m42-networkx.algorithms.flow.gomory_hu.py-177-56-constant, m42-networkx.generators.directed.py-74-7-compare, m42-networkx.algorithms.similarity.py-1390-7-arith, m42-networkx.algorithms.isomorphism.vf2pp.py-857-61-compare, m42-networkx.algorithms.cycles.py-387-22-constant, m42-networkx.generators.small.py-778-22-constant, m42-networkx.algorithms.tree.branchings.py-156-34-constant, m42-networkx.drawing.nx_pylab.py-2056-43-constant, m42-networkx.drawing.layout.py-2027-7-compare, m42-networkx.algorithms.similarity.py-1013-44-compare, m42-networkx.algorithms.dag.py-765-17-constant, m42-networkx.generators.geometric.py-493-15-compare, m42-networkx.algorithms.distance_measures.py-915-7-compare, m42-networkx.algorithms.similarity.py-1164-7-compare, m42-networkx.algorithms.similarity.py-2055-32-constant, m42-networkx.algorithms.cycles.py-752-19-compare, m42-networkx.algorithms.similarity.py-1179-12-return

## all (n = 318)

| Ordering | Median s to 1st failure [95% CI] | Mean APFDc | smartci win/tie/loss | smartci time ÷ baseline (median) [CI] |
|---|---|---|---|---|
| changed_files_first | 0.08 [0.07, 0.12] | 0.915 | 42/224/52 | 1.00 [1.00, 1.00] |
| smartci | 0.09 [0.07, 0.15] | 0.988 | – | – |
| coverage_first | 0.09 [0.07, 0.14] | 0.984 | 47/205/66 | 1.00 [1.00, 1.00] |
| fastest_first | 25.83 [21.78, 29.78] | 0.879 | 315/0/3 | 0.01 [0.01, 0.01] |
| default | 124.74 [69.84, 137.98] | 0.521 | 314/1/3 | 0.00 [0.00, 0.00] |
| random | 142.32 [136.88, 147.32] | 0.505 | 317/0/1 | 0.00 [0.00, 0.00] |

Best simple baseline: **changed_files_first**. Recommendation: smartci does not clearly beat 'changed_files_first' here; use changed_files_first (or keep smartci only if its median is lower and you accept the uncertainty).

Losses vs changed_files_first (52): d3e018213f562832734fa7126018bb22cc7c6376, f4c159f2b7e71993fee5c98ed54dbe5c1ae6ad30, e9eac8a7e04df0b9cdcff8ed1682b3971678f4ed, 2aecdbdd18210c38dc2b9fe32da3825bf30a3c33, 56c7b0d0b6141ec0ffa6a9ebb5494417120b7f50, c94928ed94899033126c9d47f797a1f698584b20, 083e47255d7087340e97ec13d256e9241ec25e77, m42-networkx.generators.community.py-435-35-arith, m42-networkx.algorithms.cycles.py-391-24-constant, m42-networkx.drawing.layout.py-1169-14-constant, m42-networkx.algorithms.flow.gomory_hu.py-173-34-compare, m42-networkx.drawing.nx_pylab.py-1992-32-constant, m42-networkx.algorithms.isomorphism.tree_isomorphism.py-56-23-arith, m42-networkx.algorithms.isomorphism.vf2pp.py-854-57-compare, m42-networkx.algorithms.isomorphism.isomorphvf2.py-762-11-compare, m42-networkx.algorithms.regular.py-38-19-compare, m42-networkx.algorithms.shortest_paths.weighted.py-867-38-compare, m42-networkx.generators.random_graphs.py-109-8-constant, m42-networkx.readwrite.text.py-263-13-constant, m42-networkx.algorithms.centrality.betweenness.py-468-11-compare, m42-networkx.drawing.layout.py-1699-17-constant, m42-networkx.algorithms.connectivity.connectivity.py-349-56-arith, m42-networkx.utils.rcm.py-139-71-constant, m42-networkx.algorithms.similarity.py-1171-15-compare, m42-networkx.drawing.nx_pylab.py-667-53-constant, m42-networkx.readwrite.text.py-824-18-compare, m42-networkx.drawing.nx_pylab.py-203-35-constant, m42-networkx.algorithms.tree.branchings.py-174-15-compare, m42-networkx.algorithms.distance_measures.py-717-25-compare, m42-networkx.algorithms.isomorphism.tree_isomorphism.py-179-32-compare, m42-networkx.algorithms.cycles.py-948-30-compare, m42-networkx.algorithms.tree.branchings.py-592-25-constant, m42-networkx.algorithms.similarity.py-1927-18-arith, m42-networkx.algorithms.similarity.py-914-20-constant, m42-networkx.generators.geometric.py-996-19-constant, m42-networkx.algorithms.flow.gomory_hu.py-177-56-constant, m42-networkx.generators.directed.py-74-7-compare, m42-networkx.algorithms.similarity.py-1390-7-arith, m42-networkx.algorithms.isomorphism.vf2pp.py-857-61-compare, m42-networkx.algorithms.cycles.py-387-22-constant, m42-networkx.generators.small.py-778-22-constant, m42-networkx.algorithms.tree.branchings.py-156-34-constant, m42-networkx.drawing.nx_pylab.py-2056-43-constant, m42-networkx.drawing.layout.py-2027-7-compare, m42-networkx.algorithms.similarity.py-1013-44-compare, m42-networkx.algorithms.dag.py-765-17-constant, m42-networkx.generators.geometric.py-493-15-compare, m42-networkx.algorithms.distance_measures.py-915-7-compare, m42-networkx.algorithms.similarity.py-1164-7-compare, m42-networkx.algorithms.similarity.py-2055-32-constant, m42-networkx.algorithms.cycles.py-752-19-compare, m42-networkx.algorithms.similarity.py-1179-12-return

## Every bug

| Kind | Bug | Title | Failing tests | Default s | smartci s | smartci rank of 1st failing file |
|---|---|---|---|---|---|---|
| mined | [d3e018213f](https://github.com/networkx/networkx/commit/d3e018213f562832734fa7126018bb22cc7c6376) | Fixed diameter/radius error for null graphs (#8454) | 2 | 163.91 | 126.71 | 182 |
| mined | [7c35210a95](https://github.com/networkx/networkx/commit/7c35210a95bcea5bf25bd9bc5fbe052f588b6d90) | fix: add suggestions from #8021 and #8029 to `is_aperiodic`  | 13 | 141.17 | 0.53 | 1 |
| mined | [f4c159f2b7](https://github.com/networkx/networkx/commit/f4c159f2b7e71993fee5c98ed54dbe5c1ae6ad30) | BUGFIX: spring energy and ARF layouts with zero iterations ( | 3 | 250.05 | 4.28 | 2 |
| mined | [a9c8113b85](https://github.com/networkx/networkx/commit/a9c8113b857f66f951800a42862d64db2538ab87) | Fix cost function in min_weighted_dominating_set (#8531) | 1 | 3.24 | 0.03 | 1 |
| mined | [b3c9b00aaa](https://github.com/networkx/networkx/commit/b3c9b00aaab32ed74e5be79bf5960772d3e63467) | Fix sparse heuristic not applied to diagonal blocks in stoch | 2 | 275.97 | 0.91 | 1 |
| mined | [46a639aeb9](https://github.com/networkx/networkx/commit/46a639aeb9bd4db8da444bd6a532df567b9a73cc) | BUG: fix SpanningTreeIterator AttributeError when using next | 1 | 206.42 | 0.51 | 1 |
| mined | [fc87a81fd3](https://github.com/networkx/networkx/commit/fc87a81fd3de0f17c03e611fd6e746994c66277c) | BUG: Handle small graphs in information_centrality (#7475) | 3 | 32.58 | 0.06 | 1 |
| mined | [e9eac8a7e0](https://github.com/networkx/networkx/commit/e9eac8a7e04df0b9cdcff8ed1682b3971678f4ed) | Fix: bug with mean degree part of geometric_soft_configurati | 1 | 280.55 | 2.55 | 2 |
| mined | [d8081795e1](https://github.com/networkx/networkx/commit/d8081795e1344c576590b214c2e4f264b5e87244) | BUG: Fix k_components losing or truncating k-components (#87 | 3 | 51.92 | 0.30 | 1 |
| mined | [139259c6c5](https://github.com/networkx/networkx/commit/139259c6c5479b35ddde9318203ae715b25a3192) | Fix ISMAGS ignoring matches when graph has extra node/edge c | 6 | 105.36 | 1.50 | 1 |
| mined | [2aecdbdd18](https://github.com/networkx/networkx/commit/2aecdbdd18210c38dc2b9fe32da3825bf30a3c33) | BUG: reverse the map returned by vf2pp functions (#8813) | 13 | 69.47 | 0.21 | 1 |
| mined | [675034adb1](https://github.com/networkx/networkx/commit/675034adb14a790336121e4e0f9d8097b880ec41) | [BUG][PERF] Fix ISMAGS directed matching and monomorphism ov | 8 | 105.59 | 1.73 | 1 |
| mined | [31ab6fd7e1](https://github.com/networkx/networkx/commit/31ab6fd7e1e149e887282b83a91752c486d071b6) | BUG: Fix _hits_numpy inf/NaN when eigh returns negated eigen | 1 | 124.26 | 0.02 | 1 |
| mined | [56c7b0d0b6](https://github.com/networkx/networkx/commit/56c7b0d0b6141ec0ffa6a9ebb5494417120b7f50) | BUG: Fix vf2 handling of isomorphism_iter with isolated subg | 6 | 69.56 | 5.87 | 6 |
| mined | [c94928ed94](https://github.com/networkx/networkx/commit/c94928ed94899033126c9d47f797a1f698584b20) | fix: handle empty candidate sets in ISMAGS.largest_common_su | 2 | 105.54 | 78.60 | 140 |
| mined | [083e47255d](https://github.com/networkx/networkx/commit/083e47255d7087340e97ec13d256e9241ec25e77) | BUG: Hold the graph weakly in cached edge and degree views ( | 1 | 211.94 | 152.14 | 82 |
| mined | [9f6079c012](https://github.com/networkx/networkx/commit/9f6079c0120416599ea5d4018bbaba229ea2e456) | BUG: Fix row-max normalization in vectorized effective_size  | 3 | 194.81 | 0.17 | 1 |
| mined | [c1ebe046ec](https://github.com/networkx/networkx/commit/c1ebe046ec672eca7cba4dc88d6e0145406d693a) | BUG: group betweenness centrality changes output with reorde | 2 | 33.00 | 0.14 | 1 |
| mutant | m42-networkx.algorithms.minors.contraction.py-394-12-return | return at networkx/algorithms/minors/contraction.py:394 | 14 | 124.90 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.simple_paths.py-916-20-constant | constant at networkx/algorithms/simple_paths.py:916 | 10 | 193.71 | 0.63 | 1 |
| mutant | m42-networkx.algorithms.approximation.traveling_salesman.py-824-20-arith | arith at networkx/algorithms/approximation/traveling_salesma | 2 | 19.77 | 5.12 | 2 |
| mutant | m42-networkx.algorithms.flow.capacityscaling.py-121-28-boolop | boolop at networkx/algorithms/flow/capacityscaling.py:121 | 2 | 67.46 | 0.63 | 3 |
| mutant | m42-networkx.generators.community.py-435-35-arith | arith at networkx/generators/community.py:435 | 2 | 35.83 | 0.24 | 1 |
| mutant | m42-networkx.generators.small.py-178-4-return | return at networkx/generators/small.py:178 | 3 | 126.70 | 0.04 | 1 |
| mutant | m42-networkx.algorithms.components.biconnected.py-375-23-compare | compare at networkx/algorithms/components/biconnected.py:375 | 27 | 9.99 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.bipartite.basic.py-82-4-return | return at networkx/algorithms/bipartite/basic.py:82 | 38 | 26.99 | 0.02 | 1 |
| mutant | m42-networkx.generators.small.py-1106-12-constant | constant at networkx/generators/small.py:1106 | 2 | 44.55 | 0.04 | 1 |
| mutant | m42-networkx.generators.line.py-278-8-return | return at networkx/generators/line.py:278 | 1 | 284.44 | 0.16 | 1 |
| mutant | m42-networkx.generators.random_graphs.py-710-37-compare | compare at networkx/generators/random_graphs.py:710 | 2 | 290.55 | 5.70 | 1 |
| mutant | m42-networkx.generators.joint_degree_seq.py-236-16-compare | compare at networkx/generators/joint_degree_seq.py:236 | 1 | 280.98 | 0.05 | 1 |
| mutant | m42-networkx.algorithms.cycles.py-391-24-constant | constant at networkx/algorithms/cycles.py:391 | 3 | 138.89 | 0.58 | 3 |
| mutant | m42-networkx.algorithms.tree.coding.py-413-4-return | return at networkx/algorithms/tree/coding.py:413 | 505 | 141.47 | 0.05 | 1 |
| mutant | m42-networkx.algorithms.centrality.betweenness.py-535-29-constant | constant at networkx/algorithms/centrality/betweenness.py:53 | 14 | 29.96 | 0.02 | 1 |
| mutant | m42-networkx.algorithms.core.py-588-4-return | return at networkx/algorithms/core.py:588 | 1 | 138.53 | 0.18 | 1 |
| mutant | m42-networkx.algorithms.centrality.laplacian.py-144-20-arith | arith at networkx/algorithms/centrality/laplacian.py:144 | 7 | 33.93 | 0.04 | 1 |
| mutant | m42-networkx.drawing.layout.py-1169-14-constant | constant at networkx/drawing/layout.py:1169 | 2 | 249.25 | 9.16 | 16 |
| mutant | m42-networkx.algorithms.traversal.edgedfs.py-153-33-compare | compare at networkx/algorithms/traversal/edgedfs.py:153 | 3 | 140.21 | 0.07 | 1 |
| mutant | m42-networkx.algorithms.triads.py-492-20-return | return at networkx/algorithms/triads.py:492 | 2 | 196.04 | 0.08 | 1 |
| mutant | m42-networkx.classes.function.py-1148-7-compare | compare at networkx/classes/function.py:1148 | 55 | 186.24 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.operators.binary.py-234-4-return | return at networkx/algorithms/operators/binary.py:234 | 4 | 126.15 | 0.07 | 1 |
| mutant | m42-networkx.classes.coreviews.py-60-8-return | return at networkx/classes/coreviews.py:60 | 4 | 207.45 | 0.07 | 1 |
| mutant | m42-networkx.algorithms.tree.coding.py-395-44-compare | compare at networkx/algorithms/tree/coding.py:395 | 447 | 141.47 | 0.05 | 1 |
| mutant | m42-networkx.algorithms.shortest_paths.dense.py-101-7-compare | compare at networkx/algorithms/shortest_paths/dense.py:101 | 10 | 135.50 | 0.01 | 1 |
| mutant | m42-networkx.generators.small.py-264-19-constant | constant at networkx/generators/small.py:264 | 7 | 27.96 | 0.04 | 1 |
| mutant | m42-networkx.generators.trees.py-375-77-constant | constant at networkx/generators/trees.py:375 | 331 | 141.47 | 0.07 | 1 |
| mutant | m42-networkx.algorithms.operators.binary.py-220-11-compare | compare at networkx/algorithms/operators/binary.py:220 | 5 | 126.15 | 0.07 | 1 |
| mutant | m42-networkx.generators.small.py-1000-12-constant | constant at networkx/generators/small.py:1000 | 1 | 292.71 | 0.04 | 1 |
| mutant | m42-networkx.algorithms.centrality.group.py-577-40-constant | constant at networkx/algorithms/centrality/group.py:577 | 5 | 33.09 | 0.24 | 1 |
| mutant | m42-networkx.algorithms.tournament.py-141-7-compare | compare at networkx/algorithms/tournament.py:141 | 3 | 195.87 | 0.10 | 1 |
| mutant | m42-networkx.algorithms.distance_regular.py-113-16-arith | arith at networkx/algorithms/distance_regular.py:113 | 1 | 165.01 | 0.09 | 1 |
| mutant | m42-networkx.algorithms.graphical.py-266-27-arith | arith at networkx/algorithms/graphical.py:266 | 17 | 185.28 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.flow.gomory_hu.py-173-34-compare | compare at networkx/algorithms/flow/gomory_hu.py:173 | 6 | 56.25 | 1.18 | 2 |
| mutant | m42-networkx.drawing.nx_pylab.py-1992-32-constant | constant at networkx/drawing/nx_pylab.py:1992 | 56 | 268.18 | 9.08 | 14 |
| mutant | m42-networkx.algorithms.matching.py-905-18-compare | compare at networkx/algorithms/matching.py:905 | 46 | 14.69 | 0.31 | 1 |
| mutant | m42-networkx.algorithms.traversal.edgebfs.py-146-22-arith | arith at networkx/algorithms/traversal/edgebfs.py:146 | 3 | 197.30 | 0.12 | 1 |
| mutant | m42-networkx.algorithms.connectivity.edge_augmentation.py-814-59-compare | compare at networkx/algorithms/connectivity/edge_augmentatio | 4 | 47.42 | 0.45 | 1 |
| mutant | m42-networkx.algorithms.flow.utils.py-188-76-constant | constant at networkx/algorithms/flow/utils.py:188 | 8 | 63.90 | 2.46 | 4 |
| mutant | m42-networkx.generators.social.py-464-47-constant | constant at networkx/generators/social.py:464 | 1 | 30.38 | 0.90 | 2 |
| mutant | m42-networkx.algorithms.isomorphism.tree_isomorphism.py-56-23-arith | arith at networkx/algorithms/isomorphism/tree_isomorphism.py | 13 | 110.88 | 0.27 | 2 |
| mutant | m42-networkx.generators.small.py-588-12-constant | constant at networkx/generators/small.py:588 | 8 | 9.99 | 0.04 | 1 |
| mutant | m42-networkx.algorithms.isomorphism.vf2pp.py-854-57-compare | compare at networkx/algorithms/isomorphism/vf2pp.py:854 | 197 | 69.47 | 0.26 | 1 |
| mutant | m42-networkx.utils.mapped_queue.py-229-18-arith | arith at networkx/utils/mapped_queue.py:229 | 15 | 39.67 | 0.41 | 2 |
| mutant | m42-networkx.generators.community.py-718-19-arith | arith at networkx/generators/community.py:718 | 1 | 276.20 | 1.14 | 1 |
| mutant | m42-networkx.convert_matrix.py-438-33-compare | compare at networkx/convert_matrix.py:438 | 2 | 306.67 | 0.26 | 1 |
| mutant | m42-networkx.algorithms.matching.py-434-11-compare | compare at networkx/algorithms/matching.py:434 | 46 | 14.69 | 0.31 | 1 |
| mutant | m42-networkx.algorithms.isomorphism.isomorphvf2.py-762-11-compare | compare at networkx/algorithms/isomorphism/isomorphvf2.py:76 | 6 | 95.62 | 11.45 | 11 |
| mutant | m42-networkx.algorithms.community.leiden.py-151-24-constant | constant at networkx/algorithms/community/leiden.py:151 | 4 | 38.10 | 1.80 | 1 |
| mutant | m42-networkx.algorithms.isomorphism.isomorphvf2.py-1193-19-compare | compare at networkx/algorithms/isomorphism/isomorphvf2.py:11 | 92 | 70.13 | 0.07 | 1 |
| mutant | m42-networkx.algorithms.centrality.voterank_alg.py-79-25-constant | constant at networkx/algorithms/centrality/voterank_alg.py:7 | 5 | 34.90 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.components.semiconnected.py-61-7-compare | compare at networkx/algorithms/components/semiconnected.py:6 | 6 | 43.81 | 0.02 | 1 |
| mutant | m42-networkx.readwrite.graph6.py-415-44-constant | constant at networkx/readwrite/graph6.py:415 | 7 | 297.46 | 0.03 | 1 |
| mutant | m42-networkx.algorithms.regular.py-38-19-compare | compare at networkx/algorithms/regular.py:38 | 18 | 165.00 | 0.26 | 1 |
| mutant | m42-networkx.readwrite.gml.py-443-16-return | return at networkx/readwrite/gml.py:443 | 1 | 297.40 | 0.30 | 1 |
| mutant | m42-networkx.algorithms.isomorphism.isomorphvf2.py-898-19-boolop | boolop at networkx/algorithms/isomorphism/isomorphvf2.py:898 | 156 | 69.67 | 0.07 | 1 |
| mutant | m42-networkx.readwrite.gexf.py-429-11-compare | compare at networkx/readwrite/gexf.py:429 | 24 | 296.77 | 0.04 | 1 |
| mutant | m42-networkx.algorithms.assortativity.neighbor_degree.py-151-11-compare | compare at networkx/algorithms/assortativity/neighbor_degree | 2 | 26.84 | 0.02 | 1 |
| mutant | m42-networkx.generators.small.py-994-16-constant | constant at networkx/generators/small.py:994 | 1 | 292.71 | 0.04 | 1 |
| mutant | m42-networkx.algorithms.coloring.equitable_coloring.py-144-7-compare | compare at networkx/algorithms/coloring/equitable_coloring.p | 6 | 35.03 | 0.10 | 1 |
| mutant | m42-networkx.algorithms.planar_drawing.py-232-44-constant | constant at networkx/algorithms/planar_drawing.py:232 | 8 | 188.99 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.smallworld.py-193-14-arith | arith at networkx/algorithms/smallworld.py:193 | 2 | 193.93 | 0.06 | 1 |
| mutant | m42-networkx.algorithms.shortest_paths.unweighted.py-609-11-boolop | boolop at networkx/algorithms/shortest_paths/unweighted.py:6 | 24 | 34.01 | 0.11 | 1 |
| mutant | m42-networkx.algorithms.shortest_paths.weighted.py-867-38-compare | compare at networkx/algorithms/shortest_paths/weighted.py:86 | 2 | 136.10 | 0.45 | 3 |
| mutant | m42-networkx.algorithms.shortest_paths.astar.py-128-11-compare | compare at networkx/algorithms/shortest_paths/astar.py:128 | 20 | 126.74 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.flow.networksimplex.py-608-8-compare | compare at networkx/algorithms/flow/networksimplex.py:608 | 2 | 67.47 | 0.25 | 1 |
| mutant | m42-networkx.algorithms.simple_paths.py-73-7-compare | compare at networkx/algorithms/simple_paths.py:73 | 6 | 193.08 | 0.01 | 1 |
| mutant | m42-networkx.generators.random_graphs.py-109-8-constant | constant at networkx/generators/random_graphs.py:109 | 4 | 285.67 | 6.06 | 6 |
| mutant | m42-networkx.algorithms.centrality.current_flow_betweenness_subset.py-213-26-arith | arith at networkx/algorithms/centrality/current_flow_between | 3 | 32.48 | 0.08 | 1 |
| mutant | m42-networkx.generators.social.py-532-49-constant | constant at networkx/generators/social.py:532 | 1 | 30.38 | 0.90 | 2 |
| mutant | m42-networkx.readwrite.text.py-263-13-constant | constant at networkx/readwrite/text.py:263 | 11 | 300.62 | 0.27 | 2 |
| mutant | m42-networkx.algorithms.shortest_paths.weighted.py-1379-7-compare | compare at networkx/algorithms/shortest_paths/weighted.py:13 | 39 | 67.36 | 0.03 | 1 |
| mutant | m42-networkx.readwrite.gml.py-78-12-return | return at networkx/readwrite/gml.py:78 | 3 | 297.19 | 0.09 | 1 |
| mutant | m42-networkx.classes.multidigraph.py-943-19-boolop | boolop at networkx/classes/multidigraph.py:943 | 2 | 240.50 | 2.59 | 1 |
| mutant | m42-networkx.algorithms.triads.py-461-22-constant | constant at networkx/algorithms/triads.py:461 | 4 | 196.04 | 0.08 | 1 |
| mutant | m42-networkx.algorithms.centrality.group.py-562-11-compare | compare at networkx/algorithms/centrality/group.py:562 | 3 | 33.28 | 0.43 | 1 |
| mutant | m42-networkx.algorithms.centrality.current_flow_betweenness.py-359-50-constant | constant at networkx/algorithms/centrality/current_flow_betw | 9 | 32.34 | 0.08 | 1 |
| mutant | m42-networkx.generators.community.py-641-26-constant | constant at networkx/generators/community.py:641 | 2 | 275.08 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.centrality.betweenness_subset.py-230-45-arith | arith at networkx/algorithms/centrality/betweenness_subset.p | 4 | 30.68 | 0.12 | 1 |
| mutant | m42-networkx.algorithms.centrality.betweenness.py-468-11-compare | compare at networkx/algorithms/centrality/betweenness.py:468 | 47 | 27.11 | 0.19 | 1 |
| mutant | m42-networkx.classes.filters.py-29-24-compare | compare at networkx/classes/filters.py:29 | 29 | 51.92 | 0.02 | 1 |
| mutant | m42-networkx.generators.nonisomorphic_trees.py-67-16-constant | constant at networkx/generators/nonisomorphic_trees.py:67 | 3 | 110.89 | 0.02 | 1 |
| mutant | m42-networkx.drawing.layout.py-1699-17-constant | constant at networkx/drawing/layout.py:1699 | 1 | 252.70 | 12.61 | 16 |
| mutant | m42-networkx.algorithms.shortest_paths.generic.py-586-7-compare | compare at networkx/algorithms/shortest_paths/generic.py:586 | 3 | 135.64 | 0.07 | 1 |
| mutant | m42-networkx.algorithms.isomorphism.ismags.py-657-85-constant | constant at networkx/algorithms/isomorphism/ismags.py:657 | 100 | 80.73 | 1.90 | 1 |
| mutant | m42-networkx.classes.reportviews.py-719-12-boolop | boolop at networkx/classes/reportviews.py:719 | 15 | 25.59 | 0.15 | 1 |
| mutant | m42-networkx.algorithms.flow.networksimplex.py-114-14-compare | compare at networkx/algorithms/flow/networksimplex.py:114 | 30 | 24.78 | 0.07 | 1 |
| mutant | m42-networkx.algorithms.traversal.breadth_first_search.py-556-21-compare | compare at networkx/algorithms/traversal/breadth_first_searc | 5 | 140.45 | 0.10 | 1 |
| mutant | m42-networkx.algorithms.community.asyn_fluid.py-131-19-compare | compare at networkx/algorithms/community/asyn_fluid.py:131 | 5 | 35.14 | 0.04 | 1 |
| mutant | m42-networkx.algorithms.asteroidal.py-73-17-arith | arith at networkx/algorithms/asteroidal.py:73 | 1 | 136.66 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.coloring.greedy_coloring.py-514-29-constant | constant at networkx/algorithms/coloring/greedy_coloring.py: | 1 | 34.97 | 0.03 | 1 |
| mutant | m42-networkx.generators.random_graphs.py-1303-29-constant | constant at networkx/generators/random_graphs.py:1303 | 2 | 52.38 | 0.76 | 1 |
| mutant | m42-networkx.algorithms.isomorphism.temporalisomorphvf2.py-141-8-return | return at networkx/algorithms/isomorphism/temporalisomorphvf | 5 | 110.74 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.chordal.py-318-7-compare | compare at networkx/algorithms/chordal.py:318 | 14 | 137.25 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.connectivity.connectivity.py-349-56-arith | arith at networkx/algorithms/connectivity/connectivity.py:34 | 11 | 44.39 | 1.44 | 1 |
| mutant | m42-networkx.algorithms.core.py-488-4-return | return at networkx/algorithms/core.py:488 | 1 | 138.49 | 0.15 | 1 |
| mutant | m42-networkx.algorithms.dag.py-1344-4-return | return at networkx/algorithms/dag.py:1344 | 4 | 141.33 | 0.69 | 1 |
| mutant | m42-networkx.generators.trees.py-746-38-arith | arith at networkx/generators/trees.py:746 | 2 | 293.55 | 0.21 | 1 |
| mutant | m42-networkx.algorithms.triads.py-469-16-constant | constant at networkx/algorithms/triads.py:469 | 5 | 196.04 | 0.08 | 1 |
| mutant | m42-networkx.classes.reportviews.py-640-27-constant | constant at networkx/classes/reportviews.py:640 | 5 | 25.59 | 1.54 | 1 |
| mutant | m42-networkx.algorithms.matching.py-248-25-compare | compare at networkx/algorithms/matching.py:248 | 29 | 27.93 | 0.03 | 1 |
| mutant | m42-networkx.algorithms.approximation.treewidth.py-255-4-return | return at networkx/algorithms/approximation/treewidth.py:255 | 8 | 25.42 | 0.01 | 1 |
| mutant | m42-networkx.utils.rcm.py-139-71-constant | constant at networkx/utils/rcm.py:139 | 47 | 31.11 | 0.17 | 1 |
| mutant | m42-networkx.algorithms.reciprocity.py-98-4-return | return at networkx/algorithms/reciprocity.py:98 | 1 | 189.77 | 0.01 | 1 |
| mutant | m42-networkx.readwrite.leda.py-92-11-compare | compare at networkx/readwrite/leda.py:92 | 1 | 298.80 | 0.01 | 1 |
| mutant | m42-networkx.readwrite.gml.py-74-58-constant | constant at networkx/readwrite/gml.py:74 | 1 | 297.30 | 0.19 | 1 |
| mutant | m42-networkx.algorithms.community.label_propagation.py-294-4-return | return at networkx/algorithms/community/label_propagation.py | 5 | 35.62 | 0.03 | 1 |
| mutant | m42-networkx.algorithms.planar_drawing.py-132-7-compare | compare at networkx/algorithms/planar_drawing.py:132 | 8 | 188.99 | 0.01 | 1 |
| mutant | m42-networkx.generators.sudoku.py-93-7-compare | compare at networkx/generators/sudoku.py:93 | 6 | 293.20 | 0.01 | 1 |
| mutant | m42-networkx.generators.small.py-778-12-constant | constant at networkx/generators/small.py:778 | 1 | 39.60 | 3.45 | 7 |
| mutant | m42-networkx.algorithms.tree.branchings.py-684-18-arith | arith at networkx/algorithms/tree/branchings.py:684 | 9 | 18.90 | 56.66 | 108 |
| mutant | m42-networkx.generators.triads.py-86-7-compare | compare at networkx/generators/triads.py:86 | 2 | 293.59 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.similarity.py-1171-15-compare | compare at networkx/algorithms/similarity.py:1171 | 1 | 190.83 | 1.18 | 4 |
| mutant | m42-networkx.drawing.nx_pylab.py-667-53-constant | constant at networkx/drawing/nx_pylab.py:667 | 25 | 265.63 | 6.52 | 14 |
| mutant | m42-networkx.algorithms.euler.py-122-39-constant | constant at networkx/algorithms/euler.py:122 | 8 | 25.09 | 0.05 | 1 |
| mutant | m42-networkx.generators.internet_as_graphs.py-138-11-compare | compare at networkx/generators/internet_as_graphs.py:138 | 5 | 280.74 | 0.16 | 1 |
| mutant | m42-networkx.algorithms.components.biconnected.py-392-15-compare | compare at networkx/algorithms/components/biconnected.py:392 | 6 | 43.62 | 0.01 | 1 |
| mutant | m42-networkx.readwrite.text.py-824-18-compare | compare at networkx/readwrite/text.py:824 | 4 | 302.17 | 1.82 | 2 |
| mutant | m42-networkx.algorithms.planarity.py-170-4-return | return at networkx/algorithms/planarity.py:170 | 9 | 189.19 | 0.05 | 1 |
| mutant | m42-networkx.algorithms.centrality.group.py-186-30-compare | compare at networkx/algorithms/centrality/group.py:186 | 10 | 32.87 | 0.02 | 1 |
| mutant | m42-networkx.algorithms.clique.py-401-8-return | return at networkx/algorithms/clique.py:401 | 1 | 137.58 | 0.07 | 1 |
| mutant | m42-networkx.algorithms.link_analysis.pagerank_alg.py-131-17-constant | constant at networkx/algorithms/link_analysis/pagerank_alg.p | 2 | 124.58 | 0.21 | 1 |
| mutant | m42-networkx.generators.intersection.py-48-4-return | return at networkx/generators/intersection.py:48 | 1 | 280.83 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.centrality.reaching.py-26-22-constant | constant at networkx/algorithms/centrality/reaching.py:26 | 6 | 34.26 | 0.03 | 1 |
| mutant | m42-networkx.algorithms.cluster.py-657-20-arith | arith at networkx/algorithms/cluster.py:657 | 2 | 138.19 | 0.37 | 1 |
| mutant | m42-networkx.algorithms.connectivity.edge_augmentation.py-58-7-compare | compare at networkx/algorithms/connectivity/edge_augmentatio | 12 | 47.03 | 0.06 | 1 |
| mutant | m42-networkx.generators.social.py-502-46-constant | constant at networkx/generators/social.py:502 | 1 | 30.38 | 0.90 | 2 |
| mutant | m42-networkx.generators.joint_degree_seq.py-328-7-compare | compare at networkx/generators/joint_degree_seq.py:328 | 2 | 280.99 | 0.06 | 1 |
| mutant | m42-networkx.generators.line.py-190-52-constant | constant at networkx/generators/line.py:190 | 14 | 136.66 | 0.01 | 1 |
| mutant | m42-networkx.generators.random_graphs.py-706-7-compare | compare at networkx/generators/random_graphs.py:706 | 10 | 185.14 | 0.08 | 1 |
| mutant | m42-networkx.readwrite.json_graph.node_link.py-244-55-compare | compare at networkx/readwrite/json_graph/node_link.py:244 | 4 | 295.82 | 0.03 | 1 |
| mutant | m42-networkx.classes.coreviews.py-107-8-return | return at networkx/classes/coreviews.py:107 | 2 | 207.59 | 0.21 | 1 |
| mutant | m42-networkx.algorithms.centrality.subgraph_alg.py-287-23-constant | constant at networkx/algorithms/centrality/subgraph_alg.py:2 | 2 | 34.77 | 0.32 | 1 |
| mutant | m42-networkx.drawing.nx_pylab.py-203-35-constant | constant at networkx/drawing/nx_pylab.py:203 | 3 | 273.37 | 14.26 | 14 |
| mutant | m42-networkx.algorithms.lowest_common_ancestors.py-118-23-compare | compare at networkx/algorithms/lowest_common_ancestors.py:11 | 21 | 187.35 | 0.24 | 1 |
| mutant | m42-networkx.generators.small.py-1079-16-constant | constant at networkx/generators/small.py:1079 | 2 | 44.55 | 0.04 | 1 |
| mutant | m42-networkx.algorithms.flow.capacityscaling.py-149-4-return | return at networkx/algorithms/flow/capacityscaling.py:149 | 13 | 67.33 | 0.49 | 3 |
| mutant | m42-networkx.algorithms.tree.branchings.py-174-15-compare | compare at networkx/algorithms/tree/branchings.py:174 | 4 | 197.51 | 0.30 | 2 |
| mutant | m42-networkx.algorithms.distance_measures.py-717-25-compare | compare at networkx/algorithms/distance_measures.py:717 | 504 | 141.47 | 0.68 | 4 |
| mutant | m42-networkx.algorithms.chains.py-146-7-boolop | boolop at networkx/algorithms/chains.py:146 | 35 | 47.03 | 0.01 | 1 |
| mutant | m42-networkx.generators.small.py-1004-12-constant | constant at networkx/generators/small.py:1004 | 1 | 292.71 | 0.04 | 1 |
| mutant | m42-networkx.algorithms.connectivity.kcutsets.py-138-23-arith | arith at networkx/algorithms/connectivity/kcutsets.py:138 | 32 | 51.92 | 0.39 | 1 |
| mutant | m42-networkx.algorithms.link_prediction.py-670-19-constant | constant at networkx/algorithms/link_prediction.py:670 | 2 | 187.04 | 0.81 | 1 |
| mutant | m42-networkx.algorithms.isomorphism.tree_isomorphism.py-179-32-compare | compare at networkx/algorithms/isomorphism/tree_isomorphism. | 19 | 110.88 | 0.27 | 2 |
| mutant | m42-networkx.linalg.attrmatrix.py-97-23-constant | constant at networkx/linalg/attrmatrix.py:97 | 3 | 295.21 | 0.02 | 1 |
| mutant | m42-networkx.readwrite.gml.py-337-38-constant | constant at networkx/readwrite/gml.py:337 | 7 | 297.13 | 0.02 | 1 |
| mutant | m42-networkx.algorithms.link_prediction.py-489-84-constant | constant at networkx/algorithms/link_prediction.py:489 | 3 | 186.77 | 0.54 | 1 |
| mutant | m42-networkx.algorithms.cycles.py-948-30-compare | compare at networkx/algorithms/cycles.py:948 | 10 | 140.16 | 1.85 | 3 |
| mutant | m42-networkx.algorithms.threshold.py-500-33-constant | constant at networkx/algorithms/threshold.py:500 | 1 | 195.63 | 0.15 | 1 |
| mutant | m42-networkx.algorithms.flow.networksimplex.py-514-11-compare | compare at networkx/algorithms/flow/networksimplex.py:514 | 50 | 24.78 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.connectivity.edge_augmentation.py-501-7-compare | compare at networkx/algorithms/connectivity/edge_augmentatio | 1 | 47.03 | 0.06 | 1 |
| mutant | m42-networkx.algorithms.components.biconnected.py-343-11-compare | compare at networkx/algorithms/components/biconnected.py:343 | 33 | 9.99 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.cluster.py-535-7-compare | compare at networkx/algorithms/cluster.py:535 | 3 | 138.13 | 0.31 | 1 |
| mutant | m42-networkx.algorithms.tree.branchings.py-592-25-constant | constant at networkx/algorithms/tree/branchings.py:592 | 38 | 18.90 | 0.36 | 2 |
| mutant | m42-networkx.algorithms.threshold.py-114-18-constant | constant at networkx/algorithms/threshold.py:114 | 3 | 195.52 | 0.03 | 1 |
| mutant | m42-networkx.algorithms.connectivity.connectivity.py-537-4-return | return at networkx/algorithms/connectivity/connectivity.py:5 | 9 | 44.82 | 0.79 | 1 |
| mutant | m42-networkx.linalg.attrmatrix.py-92-16-return | return at networkx/linalg/attrmatrix.py:92 | 1 | 295.22 | 0.03 | 1 |
| mutant | m42-networkx.algorithms.cluster.py-611-12-return | return at networkx/algorithms/cluster.py:611 | 10 | 137.83 | 0.01 | 1 |
| mutant | m42-networkx.generators.line.py-304-53-constant | constant at networkx/generators/line.py:304 | 14 | 284.38 | 0.10 | 1 |
| mutant | m42-networkx.algorithms.broadcasting.py-26-4-return | return at networkx/algorithms/broadcasting.py:26 | 24 | 136.88 | 0.01 | 1 |
| mutant | m42-networkx.convert_matrix.py-446-7-boolop | boolop at networkx/convert_matrix.py:446 | 1 | 306.76 | 0.35 | 1 |
| mutant | m42-networkx.algorithms.threshold.py-114-11-compare | compare at networkx/algorithms/threshold.py:114 | 3 | 195.52 | 0.03 | 1 |
| mutant | m42-networkx.algorithms.similarity.py-1927-18-arith | arith at networkx/algorithms/similarity.py:1927 | 4 | 191.98 | 2.33 | 4 |
| mutant | m42-networkx.algorithms.community.divisive.py-214-33-compare | compare at networkx/algorithms/community/divisive.py:214 | 1 | 35.51 | 0.17 | 1 |
| mutant | m42-networkx.algorithms.connectivity.edge_kcomponents.py-402-15-constant | constant at networkx/algorithms/connectivity/edge_kcomponent | 15 | 48.96 | 0.27 | 1 |
| mutant | m42-networkx.algorithms.tournament.py-259-4-return | return at networkx/algorithms/tournament.py:259 | 1 | 195.92 | 0.14 | 1 |
| mutant | m42-networkx.algorithms.shortest_paths.dense.py-394-10-compare | compare at networkx/algorithms/shortest_paths/dense.py:394 | 2 | 126.93 | 0.03 | 1 |
| mutant | m42-networkx.algorithms.bipartite.basic.py-140-7-compare | compare at networkx/algorithms/bipartite/basic.py:140 | 1 | 27.05 | 0.08 | 1 |
| mutant | m42-networkx.algorithms.community.leiden.py-631-37-constant | constant at networkx/algorithms/community/leiden.py:631 | 32 | 36.48 | 0.17 | 1 |
| mutant | m42-networkx.algorithms.shortest_paths.weighted.py-2437-46-constant | constant at networkx/algorithms/shortest_paths/weighted.py:2 | 25 | 14.48 | 0.02 | 1 |
| mutant | m42-networkx.algorithms.connectivity.edge_augmentation.py-55-7-compare | compare at networkx/algorithms/connectivity/edge_augmentatio | 13 | 47.03 | 0.06 | 1 |
| mutant | m42-networkx.algorithms.community.divisive.py-99-10-compare | compare at networkx/algorithms/community/divisive.py:99 | 1 | 35.36 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.similarity.py-914-20-constant | constant at networkx/algorithms/similarity.py:914 | 15 | 190.83 | 1.18 | 4 |
| mutant | m42-networkx.algorithms.shortest_paths.weighted.py-2403-14-compare | compare at networkx/algorithms/shortest_paths/weighted.py:24 | 25 | 14.48 | 0.02 | 1 |
| mutant | m42-networkx.readwrite.pajek.py-90-15-boolop | boolop at networkx/readwrite/pajek.py:90 | 1 | 298.96 | 0.08 | 1 |
| mutant | m42-networkx.algorithms.threshold.py-600-7-compare | compare at networkx/algorithms/threshold.py:600 | 1 | 195.57 | 0.09 | 1 |
| mutant | m42-networkx.algorithms.flow.boykovkolmogorov.py-181-7-compare | compare at networkx/algorithms/flow/boykovkolmogorov.py:181 | 30 | 44.24 | 0.02 | 1 |
| mutant | m42-networkx.algorithms.boundary.py-163-10-arith | arith at networkx/algorithms/boundary.py:163 | 8 | 136.67 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.traversal.breadth_first_search.py-94-36-compare | compare at networkx/algorithms/traversal/breadth_first_searc | 61 | 34.96 | 0.01 | 1 |
| mutant | m42-networkx.readwrite.graph6.py-422-18-constant | constant at networkx/readwrite/graph6.py:422 | 1 | 297.46 | 0.03 | 1 |
| mutant | m42-networkx.algorithms.isomorphism.ismags.py-866-11-compare | compare at networkx/algorithms/isomorphism/ismags.py:866 | 392 | 70.89 | 0.01 | 1 |
| mutant | m42-networkx.generators.small.py-1113-17-constant | constant at networkx/generators/small.py:1113 | 2 | 44.55 | 0.04 | 1 |
| mutant | m42-networkx.algorithms.simple_paths.py-947-23-arith | arith at networkx/algorithms/simple_paths.py:947 | 10 | 193.71 | 0.63 | 1 |
| mutant | m42-networkx.generators.small.py-996-12-constant | constant at networkx/generators/small.py:996 | 1 | 292.71 | 0.04 | 1 |
| mutant | m42-networkx.algorithms.flow.preflowpush.py-183-19-arith | arith at networkx/algorithms/flow/preflowpush.py:183 | 6 | 55.09 | 7.23 | 8 |
| mutant | m42-networkx.utils.mapped_queue.py-44-11-compare | compare at networkx/utils/mapped_queue.py:44 | 19 | 39.67 | 0.01 | 1 |
| mutant | m42-networkx.linalg.modularitymatrix.py-161-23-constant | constant at networkx/linalg/modularitymatrix.py:161 | 2 | 295.56 | 0.03 | 1 |
| mutant | m42-networkx.classes.graphviews.py-219-12-return | return at networkx/classes/graphviews.py:219 | 9 | 124.01 | 0.11 | 1 |
| mutant | m42-networkx.algorithms.richclub.py-162-18-constant | constant at networkx/algorithms/richclub.py:162 | 4 | 190.19 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.isolate.py-86-40-compare | compare at networkx/algorithms/isolate.py:86 | 56 | 26.99 | 0.02 | 1 |
| mutant | m42-networkx.algorithms.threshold.py-217-8-constant | constant at networkx/algorithms/threshold.py:217 | 2 | 195.54 | 0.06 | 1 |
| mutant | m42-networkx.algorithms.centrality.betweenness.py-500-4-return | return at networkx/algorithms/centrality/betweenness.py:500 | 20 | 30.44 | 0.19 | 1 |
| mutant | m42-networkx.algorithms.community.modularity_max.py-156-54-arith | arith at networkx/algorithms/community/modularity_max.py:156 | 6 | 39.67 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.components.weakly_connected.py-194-15-compare | compare at networkx/algorithms/components/weakly_connected.p | 76 | 0.44 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.centrality.betweenness.py-450-31-compare | compare at networkx/algorithms/centrality/betweenness.py:450 | 25 | 30.26 | 0.09 | 1 |
| mutant | m42-networkx.algorithms.simple_paths.py-917-25-constant | constant at networkx/algorithms/simple_paths.py:917 | 1 | 193.85 | 0.78 | 1 |
| mutant | m42-networkx.generators.small.py-517-27-constant | constant at networkx/generators/small.py:517 | 1 | 292.71 | 0.04 | 1 |
| mutant | m42-networkx.generators.geometric.py-996-19-constant | constant at networkx/generators/geometric.py:996 | 1 | 279.13 | 1.13 | 2 |
| mutant | m42-networkx.algorithms.flow.gomory_hu.py-177-56-constant | constant at networkx/algorithms/flow/gomory_hu.py:177 | 5 | 56.25 | 1.18 | 2 |
| mutant | m42-networkx.algorithms.bipartite.generators.py-283-25-constant | constant at networkx/algorithms/bipartite/generators.py:283 | 1 | 28.44 | 0.04 | 1 |
| mutant | m42-networkx.generators.directed.py-74-7-compare | compare at networkx/generators/directed.py:74 | 8 | 30.98 | 0.23 | 1 |
| mutant | m42-networkx.algorithms.similarity.py-1390-7-arith | arith at networkx/algorithms/similarity.py:1390 | 1 | 191.72 | 2.07 | 4 |
| mutant | m42-networkx.algorithms.components.strongly_connected.py-123-23-compare | compare at networkx/algorithms/components/strongly_connected | 18 | 25.41 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.approximation.density.py-57-33-constant | constant at networkx/algorithms/approximation/density.py:57 | 2 | 1.97 | 1.41 | 1 |
| mutant | m42-networkx.algorithms.isomorphism.vf2pp.py-857-61-compare | compare at networkx/algorithms/isomorphism/vf2pp.py:857 | 136 | 69.47 | 0.26 | 1 |
| mutant | m42-networkx.algorithms.cycles.py-387-22-constant | constant at networkx/algorithms/cycles.py:387 | 8 | 138.84 | 0.53 | 3 |
| mutant | m42-networkx.algorithms.approximation.steinertree.py-146-4-return | return at networkx/algorithms/approximation/steinertree.py:1 | 7 | 14.47 | 0.04 | 1 |
| mutant | m42-networkx.generators.harary_graph.py-149-18-constant | constant at networkx/generators/harary_graph.py:149 | 1 | 280.58 | 0.03 | 1 |
| mutant | m42-networkx.algorithms.flow.shortestaugmentingpath.py-21-7-compare | compare at networkx/algorithms/flow/shortestaugmentingpath.p | 62 | 44.06 | 0.02 | 1 |
| mutant | m42-networkx.algorithms.bipartite.cluster.py-424-30-constant | constant at networkx/algorithms/bipartite/cluster.py:424 | 22 | 27.22 | 0.06 | 1 |
| mutant | m42-networkx.algorithms.flow.capacityscaling.py-306-19-constant | constant at networkx/algorithms/flow/capacityscaling.py:306 | 10 | 67.33 | 0.49 | 3 |
| mutant | m42-networkx.algorithms.shortest_paths.generic.py-174-17-compare | compare at networkx/algorithms/shortest_paths/generic.py:174 | 1 | 140.28 | 3.61 | 12 |
| mutant | m42-networkx.readwrite.graphml.py-1072-15-compare | compare at networkx/readwrite/graphml.py:1072 | 11 | 298.29 | 0.07 | 1 |
| mutant | m42-networkx.algorithms.dag.py-587-19-compare | compare at networkx/algorithms/dag.py:587 | 6 | 140.83 | 0.19 | 1 |
| mutant | m42-networkx.generators.social.py-49-48-constant | constant at networkx/generators/social.py:49 | 1 | 35.27 | 48.04 | 26 |
| mutant | m42-networkx.generators.internet_as_graphs.py-265-31-constant | constant at networkx/generators/internet_as_graphs.py:265 | 1 | 280.81 | 0.23 | 1 |
| mutant | m42-networkx.algorithms.connectivity.cuts.py-313-8-return | return at networkx/algorithms/connectivity/cuts.py:313 | 6 | 46.45 | 1.37 | 1 |
| mutant | m42-networkx.readwrite.gml.py-729-26-arith | arith at networkx/readwrite/gml.py:729 | 6 | 297.16 | 0.05 | 1 |
| mutant | m42-networkx.algorithms.bipartite.matrix.py-210-4-return | return at networkx/algorithms/bipartite/matrix.py:210 | 39 | 29.25 | 0.09 | 1 |
| mutant | m42-networkx.algorithms.centrality.dispersion.py-80-15-compare | compare at networkx/algorithms/centrality/dispersion.py:80 | 3 | 32.70 | 0.02 | 1 |
| mutant | m42-networkx.utils.heaps.py-326-56-compare | compare at networkx/utils/heaps.py:326 | 6 | 35.18 | 0.02 | 1 |
| mutant | m42-networkx.generators.small.py-778-22-constant | constant at networkx/generators/small.py:778 | 9 | 0.37 | 0.37 | 2 |
| mutant | m42-networkx.generators.lattice.py-277-60-constant | constant at networkx/generators/lattice.py:277 | 2 | 284.17 | 0.37 | 1 |
| mutant | m42-networkx.algorithms.tree.branchings.py-156-34-constant | constant at networkx/algorithms/tree/branchings.py:156 | 1 | 197.53 | 0.32 | 2 |
| mutant | m42-networkx.algorithms.bipartite.link_analysis.py-312-7-compare | compare at networkx/algorithms/bipartite/link_analysis.py:31 | 36 | 28.57 | 0.02 | 1 |
| mutant | m42-networkx.algorithms.community.modularity_max.py-135-15-compare | compare at networkx/algorithms/community/modularity_max.py:1 | 15 | 39.67 | 0.01 | 1 |
| mutant | m42-networkx.generators.small.py-998-12-constant | constant at networkx/generators/small.py:998 | 1 | 292.71 | 0.04 | 1 |
| mutant | m42-networkx.drawing.nx_pylab.py-2056-43-constant | constant at networkx/drawing/nx_pylab.py:2056 | 117 | 268.18 | 9.08 | 14 |
| mutant | m42-networkx.algorithms.efficiency_measures.py-104-21-constant | constant at networkx/algorithms/efficiency_measures.py:104 | 4 | 166.10 | 0.04 | 1 |
| mutant | m42-networkx.algorithms.structuralholes.py-49-16-compare | compare at networkx/algorithms/structuralholes.py:49 | 12 | 194.65 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.link_analysis.pagerank_alg.py-274-4-return | return at networkx/algorithms/link_analysis/pagerank_alg.py: | 10 | 124.43 | 0.06 | 1 |
| mutant | m42-networkx.algorithms.coloring.greedy_coloring.py-512-26-compare | compare at networkx/algorithms/coloring/greedy_coloring.py:5 | 2 | 34.96 | 0.02 | 1 |
| mutant | m42-networkx.algorithms.non_randomness.py-142-70-constant | constant at networkx/algorithms/non_randomness.py:142 | 1 | 188.90 | 0.10 | 1 |
| mutant | m42-networkx.algorithms.connectivity.disjoint_paths.py-371-7-compare | compare at networkx/algorithms/connectivity/disjoint_paths.p | 18 | 27.95 | 0.02 | 1 |
| mutant | m42-networkx.algorithms.centrality.group.py-468-11-arith | arith at networkx/algorithms/centrality/group.py:468 | 6 | 33.09 | 0.24 | 1 |
| mutant | m42-networkx.algorithms.matching.py-554-23-compare | compare at networkx/algorithms/matching.py:554 | 47 | 14.69 | 0.31 | 1 |
| mutant | m42-networkx.algorithms.threshold.py-650-19-arith | arith at networkx/algorithms/threshold.py:650 | 2 | 195.57 | 0.09 | 1 |
| mutant | m42-networkx.generators.joint_degree_seq.py-652-27-compare | compare at networkx/generators/joint_degree_seq.py:652 | 1 | 283.80 | 2.88 | 1 |
| mutant | m42-networkx.generators.social.py-424-56-constant | constant at networkx/generators/social.py:424 | 1 | 30.38 | 0.90 | 2 |
| mutant | m42-networkx.algorithms.traversal.edgebfs.py-125-7-compare | compare at networkx/algorithms/traversal/edgebfs.py:125 | 50 | 29.06 | 0.02 | 1 |
| mutant | m42-networkx.algorithms.bipartite.link_analysis.py-263-27-constant | constant at networkx/algorithms/bipartite/link_analysis.py:2 | 31 | 28.57 | 0.02 | 1 |
| mutant | m42-networkx.algorithms.centrality.group.py-434-29-arith | arith at networkx/algorithms/centrality/group.py:434 | 1 | 33.40 | 0.55 | 1 |
| mutant | m42-networkx.generators.small.py-1009-17-constant | constant at networkx/generators/small.py:1009 | 1 | 292.71 | 0.04 | 1 |
| mutant | m42-networkx.algorithms.approximation.traveling_salesman.py-1239-15-compare | compare at networkx/algorithms/approximation/traveling_sales | 3 | 14.86 | 0.21 | 2 |
| mutant | m42-networkx.algorithms.community.modularity_max.py-206-27-compare | compare at networkx/algorithms/community/modularity_max.py:2 | 14 | 39.67 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.bipartite.community.py-160-15-arith | arith at networkx/algorithms/bipartite/community.py:160 | 19 | 27.47 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.bipartite.cluster.py-125-16-arith | arith at networkx/algorithms/bipartite/cluster.py:125 | 3 | 27.18 | 0.02 | 1 |
| mutant | m42-networkx.utils.random_sequence.py-58-7-arith | arith at networkx/utils/random_sequence.py:58 | 17 | 48.22 | 0.05 | 1 |
| mutant | m42-networkx.drawing.layout.py-2027-7-compare | compare at networkx/drawing/layout.py:2027 | 7 | 253.20 | 13.10 | 16 |
| mutant | m42-networkx.algorithms.connectivity.cuts.py-144-7-compare | compare at networkx/algorithms/connectivity/cuts.py:144 | 16 | 48.96 | 3.41 | 10 |
| mutant | m42-networkx.algorithms.assortativity.mixing.py-54-4-return | return at networkx/algorithms/assortativity/mixing.py:54 | 15 | 26.59 | 0.10 | 1 |
| mutant | m42-networkx.readwrite.json_graph.cytoscape.py-90-36-constant | constant at networkx/readwrite/json_graph/cytoscape.py:90 | 4 | 295.74 | 0.01 | 1 |
| mutant | m42-networkx.generators.time_series.py-68-61-arith | arith at networkx/generators/time_series.py:68 | 3 | 293.31 | 0.04 | 1 |
| mutant | m42-networkx.algorithms.isomorphism.vf2pp.py-974-19-compare | compare at networkx/algorithms/isomorphism/vf2pp.py:974 | 30 | 70.70 | 0.65 | 1 |
| mutant | m42-networkx.algorithms.matching.py-134-11-boolop | boolop at networkx/algorithms/matching.py:134 | 3 | 187.66 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.connectivity.connectivity.py-324-41-compare | compare at networkx/algorithms/connectivity/connectivity.py: | 9 | 44.24 | 0.02 | 1 |
| mutant | m42-networkx.algorithms.community.divisive.py-216-4-return | return at networkx/algorithms/community/divisive.py:216 | 1 | 35.51 | 0.17 | 1 |
| mutant | m42-networkx.algorithms.centrality.trophic.py-71-29-constant | constant at networkx/algorithms/centrality/trophic.py:71 | 8 | 34.80 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.bipartite.cluster.py-261-7-compare | compare at networkx/algorithms/bipartite/cluster.py:261 | 2 | 27.22 | 0.06 | 1 |
| mutant | m42-networkx.algorithms.similarity.py-1013-44-compare | compare at networkx/algorithms/similarity.py:1013 | 19 | 190.83 | 1.18 | 4 |
| mutant | m42-networkx.generators.internet_as_graphs.py-66-10-compare | compare at networkx/generators/internet_as_graphs.py:66 | 6 | 280.74 | 0.16 | 1 |
| mutant | m42-networkx.generators.small.py-210-22-constant | constant at networkx/generators/small.py:210 | 1 | 292.71 | 0.04 | 1 |
| mutant | m42-networkx.algorithms.dag.py-765-17-constant | constant at networkx/algorithms/dag.py:765 | 2 | 141.30 | 0.81 | 2 |
| mutant | m42-networkx.algorithms.approximation.traveling_salesman.py-921-24-constant | constant at networkx/algorithms/approximation/traveling_sale | 2 | 23.68 | 9.03 | 2 |
| mutant | m42-networkx.utils.misc.py-429-12-return | return at networkx/utils/misc.py:429 | 1 | 308.87 | 0.22 | 1 |
| mutant | m42-networkx.algorithms.flow.boykovkolmogorov.py-226-45-compare | compare at networkx/algorithms/flow/boykovkolmogorov.py:226 | 58 | 44.06 | 0.02 | 1 |
| mutant | m42-networkx.algorithms.shortest_paths.unweighted.py-339-24-return | return at networkx/algorithms/shortest_paths/unweighted.py:3 | 34 | 14.54 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.smallworld.py-189-35-constant | constant at networkx/algorithms/smallworld.py:189 | 2 | 193.93 | 0.06 | 1 |
| mutant | m42-networkx.readwrite.graphml.py-1093-8-return | return at networkx/readwrite/graphml.py:1093 | 19 | 298.24 | 0.02 | 1 |
| mutant | m42-networkx.algorithms.approximation.traveling_salesman.py-762-19-compare | compare at networkx/algorithms/approximation/traveling_sales | 6 | 18.90 | 4.25 | 2 |
| mutant | m42-networkx.algorithms.approximation.traveling_salesman.py-1252-38-compare | compare at networkx/algorithms/approximation/traveling_sales | 2 | 14.86 | 0.21 | 2 |
| mutant | m42-networkx.algorithms.coloring.greedy_coloring.py-507-36-compare | compare at networkx/algorithms/coloring/greedy_coloring.py:5 | 1 | 34.97 | 0.03 | 1 |
| mutant | m42-networkx.algorithms.triads.py-212-22-arith | arith at networkx/algorithms/triads.py:212 | 5 | 196.11 | 0.15 | 1 |
| mutant | m42-networkx.algorithms.link_analysis.pagerank_alg.py-248-12-constant | constant at networkx/algorithms/link_analysis/pagerank_alg.p | 2 | 124.58 | 0.21 | 1 |
| mutant | m42-networkx.generators.geometric.py-493-15-compare | compare at networkx/generators/geometric.py:493 | 3 | 278.42 | 0.42 | 2 |
| mutant | m42-networkx.algorithms.centrality.current_flow_betweenness.py-261-26-arith | arith at networkx/algorithms/centrality/current_flow_between | 15 | 31.11 | 0.01 | 1 |
| mutant | m42-networkx.readwrite.graphml.py-1058-8-return | return at networkx/readwrite/graphml.py:1058 | 18 | 298.24 | 0.02 | 1 |
| mutant | m42-networkx.algorithms.shortest_paths.generic.py-436-13-compare | compare at networkx/algorithms/shortest_paths/generic.py:436 | 1 | 135.82 | 0.25 | 1 |
| mutant | m42-networkx.algorithms.distance_measures.py-915-7-compare | compare at networkx/algorithms/distance_measures.py:915 | 7 | 164.54 | 23.74 | 4 |
| mutant | m42-networkx.algorithms.centrality.betweenness.py-420-28-constant | constant at networkx/algorithms/centrality/betweenness.py:42 | 113 | 27.11 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.similarity.py-1164-7-compare | compare at networkx/algorithms/similarity.py:1164 | 30 | 190.83 | 1.18 | 4 |
| mutant | m42-networkx.algorithms.connectivity.edge_kcomponents.py-468-15-compare | compare at networkx/algorithms/connectivity/edge_kcomponents | 6 | 49.79 | 1.10 | 1 |
| mutant | m42-networkx.algorithms.dag.py-869-13-compare | compare at networkx/algorithms/dag.py:869 | 3 | 29.06 | 0.07 | 1 |
| mutant | m42-networkx.algorithms.similarity.py-2055-32-constant | constant at networkx/algorithms/similarity.py:2055 | 22 | 190.32 | 0.67 | 4 |
| mutant | m42-networkx.algorithms.graphical.py-168-45-constant | constant at networkx/algorithms/graphical.py:168 | 1 | 185.28 | 0.24 | 1 |
| mutant | m42-networkx.algorithms.shortest_paths.weighted.py-2448-17-compare | compare at networkx/algorithms/shortest_paths/weighted.py:24 | 28 | 14.48 | 0.02 | 1 |
| mutant | m42-networkx.algorithms.cluster.py-538-11-constant | constant at networkx/algorithms/cluster.py:538 | 2 | 138.14 | 0.32 | 1 |
| mutant | m42-networkx.linalg.spectrum.py-196-8-return | return at networkx/linalg/spectrum.py:196 | 1 | 295.65 | 0.08 | 1 |
| mutant | m42-networkx.algorithms.matching.py-245-24-constant | constant at networkx/algorithms/matching.py:245 | 33 | 27.93 | 0.03 | 1 |
| mutant | m42-networkx.algorithms.cycles.py-752-19-compare | compare at networkx/algorithms/cycles.py:752 | 7 | 138.98 | 0.50 | 3 |
| mutant | m42-networkx.generators.small.py-586-16-constant | constant at networkx/generators/small.py:586 | 7 | 9.99 | 0.04 | 1 |
| mutant | m42-networkx.algorithms.planar_drawing.py-221-15-boolop | boolop at networkx/algorithms/planar_drawing.py:221 | 8 | 188.99 | 0.01 | 1 |
| mutant | m42-networkx.generators.social.py-49-40-constant | constant at networkx/generators/social.py:49 | 1 | 35.27 | 48.04 | 26 |
| mutant | m42-networkx.algorithms.tree.coding.py-116-11-compare | compare at networkx/algorithms/tree/coding.py:116 | 2 | 205.34 | 0.09 | 1 |
| mutant | m42-networkx.algorithms.bipartite.matching.py-496-12-arith | arith at networkx/algorithms/bipartite/matching.py:496 | 5 | 29.01 | 0.03 | 1 |
| mutant | m42-networkx.algorithms.centrality.subgraph_alg.py-101-6-compare | compare at networkx/algorithms/centrality/subgraph_alg.py:10 | 1 | 34.46 | 0.01 | 1 |
| mutant | m42-networkx.algorithms.triads.py-484-16-return | return at networkx/algorithms/triads.py:484 | 3 | 196.04 | 0.08 | 1 |
| mutant | m42-networkx.readwrite.gexf.py-1103-11-compare | compare at networkx/readwrite/gexf.py:1103 | 5 | 296.74 | 0.02 | 1 |
| mutant | m42-networkx.algorithms.similarity.py-1179-12-return | return at networkx/algorithms/similarity.py:1179 | 1 | 191.16 | 1.51 | 4 |
| mutant | m42-networkx.algorithms.centrality.group.py-524-19-compare | compare at networkx/algorithms/centrality/group.py:524 | 3 | 33.28 | 0.43 | 1 |

Skipped (22): 54eca158c1ec10ea996fb4744b030bd47a42ff73: rebase: no_apply; 215470ae23a3f39b2c73da307260819921635921: rebase: no_apply; 5872457bf3f40503502e1ed74c8ab8d4e6ce7f55: rebase: no_apply; b7816afaf560542cb0892bbabfab1c343b6f9936: rebase: no_apply; e517554b89ab99608cfe9576bc40e46d8a0424b6: rebase: no_failure; 7ac7125167bdd1e3b39ce0f6778cf11ef64d01fc: rebase: no_apply; 845733e8af571c3e99b72e78acd1fc4d8482be59: rebase: no_apply; 1828adac8622f7ce43829d164cadf12136f37a0a: rebase: no_apply; d607f229f55a03e3fc7454f35911bdd0d5e5f5ef: rebase: no_apply; b9df494909c2fb8fdae1975832f0503d32df5522: rebase: no_apply; e3542acf18c53d07f80a5b4c17d50218d7259469: rebase: no_apply; 86e143dd83f350f7d6684bc81750573dfc309ea7: rebase: no_apply; 9e33b118bf40d4b9326366c5bb413d7e7f1c5027: rebase: no_apply; 772c8dcf1f615e239511277ee90241f3396c7648: rebase: no_apply; b3148fa6ec0e5989f714817040c94d8a6cf8fe33: rebase: no_apply; 32b2c75e5179dedae57eee82580bd6b408485d77: rebase: no_apply; 416c3e26da0567c9242aa415810dcffca27d625f: rebase: no_apply; 73cb92bbaed12828848f2609340442119e7e0fe8: rebase: no_apply; 0e3f58edd891bbef8f8013f147e8b679deba9970: rebase: no_apply; c279073cc33dab38777e701370210d0a7a98849a: rebase: no_apply; 8e0b38e1a11335f07db13a13a6a5955eecf33408: rebase: no_apply; 0db8227000872d7a9f6ce84c54ba1e5e99429122: rebase: no_apply
