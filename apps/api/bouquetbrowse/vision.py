import io
from functools import lru_cache

from PIL import Image

from .config import get_settings
from .providers import CapabilityError

MODEL = "google/siglip2-base-patch16-224"


@lru_cache(maxsize=1)
def load_encoder():
    s = get_settings()
    if not s.siglip_revision or s.image_embedding_provider != "siglip":
        raise CapabilityError(
            "Enable siglip, install the vision extra and pin SIGLIP_REVISION before image inference.",
            "vision_not_configured",
        )
    try:
        import torch
        from transformers import AutoModel, AutoProcessor
    except ImportError as exc:
        raise CapabilityError(
            "Install the optional vision dependencies in the worker.", "vision_dependencies_missing"
        ) from exc
    torch.set_num_threads(1)
    model = AutoModel.from_pretrained(
        MODEL, revision=s.siglip_revision, trust_remote_code=False, use_safetensors=True
    ).eval()
    processor = AutoProcessor.from_pretrained(MODEL, revision=s.siglip_revision, trust_remote_code=False)
    return model, processor


def image_embedding(content):
    model, processor = load_encoder()
    import torch

    with Image.open(io.BytesIO(content)) as source:
        inputs = processor(images=source.convert("RGB"), return_tensors="pt")
    with torch.inference_mode():
        features = model.get_image_features(**inputs)
        if not torch.is_tensor(features):
            features = features.pooler_output
        features = features / features.norm(dim=-1, keepdim=True).clamp(min=1e-12)
    vector = features[0].cpu().tolist()
    if len(vector) != 768:
        raise CapabilityError("The pinned vision model has an unexpected dimension.", "vision_contract_error")
    return vector, f"{MODEL}@{get_settings().siglip_revision}"
