# Credits and contribution disclosure

[Overview](README.md) · [Judge guide](docs/JUDGE_GUIDE.md) · [Results](docs/RESULTS.md)

## Project contribution and AI assistance

Heart Echo combines the project's own trained heart-sound models, native SwiftUI recording/result/history flow, independent BPM and murmur paths, and a Mac-hosted care service with validated public-directory cards. `ChestBPM/` is the original prototype from which the current app was developed; it is preserved rather than presented as unrelated third-party work. [PORTING.json](HeartEcho/PORTING.json) records source origins and hashes. The team states both prototypes were developed during the event.

**OpenAI ChatGPT/Codex** assisted with planning, source implementation, debugging, research, training/evaluation tooling, tests and documentation. This is AI-assisted work. **Google Gemini** generates runtime care conversation; it was not trained by this project. **Google Gemma via Unsloth/llama.cpp** supports the earlier local care route and a separately documented synthetic-data LoRA pilot. Those language models do not analyze recordings. [OpenAI Codex](https://openai.com/codex/) · [Gemini](https://ai.google.dev/gemini-api/docs) · [Gemma](https://ai.google.dev/gemma)

The audio model weights bundled with the app were trained by the project; the project does not claim ownership of third-party datasets, pretrained language/audio encoders, libraries, or design guidance. Research alternatives are distinguished from the shipping models.

## Data used by the shipped audio pipeline

| Source | Use and attribution |
| --- | --- |
| [CirCor DigiScope 1.0.3](https://doi.org/10.13026/tshs-mw03), Oliveira et al. | Public heart-sound recordings, sound-state annotations and murmur labels for timing/murmur training and evaluation. Open Data Commons Attribution License 1.0. [Original paper](https://doi.org/10.1109/JBHI.2021.3137048). |
| [VOiCES](https://iqtlabs.github.io/voices/), IARPA/Lab41/SRI | Two speech/babble examples used for noise augmentation, obtained through the [PyTorch audio augmentation tutorial](https://docs.pytorch.org/audio/main/tutorials/audio_data_augmentation_tutorial.html). CC BY 4.0; the same noise clips recur across some train/test mixtures, so this is not unseen-noise validation. |

Contains information from the **CirCor DigiScope Phonocardiogram Dataset**, available under the [ODC Attribution License](https://opendatacommons.org/licenses/by/1-0/). Bundled examples are shortened/PCM16-encoded as documented in [sample sources and checksums](HeartEcho/Resources/MurmurSamples/SOURCES.json); the [full license](HeartEcho/Resources/MurmurSamples/LICENSE.txt) is retained. Source annotations belong to public dataset participants, not the person running the demo.

Detailed model/training provenance and source hashes: [PROVENANCE.txt](ChestBPM/ML/PROVENANCE.txt), [phase report](ChestBPM/ML/murmur-phase-report.json), and [model decision](research/murmur-model-decision.md).

## Research and evaluation sources

These sources support separate experiments or references; listing them does not mean their weights or performance are shipped in the app.

| Source | Scope |
| --- | --- |
| [PhysioNet/CinC Challenge 2016](https://physionet.org/content/challenge-2016/1.0.0/) | Public normal/abnormal research; [source inventory](research/results/physionet2016-source.json). It is not an AFib dataset. |
| [BMD-HS](https://github.com/sani002/BMD-HS-Dataset) and its authors | Public multi-site valve research; pinned source and license hashes in [bmd-source.json](research/results/bmd-source.json). No valve-disease classifier is added to the app. |
| [EPHNOGRAM](https://doi.org/10.13026/tjtq-5911), Kazemnejad, Gordany and Sameni | Separate public ECG/PCG comparison study, ODC Attribution 1.0. [Paper](https://doi.org/10.1088/1361-6579/ad43af). Automated ECG references are not clinician-reviewed ground truth. |
| [PASCAL heart-sound challenge](http://www.peterjbentley.com/heartchallenge/) | External historical sound-classifier experiments; dataset/source independence limits remain in their reports. Not evidence of live-phone accuracy. |
| [PANNs](https://github.com/qiuqiangkong/audioset_tagging_cnn), Qiuqiang Kong et al.; [pretrained weights](https://zenodo.org/records/3987831) | AudioSet-pretrained CNN6 research alternatives. Upstream code MIT; weight source declares CC BY 4.0. [Retained code license](research/third_party/PANNs-LICENSE.MIT). Downloaded weights are excluded. |
| [TorchVision](https://github.com/pytorch/vision) | Pretrained ResNet18 research alternative. [Retained BSD license](research/third_party/TorchVision-LICENSE.BSD). |
| [Niizumi et al., EMBC 2024](https://arxiv.org/abs/2404.17107); [M2D authors' implementation](https://github.com/nttcslab/m2d/tree/master/app/circor) | Separate M2D comparison. NTT's evaluation license restricts redistribution/use. [Notice](research/third_party/M2D-NOTICE.md). Upstream implementation and checkpoints are not distributed here or bundled as the app detector. |
| [McDonald, Gales and Agarwal, 2024](https://doi.org/10.1371/journal.pdig.0000436) | Research motivation for explicit timing supervision; no paper code or weights copied into the shipped phase model. |
| [Springer/Schmidt segmentation reference](https://physionet.org/content/hss/1.0/) | Research reference; no GPL implementation or trained weights copied into the shipped model. |
| [LU-Net authors](https://github.com/ShamsNafisaAli/LU-Net-Heart-Sound-Denoising-) | Evaluated denoising alternative; not enabled/bundled. Pretrained redistribution permission was not established. |

Private-derived phone-style research is disclosed in the model decision. No private captures, profiles, derivative audio or research weights from those experiments are included in the submission package or adopted into the shipped detector.

## Care directories and language-model tooling

- [CMS NPPES](https://npiregistry.cms.hhs.gov/api-page): provider identity, taxonomy and practice address; not proof of coverage or quality.
- [HRSA health centers](https://data.hrsa.gov/topics/health-centers/): public service-site listings; services, appointments and sliding-fee eligibility require confirmation.
- [CMS National Provider Directory](https://directory.cms.gov/developers) and [The Health Plan public directory](https://www.healthplan.org/patient-access-api): narrowly scoped plan/network research; no nationwide coverage guarantee.
- [Google Gemini API](https://ai.google.dev/gemini-api/docs), [Google Gemma](https://ai.google.dev/gemma), [Unsloth](https://github.com/unslothai/unsloth), [llama.cpp](https://github.com/ggml-org/llama.cpp), [PEFT](https://github.com/huggingface/peft), [Transformers](https://github.com/huggingface/transformers), [bitsandbytes](https://github.com/bitsandbytes-foundation/bitsandbytes) and [TRL](https://github.com/huggingface/trl): runtime or historical language-model training/export tooling. Pins, revisions, licenses and evaluation boundaries are in [care provenance](care-assistant/docs/provenance.md) and [the fine-tuning record](care-assistant/finetuning/README.md). Downloaded language weights/adapters are not included.
- [Model Context Protocol SDK](https://github.com/modelcontextprotocol/typescript-sdk), [Express](https://expressjs.com/), [Zod](https://zod.dev/), [Playwright](https://playwright.dev/) and [Supertest](https://github.com/ladjs/supertest): care-service implementation and checks. Exact versions are in [package-lock.json](care-assistant/package-lock.json).

## App, research libraries and design

[Apple SDKs](https://developer.apple.com/documentation/) provide SwiftUI, AVFoundation, Core ML, HealthKit, WatchConnectivity and SF Symbols for native UI, audio, inference and optional Watch comparison. Python research uses [PyTorch](https://pytorch.org/), [NumPy](https://numpy.org/), [SciPy](https://scipy.org/), [scikit-learn](https://scikit-learn.org/), [librosa](https://librosa.org/), [coremltools](https://github.com/apple/coremltools) and [WFDB](https://github.com/MIT-LCP/wfdb-python), as specified in the component requirements files.

The result/chat design pass adapted **[Unslop](https://github.com/heydamir/unslop)** by **[Damir Sokolovsky](https://github.com/heydamir)**, licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), to native SwiftUI. [Design history](HeartEcho/Docs/DesignPreviewHistory.md) preserves that attribution.

Dataset and dependency licenses remain source-specific; this repository does not claim that all components share a single license. Reading the repository does not grant redistribution rights to excluded research artifacts.
