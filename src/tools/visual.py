# src/tools/visual.py
from typing import Optional, Dict, Any
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
def render_vega_lite_png(spec: Dict[str, Any], width: Optional[int] = None, height: Optional[int] = None) -> str:
    """
    Render a Vega-Lite spec (dict) to a PNG file and return the file path.
    """
    if width:
        spec.setdefault("width", width)
    if height:
        spec.setdefault("height", height)

    png_bytes = vlc.vegalite_to_png(spec=spec)
    out_dir = "outputs"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "chart.png")
    with open(out_path, "wb") as f:
        f.write(png_bytes)
    return out_path
