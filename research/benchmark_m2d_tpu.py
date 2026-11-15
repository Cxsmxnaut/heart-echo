"""Time M2D training steps on an available Kaggle TPU; synthetic inputs only.

No patient data, model selection, clinical score or trained checkpoint is used.
Existing PyTorch/XLA runtimes use SPMD across all available TPU chips, preserving
the logical batch32. A native TorchTPU runtime is measured on one device unless
distributed support has been explicitly configured. Never fall back to CPU.
"""
import importlib.util
import json
from pathlib import Path
import statistics
import time

import numpy as np
import torch
from torch.nn import functional as F

from m2d_murmur import M2DMurmur,sha


def main():
    torch.set_num_threads(2);torch.manual_seed(20261122)
    info=dict(benchmark_only=True,private_audio_uploaded=False,patient_data_used=False,
              batch=32,input_shape=[32,1,80,501],warmup_steps=8,timed_steps=40,
              accuracy_measured=False,trained_model_exported=False)
    if importlib.util.find_spec('torch_xla') is not None:
        import torch_xla
        import torch_xla.runtime as xr
        import torch_xla.core.xla_model as xm
        xr.use_spmd()
        if xr.device_type()!='TPU':
            raise RuntimeError('XLA did not find a TPU; refusing a CPU benchmark')
        import torch_xla.distributed.spmd as xs
        device=torch_xla.device() if hasattr(torch_xla,'device') else xm.xla_device()
        count=xr.global_runtime_device_count()
        mesh=xs.Mesh(np.arange(count),(count,),('data',))
        info.update(backend='PyTorch/XLA supplied by Kaggle',backend_version=torch_xla.__version__,
                    available_devices=count,used_devices=count,parallelism='SPMD; logical batch32')
        def synchronize():
            xm.mark_step();xm.wait_device_ops()
        def step(optimizer):
            xm.optimizer_step(optimizer,barrier=True)
        def mark(value):
            xs.mark_sharding(value,mesh,('data',)+(None,)*(value.ndim-1))
        amp_device='xla'
    elif importlib.util.find_spec('torch_tpu') is not None:
        import torch_tpu
        from torch_tpu import _loader
        _loader.load()
        if torch._C._get_privateuse1_backend_name()!='tpu':
            from torch_tpu._internal.utils import hardware
            details=dict(stage='native_hardware_discovery',
                usable_local_tpu_devices=hardware.get_tpu_device_count(),
                supported_tpu_pci_device_detected=hardware.get_tpu_spec() is not None,
                torch=torch.__version__)
            print(json.dumps(details),flush=True)
            Path('/kaggle/working/m2d-tpu-hardware.json').write_text(json.dumps(details,indent=2)+'\n')
            raise RuntimeError('TorchTPU could not discover an accessible local TPU device in this Kaggle environment')
        device=torch.device('tpu')
        count=torch.tpu.device_count()
        info.update(backend='TorchTPU',backend_version=getattr(torch_tpu,'__version__','unknown'),
                    available_devices=count,used_devices=1,parallelism='single TPU device')
        def synchronize():
            torch.tpu.synchronize()
        def step(optimizer):
            optimizer.step()
        def mark(value):
            pass
        amp_device='tpu'
    else:
        raise RuntimeError('Kaggle TPU image has no usable PyTorch TPU backend; no CPU fallback')
    info.update(torch=torch.__version__,device=str(device))
    print(json.dumps(dict(stage='backend_ready',**info)),flush=True)
    model=M2DMurmur(Path('/kaggle/temp/heart-m2d-speed/upstream')).to(device).train()
    # Explicit attention math works on both TPU backends without a CUDA flash kernel.
    for block in model.runtime.backbone.blocks:
        block.attn.fused_attn=False
    if amp_device=='tpu':
        model=torch.compile(model,backend='tpu')
    x=torch.randn(32,1,80,501).mul_(4.2).sub_(7.1).to(device)
    y=(torch.arange(32)%3).to(device)
    mark(x);mark(y)
    synchronize()
    results={}
    for name in ['sgd','adamw']:
        print(json.dumps(dict(stage='warming_and_compiling',optimizer=name)),flush=True)
        params=[p for p in model.parameters() if p.requires_grad]
        optimizer=(torch.optim.AdamW(params,lr=.00025,betas=(.9,.95),weight_decay=.0001,amsgrad=True)
                   if name=='adamw' else torch.optim.SGD(params,lr=.00025,momentum=.9))
        def iteration():
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(amp_device,dtype=torch.bfloat16):
                logits=model(x)
                loss=F.cross_entropy(logits,y)
            loss.backward();step(optimizer)
            return loss
        began=time.perf_counter()
        for _ in range(8):
            loss=iteration()
        synchronize()
        warmup=time.perf_counter()-began
        batches=[]
        for _ in range(4):
            synchronize();began=time.perf_counter()
            for _ in range(10):
                loss=iteration()
            synchronize();batches.append((time.perf_counter()-began)/10)
        value=float(loss.detach().cpu())
        if not np.isfinite(value):
            raise ValueError('Nonfinite benchmark loss')
        results[name]=dict(warmup_and_compilation_seconds=warmup,seconds_per_step_samples=batches,
            median_seconds_per_step=statistics.median(batches),synthetic_loss=value,
            estimated_562_training_batches_seconds=statistics.median(batches)*562,
            excludes=['public-audio download/preparation','selection evaluation','checkpoint writes'])
        print(json.dumps(dict(stage='timing_complete',optimizer=name,**results[name])),flush=True)
        Path('/kaggle/working/m2d-tpu-benchmark.json').write_text(
            json.dumps(dict(info,status='partial',results=results),indent=2)+'\n')
        del optimizer
    info.update(status='complete',results=results,source_sha256=sha(Path(__file__)),
        limits=['Synthetic fixed input throughput, not full training time or clinical accuracy.',
                'TPU bf16; current GPU run uses CUDA fp16 AMP. No direct accuracy equivalence claimed.',
                'First-use compilation and available chip count must be included when choosing a device.'])
    Path('/kaggle/working/m2d-tpu-benchmark.json').write_text(json.dumps(info,indent=2)+'\n')
    print(json.dumps(dict(complete=True,results=results)),flush=True)


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        report=dict(status='error',benchmark_only=True,error_type=type(error).__name__,error=str(error))
        Path('/kaggle/working/m2d-tpu-benchmark-error.json').write_text(json.dumps(report,indent=2)+'\n')
        raise
