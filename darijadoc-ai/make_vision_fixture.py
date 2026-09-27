"""Generate synthetic ordonnance photos for vision testing.

Four fixtures:
  prescription_fixture.png  clear French ordonnance, 4 numbered lines
  prescription_arabic.png   Arabic-script page (needs an Arabic-capable font)
  prescription_blurry.png   deliberately blurred, to test the unreadable path
  prescription_partial.png  bottom cropped, to test per-line confidence

Run: .venv/bin/python make_vision_fixture.py
"""
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter


def resolve_font(prefer_arabic=False):
    """Find a real font file via fontconfig.

    Never hardcode a path. Font packages differ per machine, and a font without
    the needed glyphs silently produces a fixture that looks fine but contains
    unreadable text. Liberation, for example, has ZERO Arabic glyphs, so Arabic
    labels render as empty boxes and the model correctly calls the page
    unreadable -- which is indistinguishable from a model failure.
    """
    if prefer_arabic:
        out = subprocess.run(["fc-list", ":lang=ar", "file", "family"],
                             capture_output=True, text=True).stdout
        for line in out.splitlines():
            if ":" not in line:
                continue
            path, fam = line.split(":", 1)
            path, fam = path.strip(), fam.strip().lower()
            if "mono" not in fam and Path(path).exists():
                return path
    out = subprocess.run(["fc-match", "-f", "%{file}", "monospace"],
                         capture_output=True, text=True).stdout.strip()
    if not out or not Path(out).exists():
        raise RuntimeError("no usable font; install fonts-dejavu-core or fonts-freefont-ttf")
    return out


LATIN_FONT = resolve_font()
ARABIC_FONT = resolve_font(prefer_arabic=True)

FR = [
    ("Dr. Amina Benali", 22, True),
    ("Medecin Generaliste - Casablanca", 15, False),
    ("", 10, False),
    ("Date: 12/03/2026        Patient: Y. El Amrani", 16, False),
    ("", 10, False),
    ("Rp/", 20, True),
    ("", 10, False),
    ("1. Doliprane 1000 mg      1 comprime", 18, False),
    ("   1 x 3 / jour  pendant 5 jours", 16, False),
    ("   Si douleur", 16, False),
    ("", 10, False),
    ("2. Toplexil sirop 125 ml", 18, False),
    ("   1 c. a soupe x 2 / jour  pendant 7 jours", 16, False),
    ("", 10, False),
    ("3. Smecta 3 g            1 sachet", 18, False),
    ("   1 x 3 / jour  apres chaque repas", 16, False),
    ("", 10, False),
    ("4. Aer                   1 bouffee", 18, False),
    ("   si gene respiratoire", 16, False),
    ("", 10, False),
    ("Controle dans 7 jours.", 16, False),
    ("Signature + cachet", 16, False),
]

# Arabic-script page. Drug names stay Latin, as on a real ordonnance.
AR = [
    ("د. أمينة بنعلي", 22, True),
    ("طبيبة عامة - الدار البيضاء", 15, False),
    ("", 10, False),
    ("التاريخ: 12/03/2026", 16, False),
    ("", 10, False),
    ("Rp/ وصفة طبية", 20, True),
    ("", 10, False),
    ("1. Doliprane 1000 mg    قرص واحد", 18, False),
    ("   3 مرات في اليوم لمدة 5 أيام", 16, False),
    ("   عند الألم", 16, False),
    ("", 10, False),
    ("2. Toplexil شراب 125 مل", 18, False),
    ("   ملعقة كبيرة مرتين في اليوم لمدة 7 أيام", 16, False),
    ("", 10, False),
    ("3. Smecta 3 غ            كيس واحد", 18, False),
    ("   3 مرات في اليوم بعد كل وجبة", 16, False),
    ("", 10, False),
    ("المراجعة بعد 7 أيام", 16, False),
]


def is_arabic(text):
    return any("\u0600" <= c <= "\u06FF" for c in text)


def render(lines, w=980, h=1180, rule_at=160, blur=0.6, rot=-1.2, bg=(247, 244, 236)):
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    y = 70
    for text, size, bold in lines:
        if not text:
            y += size
            continue
        path = ARABIC_FONT if is_arabic(text) else LATIN_FONT
        d.text((70, y), text, font=ImageFont.truetype(path, size), fill=(28, 30, 38))
        y += size + 14
    d.line([(60, rule_at), (w - 60, rule_at)], fill=(150, 145, 135), width=3)
    img = img.rotate(rot, expand=False, fillcolor=bg, resample=Image.BICUBIC)
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    return img


def main():
    out = Path(__file__).parent / "outputs"
    out.mkdir(exist_ok=True)
    print(f"latin font : {LATIN_FONT}")
    print(f"arabic font: {ARABIC_FONT}")

    render(FR).save(out / "prescription_fixture.png")
    render(AR).save(out / "prescription_arabic.png")
    render(FR, blur=11, rot=0).save(out / "prescription_blurry.png")
    # h=460 cuts the page above item 4 (Aer sits at y=475), so Aer is genuinely
    # absent from this image.
    #
    # blur stays at the default 0.6 on purpose. At blur=2.4 the date band
    # (y 143-178) had no pixel darker than 128 -- min 181, sd 12.6, against
    # min 72 / sd 30.7 on the sharp page -- so the printed "12/03/2026" was
    # physically unreadable and the model returned 12/10/2023. That made the
    # ground truth unsatisfiable and tested blur robustness by accident, on a
    # fixture whose job is the crop. The blurry fixture covers blur already.
    wide = render(FR, h=460, rule_at=140)
    wide.save(out / "prescription_wide.png")

    # Same crop, padded back to a normal aspect ratio. gpt-4o returns
    # content=null with finish_reason="stop" for the 2.13:1 version on every
    # attempt, and handles this one fine, so the suite uses the padded one and
    # keeps the wide one as a documented repro.
    padded = Image.new("RGB", (wide.width, 1180), (255, 255, 255))
    padded.paste(wide, (0, 0))
    padded.save(out / "prescription_partial.png")

    for name in ("prescription_fixture.png", "prescription_arabic.png",
                 "prescription_blurry.png", "prescription_partial.png",
                 "prescription_wide.png"):
        p = out / name
        print(f"wrote {p.name:32} {p.stat().st_size // 1024:4} KB")


if __name__ == "__main__":
    main()
