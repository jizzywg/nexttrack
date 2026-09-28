import json
from pathlib import Path

from django.core.management.base import BaseCommand

from recommender.services import build_evaluation


def _fmt(stat, digits=3):
    if not stat:
        return "  n/a  "
    lo, hi = stat["ci"]
    return f"{stat['mean']:.{digits}f} [{lo:.{digits}f}, {hi:.{digits}f}]"


class Command(BaseCommand):
    help = (
        "Run the offline evaluation (accuracy vs Last.fm similar-track ground truth when available, plus "
        "coverage, diversity, novelty and latency) for the full model, ablations and baselines."
    )

    def add_arguments(self, parser):
        parser.add_argument("--k", type=int, default=10, help="List length (default 10).")
        parser.add_argument("--sample", type=int, default=100, help="Number of seed tracks to evaluate (default 100).")
        parser.add_argument("--rng-seed", type=int, default=42, help="Random seed for reproducibility.")
        parser.add_argument("--json", dest="json_path", help="Also write the full report to this JSON file.")

    def handle(self, *args, **options):
        report = build_evaluation(k=options["k"], sample=options["sample"], rng_seed=options["rng_seed"])
        gt = report["ground_truth"]
        self.stdout.write(
            f"Catalogue: {report['catalogue_size']} tracks | seeds evaluated: {report['sample']} | k = {report['k']}"
        )
        self.stdout.write(
            f"Ground truth: {gt['source'] or 'none'} ({gt['pairs']} pairs over {gt['seeds_with_reference']} seeds)\n"
        )
        header = f"{'Strategy':<52} {'nDCG@k':<22} {'Precision@k':<22} {'Hit@k':<22} {'Coverage':<9} {'Diversity':<22} {'ms':>6}"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))
        for row in report["strategies"]:
            self.stdout.write(
                f"{row['name']:<52} {_fmt(row['ndcg']):<22} {_fmt(row['precision']):<22} {_fmt(row['hit_rate']):<22} "
                f"{row['coverage']:<9.3f} {_fmt(row['diversity']):<22} {row['latency_ms']:>6.1f}"
            )
        for note in report["notes"]:
            self.stdout.write(self.style.WARNING(f"\nNote: {note}"))
        if options["json_path"]:
            Path(options["json_path"]).write_text(json.dumps(report, indent=2), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Wrote {options['json_path']}"))
