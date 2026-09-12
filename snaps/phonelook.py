"""Give any image the 2015 phone-snapshot look (no caption bar).

    python3 phonelook.py in1.jpg in2.png ...   -> in1-phone.jpg, in2-phone.jpg
Use it on character reference images so the references themselves carry
the soft, noisy, compressed look instead of a clean AI-portrait look.
"""
import sys, json
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).parent))
from snapify import apply_look
LOOK = {'softness': 0.7, 'blur': 0.8, 'noise_luma': 6.0, 'noise_chroma': 3.0,
        'jpeg_quality': 62, 'black_lift': 8, 'saturation': 0.9, 'vignette': 0.12}
for i, src in enumerate(sys.argv[1:]):
    p = Path(src)
    im = Image.open(p).convert('RGB')
    if max(im.size) > 1600:  # old phones were not 4K
        im.thumbnail((1600, 1600), Image.BICUBIC)
    out = apply_look(im, LOOK, seed=i)
    dst = p.with_name(p.stem + '-phone.jpg')
    out.save(dst, 'JPEG', quality=80)
    print(dst, out.size)
