# M2D research evaluation

Reference: Niizumi, Takeuchi, Ohishi, Harada and Kashino, “Exploring Pre-trained General-purpose Audio Representations for Heart Murmur Detection,” IEEE EMBC 2024, https://arxiv.org/abs/2404.17107.

Authors' code: https://github.com/nttcslab/m2d/tree/master/app/circor.

The unchanged portable runtime is fetched from revision `3d0c4de9447c404a8d3f9f37e04f53bc902e09b3`. The checkpoint is the paper's `m2d_vit_base-80x608p16x16-220930-mr7_enconly/checkpoint-300.pth`, from the authors' v0.1.0 release. Exact source and artifact SHA-256 values are in `m2d_murmur.py`.

Upstream uses NTT's **Software License Agreement for Evaluation**, including a non-commercial internal-evaluation restriction. It is not an MIT-licensed package. Read the actual terms at https://github.com/nttcslab/m2d/blob/master/LICENSE.pdf. The original license and extracted text are retained in the ignored upstream cache. Do not publish upstream code or trained derivatives or package them into a distributed app based on this experiment's authorization. An appropriate deployment license would need separate review.

This experiment downloads the unchanged runtime and public weights into ignored caches and uses them in a private research run. No license text or upstream implementation is embedded in the submitted notebook. The notebook contains our wrapper/trainer, public recording metadata and fingerprints only.
