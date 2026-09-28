"""Run every EDA section in order (A needs only the LRTS repo; B-H need data/interim tables)."""
from __future__ import annotations

import time

from stp.eda import a_baselines, b_costs, c_shape, d_failures, e_changes, f_signal, g_ttff, h_split

SECTIONS = {"A": a_baselines, "B": b_costs, "C": c_shape, "D": d_failures, "E": e_changes,
            "F": f_signal, "G": g_ttff, "H": h_split}  # D must precede G and H (writes failed_run_labels)


def main(only: str = "ABCDEFGH") -> None:
    for key in only:
        t0 = time.time()
        SECTIONS[key].run()
        print(f"[eda] section {key} done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    import sys

    main(sys.argv[1] if len(sys.argv) > 1 else "ABCDEFGH")
