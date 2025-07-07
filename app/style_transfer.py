# style_transfer.py

import torch
from torchvision import transforms
from PIL import Image
import os
from app.transformer_net import TransformerNet  # Or your model definition

# Where your style models (.pth) live
STYLE_MODELS = {
    "mosaic": "./app/model/mosaic.pth",
    "candy": "./app/model/candy.pth",
    "udnie": "./app/model/udnie.pth",
    # Add more style .pth files here!
}

def run_style_transfer(input_image_path, output_image_path, style_name):
    if style_name not in STYLE_MODELS:
        raise ValueError(f"Style '{style_name}' not found!")

    # Load model for selected style
    model_path = STYLE_MODELS[style_name]
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model file not found: {model_path}")

    model = TransformerNet()
    checkpoint = torch.load(model_path)
    # Remove incompatible keys
    cleaned_state_dict = {
        k: v for k, v in checkpoint.items()
        if "running_mean" not in k and "running_var" not in k
    }
    # # Check if it's a checkpoint dict or raw state dict
    # if isinstance(checkpoint, dict) and 'state_dict' in checkpoint:
    #     state_dict = checkpoint['state_dict']
    # else:
    #     state_dict = checkpoint

    model.load_state_dict(cleaned_state_dict)
    model.eval()



    # Load and preprocess input image
    image = Image.open(input_image_path).convert("RGB")
    transform = transforms.Compose([
        transforms.Resize(512),
        transforms.ToTensor(),
        transforms.Lambda(lambda x: x.mul(255))
    ])
    tensor = transform(image).unsqueeze(0)

    # Run inference
    with torch.no_grad():
        output = model(tensor).cpu()

    # Postprocess & save output image
    output = output.squeeze(0).clamp(0, 255).permute(1, 2, 0).byte().numpy()
    output_image = Image.fromarray(output)
    output_image.save(output_image_path)

    return True
