from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.config import DEFAULT_PROCESSED_DATASET, DEFAULT_SOURCE_LOG, PROCESSED_DIR
from src.ingestion.capiq_loader import load_capiq_exports
from src.ingestion.public_demo_loader import load_public_demo
from src.modeling.metrics import prepare_monitoring_dataset
from src.utils import ensure_dir, write_csv


def build_dataset(
    source: str,
    input_path: str | Path | None = None,
    output_path: str | Path = DEFAULT_PROCESSED_DATASET,
    allow_public_output: bool = False,
) -> tuple[Path, Path]:
    if source == "public-demo":
        inputs = load_public_demo()
    elif source == "capiq":
        if input_path is None:
            raise ValueError("--input is required when --source capiq")
        # Licensed-data safeguard: Capital IQ output must stay in data_private/.
        resolved = Path(output_path).resolve()
        if "data_private" not in resolved.parts and not allow_public_output:
            raise ValueError(
                f"Refusing to write Capital IQ data to a public path: {resolved}. "
                "Point --output inside data_private/ or pass --allow-public-output "
                "if you are absolutely sure."
            )
        inputs = load_capiq_exports(input_path)
    else:
        raise ValueError("source must be 'public-demo' or 'capiq'")

    dataset = prepare_monitoring_dataset(inputs)
    output = Path(output_path)
    ensure_dir(output.parent)
    write_csv(dataset, output)

    source_log = inputs.get("source_log", pd.DataFrame())
    source_log_path = DEFAULT_SOURCE_LOG if output == DEFAULT_PROCESSED_DATASET else output.parent / "source_log.csv"
    if not source_log.empty:
        write_csv(source_log, source_log_path)
    else:
        write_csv(pd.DataFrame(), source_log_path)

    return output, source_log_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the normalized PE monitoring dataset.")
    parser.add_argument("--source", choices=["public-demo", "capiq"], required=True)
    parser.add_argument("--input", default=None, help="Input folder for Capital IQ exports.")
    parser.add_argument("--output", default=str(DEFAULT_PROCESSED_DATASET))
    parser.add_argument("--allow-public-output", action="store_true",
                        help="Override the safeguard that blocks writing Capital IQ "
                             "data outside data_private/.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_dir(PROCESSED_DIR)
    output, source_log = build_dataset(args.source, args.input, args.output,
                                       allow_public_output=args.allow_public_output)
    print(f"Monitoring dataset written to {output}")
    print(f"Source log written to {source_log}")


if __name__ == "__main__":
    main()
