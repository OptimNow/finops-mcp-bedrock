# src/tools/visual.py
"""
Visual tools for chart generation and image creation.
"""
from typing import Optional, List, Dict, Any, Union
import altair as alt
import base64
import io
import json
import os

# ---------- Titan Image Gen (v2) ----------
def titan_image_generate(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    cfg_scale: float = 7.5,
    steps: int = 30,
    negative_prompt: Optional[str] = None
) -> str:
    """
    Generate an image with Amazon Titan Image Generator v2.
    Returns the local file path to the PNG.
    """
    import boto3
    from PIL import Image

    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
    model_id = "amazon.titan-image-generator-v2:0"
    br = boto3.client("bedrock-runtime", region_name=region)

    body = {
        "taskType": "TEXT_IMAGE",
        "textToImageParams": {
            "text": prompt,
            **({"negativeText": negative_prompt} if negative_prompt else {})
        },
        "imageGenerationConfig": {
            "width": width,
            "height": height,
            "cfgScale": cfg_scale,
            "steps": steps,
            "seed": 0
        }
    }

    resp = br.invoke_model(modelId=model_id, body=json.dumps(body))
    payload = json.loads(resp["body"].read())
    b64 = payload["images"][0]
    img_bytes = base64.b64decode(b64)
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")

    out_dir = "outputs"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "titan_image.png")
    img.save(out_path, format="PNG")
    return out_path


# ---------- Smart Chart Generator ----------
def create_chart(
    chart_type: str,
    data: List[Dict[str, Any]],
    x_field: str,
    y_field: str,
    title: str = "Chart",
    color_field: Optional[str] = None,
    x_title: Optional[str] = None,
    y_title: Optional[str] = None,
    color_scheme: Optional[Dict[str, str]] = None,
    width: int = 500,
    height: int = 300
) -> str:
    """
    Create a chart with simple parameters. The tool handles all Vega-Lite complexity.
    
    Args:
        chart_type: Type of chart - "bar", "line", "pie", "area"
        data: List of data points as dictionaries. 
              For time series, use ISO dates: [{"date": "2025-08-01", "cost": 100}, ...]
              For categories: [{"service": "EC2", "cost": 150}, ...]
              For multi-series: add a type field [{"date": "2025-08-01", "cost": 100, "type": "Actual"}, ...]
        x_field: Field name for X axis (e.g., "date", "service", "month")
        y_field: Field name for Y axis (e.g., "cost", "amount", "value")
        title: Chart title
        color_field: Optional field for color grouping (e.g., "type" for Actual vs Forecast)
        x_title: Optional custom X axis title
        y_title: Optional custom Y axis title  
        color_scheme: Optional color mapping like {"Actual": "blue", "Forecast": "orange"}
        width: Chart width in pixels (default 500)
        height: Chart height in pixels (default 300)
    
    Returns:
        Success message if chart created, error message otherwise.
    
    Examples:
        # Simple bar chart
        create_chart("bar", [{"service": "EC2", "cost": 150}], "service", "cost", "Costs by Service")
        
        # Line chart with time series
        create_chart("line", [{"date": "2025-08-01", "cost": 53}], "date", "cost", "Cost Trend")
        
        # Multi-series line (actual vs forecast)
        create_chart("line", 
                     [{"date": "2025-08-01", "cost": 53, "type": "Actual"},
                      {"date": "2025-11-01", "cost": 25, "type": "Forecast"}],
                     "date", "cost", "Actual vs Forecast",
                     color_field="type",
                     color_scheme={"Actual": "blue", "Forecast": "orange"})
    """
    import chainlit as cl
    import asyncio
    
    try:
        if not data:
            return "❌ Error: No data provided for chart"
        
        # Detect if x_field contains dates (ISO format)
        is_temporal = False
        sample_value = str(data[0].get(x_field, ""))
        if len(sample_value) >= 10 and sample_value[4] == "-" and sample_value[7] == "-":
            is_temporal = True
        
        # Build the encoding
        x_encoding = {
            "field": x_field,
            "type": "temporal" if is_temporal else "nominal",
            "title": x_title or x_field.replace("_", " ").title()
        }
        
        # Add proper axis formatting for temporal data
        if is_temporal:
            x_encoding["axis"] = {"format": "%b %Y"}
            # Sort by date
            x_encoding["sort"] = None  # Natural sort for temporal
        elif chart_type == "bar":
            # Sort bars by value descending
            x_encoding["sort"] = "-y"
        
        y_encoding = {
            "field": y_field,
            "type": "quantitative",
            "title": y_title or y_field.replace("_", " ").title(),
            "scale": {"zero": True}
        }
        
        encoding = {"x": x_encoding, "y": y_encoding}
        
        # Handle color/grouping
        if color_field:
            color_encoding = {
                "field": color_field,
                "type": "nominal",
                "title": color_field.replace("_", " ").title()
            }
            
            # Apply custom color scheme
            if color_scheme:
                domain = list(color_scheme.keys())
                range_colors = []
                for key in domain:
                    color = color_scheme[key].lower()
                    # Map color names to hex
                    color_map = {
                        "blue": "#1f77b4",
                        "orange": "#ff7f0e", 
                        "green": "#2ca02c",
                        "red": "#d62728",
                        "purple": "#9467bd",
                        "brown": "#8c564b",
                        "pink": "#e377c2",
                        "gray": "#7f7f7f",
                        "grey": "#7f7f7f"
                    }
                    range_colors.append(color_map.get(color, color))
                
                color_encoding["scale"] = {"domain": domain, "range": range_colors}
            
            encoding["color"] = color_encoding
            
            # Add dashed lines for forecasts in line charts
            if chart_type == "line" and color_scheme and "Forecast" in color_scheme:
                encoding["strokeDash"] = {
                    "field": color_field,
                    "type": "nominal",
                    "scale": {
                        "domain": list(color_scheme.keys()),
                        "range": [[1, 0] if k != "Forecast" else [5, 5] for k in color_scheme.keys()]
                    },
                    "legend": None
                }
        
        # Build mark based on chart type
        if chart_type == "bar":
            mark = {"type": "bar"}
        elif chart_type == "line":
            mark = {"type": "line", "point": True, "strokeWidth": 2}
        elif chart_type == "area":
            mark = {"type": "area", "line": True, "point": True}
        elif chart_type == "pie":
            mark = {"type": "arc", "innerRadius": 50}
            # Pie charts use theta instead of x/y
            encoding = {
                "theta": {"field": y_field, "type": "quantitative"},
                "color": {"field": x_field, "type": "nominal", "title": x_title or x_field}
            }
        else:
            return f"❌ Unknown chart type: {chart_type}. Use: bar, line, pie, area"
        
        # Build the spec
        spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "width": width,
            "height": height,
            "title": title,
            "data": {"values": data},
            "mark": mark,
            "encoding": encoding
        }
        
        # Create chart
        chart = alt.Chart.from_dict(spec)
        
        # Save
        out_dir = "outputs"
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "chart.png")
        chart.save(out_path, format="png")
        
        # Send to Chainlit
        async def send_image():
            image_element = cl.Image(
                path=out_path,
                name=title,
                display="inline"
            )
            await cl.Message(content="", elements=[image_element]).send()
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(send_image())
            else:
                asyncio.run(send_image())
        except RuntimeError:
            asyncio.run(send_image())
        
        return f"✅ {chart_type.title()} chart '{title}' created successfully."
        
    except Exception as e:
        return f"❌ Failed to create chart: {str(e)}"


# ---------- Keep old function for backward compatibility ----------
def render_vega_lite_png(spec: Union[str, dict], output_path: str = "outputs/chart.png") -> str:
    """
    Render a raw Vega-Lite JSON specification as PNG.
    Prefer using create_chart() for simpler usage.
    """
    import chainlit as cl
    import asyncio
    
    try:
        if isinstance(spec, str):
            spec = json.loads(spec)
        
        if "$schema" not in spec:
            spec["$schema"] = "https://vega.github.io/schema/vega-lite/v5.json"
        if "width" not in spec:
            spec["width"] = 400
        if "height" not in spec:
            spec["height"] = 300
        
        chart = alt.Chart.from_dict(spec)
        
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        chart.save(output_path, format="png")
        
        async def send_image():
            image_element = cl.Image(
                path=output_path,
                name="Chart",
                display="inline"
            )
            await cl.Message(content="", elements=[image_element]).send()
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(send_image())
            else:
                asyncio.run(send_image())
        except RuntimeError:
            asyncio.run(send_image())
        
        return "✅ Chart created successfully."
        
    except Exception as e:
        return f"❌ Failed to create chart: {str(e)}"
