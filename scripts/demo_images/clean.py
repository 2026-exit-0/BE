import os, sys, re, json, csv, shutil
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
from scipy.ndimage import laplace

def _keep_brightness(src, out):
    a = np.asarray(src.convert("L"), float).mean()
    b = np.asarray(out.convert("L"), float).mean()
    if b < 1: return out
    return ImageEnhance.Brightness(out).enhance(min(1.6, a / b))

# 보정은 FE 필터에서 전담 → 폴백 이미지는 정제만(보정 X). 이중보정 방지.
ENHANCE = False

def enhance(im):
    """세게 보정: 선명도 + 국소대비(모공/주름) 강조, 밝기 유지(어두워지지 않음)."""
    o = im.filter(ImageFilter.UnsharpMask(radius=2, percent=180, threshold=1))
    o = o.filter(ImageFilter.UnsharpMask(radius=10, percent=80, threshold=0))
    o = _keep_brightness(im, o)
    return ImageEnhance.Color(o).enhance(1.05)

Z1 = sys.argv[1]   # z1b (recovered korean)
Z2 = sys.argv[2]   # z2/scans_rows/scan_image
OUT = sys.argv[3]  # outputs dir
K = 4              # keep up to K per group
HAMMING_MIN = 10   # dHash distance to count as distinct
BLUR_FLOOR = 8.0   # ESP32-CAM is inherently soft; only truly degenerate below ~8

PART_FIX = {"CNIN":"CHIN"}
AGE_ASCII = {"20대":"20s","30대":"30s","40대":"40s","50대":"50s","60대+":"60plus","기타":"na"}

def meta_z1(path):
    parts = path.split(os.sep); fn = os.path.basename(path)
    grp = next((p for p in parts if "대" in p), "")
    m = re.search(r"(\d0)\s*대", grp)
    ageband = ("60대+" if m and int(m.group(1))>=60 else (m.group(1)+"대" if m else "기타"))
    gender = "F" if "여" in grp else ("M" if "남" in grp else None)
    part = next((t for t in ("FOREHEAD","NOSE","CHIN","L_CHEEK","R_CHEEK") if t in fn.upper()), None)
    light = "uv" if "_uv" in fn.lower() else ("white" if "_white" in fn.lower() else None)
    return ageband, gender, part, light

def meta_z2(path):
    parts = path.split(os.sep)
    mem = next((p for p in parts if re.match(r"M\d+_\d+_(WOMAN|MAN|FEMALE|MALE)", p, re.I)), "")
    mm = re.match(r"M\d+_(\d+)_(\w+)", mem)
    age = int(mm.group(1)) if mm else None
    g = (mm.group(2).upper() if mm else "")
    gender = "F" if g in ("WOMAN","FEMALE") else ("M" if g in ("MAN","MALE") else None)
    # 03 = bogus age -> unknown
    ageband = "60대+" if (age and age>=60) else (f"{(age//10)*10}대" if (age and age>=10) else "기타")
    light = "uv" if any(p.upper()=="UV" for p in parts) else ("white" if any(p.upper() in ("WHITE_LED","WHITE") for p in parts) else None)
    part = None
    for p in parts[::-1]:
        u = p.upper(); u = PART_FIX.get(u,u)
        if u in ("FOREHEAD","NOSE","CHIN","L_CHEEK","R_CHEEK"): part=u; break
    return ageband, gender, part, light

def dhash(im, h=8):
    g = np.asarray(im.convert("L").resize((h+1,h), Image.LANCZOS), dtype=np.int16)
    bits = g[:,1:] > g[:,:-1]
    v = 0
    for b in bits.flatten(): v = (v<<1)|int(b)
    return v

def focus(im):
    g = np.asarray(im.convert("L").resize((256,256)), dtype=np.float64)
    return float(laplace(g).var())

def ham(a,b): return bin(a^b).count("1")

rows=[]
for root, metafn in ((Z1, meta_z1),(Z2, meta_z2)):
    for dp,_,files in os.walk(root):
        for f in files:
            if not f.lower().endswith((".jpg",".jpeg",".png")): continue
            full=os.path.join(dp,f)
            ab,ge,pa,li = metafn(full)
            if not (pa and li and ge): continue
            try:
                im=Image.open(full); im.load()
                rows.append(dict(path=full, ageband=ab, gender=ge, part=pa, light=li,
                                 focus=focus(im), dhash=dhash(im)))
            except Exception as e:
                print("skip", full, e)

print("usable images:", len(rows))

# group & select
from collections import defaultdict
groups=defaultdict(list)
for r in rows: groups[(r["ageband"],r["gender"],r["part"],r["light"])].append(r)

os.makedirs(OUT, exist_ok=True)
imgdir=os.path.join(OUT,"demo_images"); os.makedirs(imgdir, exist_ok=True)
mapping=[]; report=[]
for key, items in sorted(groups.items()):
    ab,ge,pa,li=key
    items.sort(key=lambda r:-r["focus"])
    chosen=[]
    for r in items:
        if len(chosen)>=K: break
        if any(ham(r["dhash"],c["dhash"])<HAMMING_MIN for c in chosen):
            r["_why"]="dup"; continue
        chosen.append(r); r["_why"]="chosen"
    for i,r in enumerate(chosen,1):
        ascii_ab=AGE_ASCII.get(ab,"na")
        newname=f"{ascii_ab}_{ge}_{pa}_{li}_{i}.jpg"
        _im=Image.open(r["path"]).convert("RGB")
        (enhance(_im) if ENHANCE else _im).save(os.path.join(imgdir,newname), quality=92)
        blurry = r["focus"]<BLUR_FLOOR
        mapping.append(dict(age_band=ab, gender=ge, part=pa, light=li,
                            file=newname, focus=round(r["focus"],1), low_quality=blurry))
    report.append(dict(group=f"{ab}/{ge}/{pa}/{li}", total=len(items),
                       chosen=len(chosen), best_focus=round(items[0]['focus'],1)))

with open(os.path.join(OUT,"demo_image_map.json"),"w") as fp:
    json.dump(mapping, fp, ensure_ascii=False, indent=2)
with open(os.path.join(OUT,"clean_report.csv"),"w",newline="") as fp:
    w=csv.DictWriter(fp, fieldnames=["group","total","chosen","best_focus"]); w.writeheader(); w.writerows(report)

print("\n=== per-group (total -> chosen, best focus) ===")
for r in report: print(f"  {r['group']:<28} {r['total']:>3} -> {r['chosen']}  (best {r['best_focus']})")
print(f"\nchosen files: {len(mapping)}  | groups: {len(report)}")
low=[m for m in mapping if m['low_quality']]
if low: print("LOW-QUALITY (best available still blurry):", len(low), [m['file'] for m in low])
