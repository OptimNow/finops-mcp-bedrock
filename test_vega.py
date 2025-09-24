from src.tools.visual import render_vega_lite_png

# Simple bar chart spec
spec = {
    "data": {"values": [
        {"month": "Jan", "cost": 120},
        {"month": "Feb", "cost": 135},
        {"month": "Mar", "cost": 128},
        {"month": "Apr", "cost": 142},
        {"month": "May", "cost": 150},
        {"month": "Jun", "cost": 147}
    ]},
    "mark": "bar",
    "encoding": {
        "x": {"field": "month", "type": "ordinal"},
        "y": {"field": "cost", "type": "quantitative"}
    }
}

# Run the renderer
path = render_vega_lite_png(spec)
print("✅ Chart saved to:", path)
