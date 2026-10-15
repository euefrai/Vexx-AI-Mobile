"""Run the frozen, local-only document retrieval benchmark."""

import argparse
import json
import tempfile
from pathlib import Path

import research_quality_lab


ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = ROOT / "benchmarks" / "research_quality_v1.json"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="julia-quality-lab-") as work_dir:
        report = research_quality_lab.run_document_retrieval_benchmark(
            args.dataset, Path(work_dir) / "retrieval", k=args.k
        )
        report["checkpoint_benchmark"] = research_quality_lab.run_checkpoint_benchmark(
            args.dataset, Path(work_dir) / "checkpoints.sqlite3"
        )
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
