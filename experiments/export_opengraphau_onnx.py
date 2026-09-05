"""Export OpenGraphAU stage-2 (MEFL) checkpoints to ONNX.

Not run in CI. Requires a scratch environment with torch, torchvision, timm, onnx,
onnxruntime and a clone of https://github.com/lingjivoo/OpenGraphAU (Apache-2.0).

    python experiments/export_opengraphau_onnx.py <repo_dir> <ckpt.pth> <arch> <out.onnx>

arch: resnet18 | resnet50 | swin_transformer_tiny. The checkpoint is loaded with
weights_only=True (no arbitrary pickle execution). The exported graph takes a 1x3x224x224
ImageNet-normalized float32 image and returns 41 sigmoid probabilities. The script verifies
the ONNX output against PyTorch on a random input and prints SHA-256 and size for the manifest.
"""

from __future__ import annotations

import hashlib
import sys
from functools import partial
from pathlib import Path


def main() -> None:
    repo, ckpt, arch, out = sys.argv[1:5]
    sys.path.insert(0, repo)
    import model.resnet as resnet_mod  # type: ignore[import-not-found]
    import numpy as np
    import onnxruntime as ort
    import torch

    for name in ("resnet18", "resnet50", "resnet101"):
        # upstream constructors try to load ImageNet weights from disk; we load the full
        # checkpoint right after, so skip that.
        setattr(resnet_mod, name, partial(getattr(resnet_mod, name), pretrained=False))
    from model.MEFL import MEFARG  # type: ignore[import-not-found]

    state = torch.load(ckpt, map_location="cpu", weights_only=True)["state_dict"]
    state = {k.removeprefix("module."): v for k, v in state.items()}
    net = MEFARG(num_main_classes=27, num_sub_classes=14, backbone=arch)
    result = net.load_state_dict(state, strict=True)
    assert not result.missing_keys and not result.unexpected_keys
    net.eval()

    x = torch.randn(1, 3, 224, 224)
    torch.onnx.export(
        net,
        x,
        out,
        input_names=["image"],
        output_names=["au_prob"],
        opset_version=17,
        dynamo=False,
        dynamic_axes={"image": {0: "batch"}, "au_prob": {0: "batch"}},
    )
    with torch.no_grad():
        ref = net(x).numpy()
    sess = ort.InferenceSession(out, providers=["CPUExecutionProvider"])
    got = sess.run(None, {"image": x.numpy()})[0]
    print("max |onnx - torch| =", float(np.abs(got - ref).max()))
    data = Path(out).read_bytes()
    print("sha256", hashlib.sha256(data).hexdigest(), "size_bytes", len(data))


if __name__ == "__main__":
    main()
