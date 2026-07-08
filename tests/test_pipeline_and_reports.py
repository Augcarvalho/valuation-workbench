from pathlib import Path

from src.pipeline.build_dataset import build_dataset
from src.reporting.board_pack import generate_board_pack


def test_public_demo_builds_monitoring_dataset(tmp_path):
    output = tmp_path / "monitoring_dataset.csv"
    dataset_path, source_log_path = build_dataset("public-demo", output_path=output)

    assert dataset_path.exists()
    assert source_log_path.exists()
    assert dataset_path.stat().st_size > 0


def test_board_pack_generates_html_and_pdf(tmp_path):
    outputs = generate_board_pack(demo=True, output_dir=Path(tmp_path), output_format="both")

    assert outputs["html"].exists()
    assert outputs["pdf"].exists()
    assert outputs["html"].stat().st_size > 1000
    assert outputs["pdf"].stat().st_size > 1000
