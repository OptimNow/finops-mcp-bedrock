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
    Create a chart with simple parameters. The tool handles all complexity.
    
    Args:
        chart_type: Type of chart - "bar", "line", "pie", "area"
        data: List of data points as dictionaries.
        x_field: Field name for X axis
        y_field: Field name for Y axis
        title: Chart title
        color_field: Optional field for color grouping
        x_title: Optional custom X axis title
        y_title: Optional custom Y axis title
        color_scheme: Optional color mapping like {"Actual": "blue", "Forecast": "orange"}
        width: Chart width in pixels
        height: Chart height in pixels
    
    Returns:
        Success message if chart created, error message otherwise.
    """
    import chainlit as cl
    import asyncio
    from datetime import datetime
    
    try:
        if not data:
            return "Error: No data provided for chart"
        
        # Detect if x_field contains dates
        is_temporal = False
        sample_value = str(data[0].get(x_field, ""))
        if len(sample_value) >= 10 and sample_value[4:5] == "-" and sample_value[7:8] == "-":
            is_temporal = True
        
        # For temporal data, convert to month labels
        if is_temporal:
            data = sorted(data, key=lambda x: x[x_field])
            for item in data:
                date_str = item[x_field]
                try:
                    dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
                    item["_month_label"] = dt.strftime("%b %Y")
                    item["_sort_key"] = date_str[:10]
                except:
                    item["_month_label"] = date_str
                    item["_sort_key"] = date_str
            
            unique_months = []
            seen = set()
            for item in data:
                label = item["_month_label"]
                if label not in seen:
                    unique_months.append(label)
                    seen.add(label)
            
            x_field_display = "_month_label"
        else:
            x_field_display = x_field
            unique_months = None
        
        # Color mapping
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
        
        source = alt.Data(values=data)
        
        if chart_type == "pie":
            chart = alt.Chart(source).mark_arc(innerRadius=50).encode(
                theta=alt.Theta(field=y_field, type="quantitative"),
                color=alt.Color(
                    field=x_field_display,
                    type="nominal",
                    title=x_title or x_field.replace("_", " ").title()
                )
            ).properties(width=width, height=height, title=title)
        
        elif color_field and color_scheme:
            domain = list(color_scheme.keys())
            range_colors = [color_map.get(color_scheme[k].lower(), color_scheme[k]) for k in domain]
            
            x_enc = alt.X(
                field=x_field_display,
                type="nominal",
                title=x_title or "Date",
                sort=unique_months if unique_months else None,
                axis=alt.Axis(labelAngle=-45)
            )
            
            y_enc = alt.Y(
                field=y_field,
                type="quantitative",
                title=y_title or y_field.replace("_", " ").title(),
                scale=alt.Scale(zero=True)
            )
            
            color_enc = alt.Color(
                field=color_field,
                type="nominal",
                title=color_field.replace("_", " ").title(),
                scale=alt.Scale(domain=domain, range=range_colors)
            )
            
            if chart_type == "line":
                stroke_dash_range = [[1, 0] if k != "Forecast" else [5, 5] for k in domain]
                chart = alt.Chart(source).mark_line(point=True, strokeWidth=2).encode(
                    x=x_enc,
                    y=y_enc,
                    color=color_enc,
                    strokeDash=alt.StrokeDash(
                        field=color_field,
                        type="nominal",
                        scale=alt.Scale(domain=domain, range=stroke_dash_range),
                        legend=None
                    )
                ).properties(width=width, height=height, title=title)
            elif chart_type == "bar":
                chart = alt.Chart(source).mark_bar().encode(
                    x=x_enc,
                    y=y_enc,
                    color=color_enc,
                    xOffset=alt.XOffset(field=color_field, type="nominal")
                ).properties(width=width, height=height, title=title)
            elif chart_type == "area":
                chart = alt.Chart(source).mark_area(line=True, point=True, opacity=0.5).encode(
                    x=x_enc,
                    y=y_enc,
                    color=color_enc
                ).properties(width=width, height=height, title=title)
            else:
                return f"Unknown chart type: {chart_type}"
        
        else:
            x_enc = alt.X(
                field=x_field_display,
                type="nominal",
                title=x_title or x_field.replace("_", " ").title(),
                sort=unique_months if unique_months else ("-y" if chart_type == "bar" else None),
                axis=alt.Axis(labelAngle=-45) if is_temporal else alt.Axis()
            )
            
            y_enc = alt.Y(
                field=y_field,
                type="quantitative",
                title=y_title or y_field.replace("_", " ").title(),
                scale=alt.Scale(zero=True)
            )
            
            if chart_type == "bar":
                chart = alt.Chart(source).mark_bar().encode(
                    x=x_enc,
                    y=y_enc,
                    color=alt.Color(field=x_field_display, type="nominal", legend=None)
                )
            elif chart_type == "line":
                chart = alt.Chart(source).mark_line(point=True, strokeWidth=2).encode(
                    x=x_enc,
                    y=y_enc
                )
            elif chart_type == "area":
                chart = alt.Chart(source).mark_area(line=True, point=True).encode(
                    x=x_enc,
                    y=y_enc
                )
            else:
                return f"Unknown chart type: {chart_type}. Use: bar, line, pie, area"
            
            chart = chart.properties(width=width, height=height, title=title)
        
        out_dir = "outputs"
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "chart.png")
        chart.save(out_path, format="png")
        
        async def send_image():
            image_element = cl.Image(path=out_path, name=title, display="inline")
            await cl.Message(content="", elements=[image_element]).send()
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(send_image())
            else:
                asyncio.run(send_image())
        except RuntimeError:
            asyncio.run(send_image())
        
        return f"Chart '{title}' created successfully."
        
    except Exception as e:
        import traceback
        return f"Failed to create chart: {str(e)}\n{traceback.format_exc()}"


def render_vega_lite_png(spec: Union[str, dict], output_path: str = "outputs/chart.png") -> str:
    """Render a raw Vega-Lite JSON specification as PNG."""
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
            image_element = cl.Image(path=output_path, name="Chart", display="inline")
            await cl.Message(content="", elements=[image_element]).send()
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(send_image())
            else:
                asyncio.run(send_image())
        except RuntimeError:
            asyncio.run(send_image())
        
        return "Chart created successfully."
        
    except Exception as e:
        return f"Failed to create chart: {str(e)}"
