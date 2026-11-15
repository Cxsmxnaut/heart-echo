"""Download only public research assets and verify their pinned hashes."""
import argparse
import hashlib
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent
ASSETS = {
    'noise/speech.wav': ('https://download.pytorch.org/torchaudio/tutorial-assets/Lab41-SRI-VOiCES-src-sp0307-ch127535-sg0042-8000hz.wav', '17c4b9935a0d336478d97a60c3f737e80cdb4cc334c9b411050a8e32e2c2ec88'),
    'noise/babble.wav': ('https://download.pytorch.org/torchaudio/tutorial-assets/Lab41-SRI-VOiCES-rm1-babb-mc01-stu-clo-8000hz.wav', '68c7c30f242df769349ff75f4d8afbf228c5ad269c7399f696c550a7247e795e'),
}


def main():
    parser = argparse.ArgumentParser(); parser.parse_args()
    for name, (url, digest) in ASSETS.items():
        path = ROOT / 'cache' / name
        data = path.read_bytes() if path.exists() else urllib.request.urlopen(url, timeout=60).read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Checksum mismatch: ' + name)
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        print(name, digest)


if __name__ == '__main__': main()
