# src/tools/visual.py
from typing import Union
from typing import Optional, Dict, Any
import altair as alt
import base64, io, json, os
from PIL import Image
import vl_convert as vlc
import boto3

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
    # Titan v2 returns base64 images array
    b64 = payload["images"][0]
    img_bytes = base64.b64decode(b64)
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")

    out_dir = "outputs"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "titan_image.png")
    img.save(out_path, format="PNG")
    return out_path

# ---------- Vega-Lite rendering ----------
import json
import altair as alt
import os

def render_vega_lite_png(spec: Union[str, dict], output_path: str = "outputs/chart.png") -> str:
    import altair as alt
    import json

    # Accept string or dict
    if isinstance(spec, str):
        spec = json.loads(spec)

    # Force mode to vega-lite
    if "$schema" in spec:
        spec.pop("$schema", None)

    chart = alt.Chart.from_dict(spec)
    chart.save(output_path, format="png")
    return output_path


