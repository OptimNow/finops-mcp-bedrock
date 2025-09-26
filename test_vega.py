import shutil
from pathlib import Path

from src.tools.visual import render_vega_lite_png


SPEC = {
    "data": {
        "values": [
            {"month": "Jan", "cost": 120},
            {"month": "Feb", "cost": 135},
            {"month": "Mar", "cost": 128},
            {"month": "Apr", "cost": 142},
            {"month": "May", "cost": 150},
            {"month": "Jun", "cost": 147},
        ]
    },
    "mark": "bar",
    "encoding": {
        "x": {"field": "month", "type": "ordinal"},
        "y": {"field": "cost", "type": "quantitative"},
    },
}


def test_render_vega_lite_png_creates_outputs_directory_and_file():
    outputs_dir = Path("outputs")
    shutil.rmtree(outputs_dir, ignore_errors=True)

    result_path = Path(render_vega_lite_png(SPEC))

    assert outputs_dir.is_dir(), "The outputs directory should be created."
    assert result_path.is_file(), "The PNG file should be created at the expected location."

    # Cleanup after test to avoid side effects on subsequent runs
    if outputs_dir.exists():
        shutil.rmtree(outputs_dir)
