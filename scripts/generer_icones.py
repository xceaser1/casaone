"""Genere les icones PNG de l'application (PWA / home-screen) sans dependance.

Icone : fond vert URBAGEC + viseur de scan blanc (4 coins) + motif QR central.
Ecrit icon-180/192/512.png dans static/images/app/.
"""
import os
import struct
import zlib

VERT = (0x14, 0x68, 0x3F)
BLANC = (0xFF, 0xFF, 0xFF)

# Rectangles blancs en coordonnees normalisees (0..1) : viseur + motif QR.
MG, T, L = 0.19, 0.055, 0.17
RECTS = [
    # coins du viseur (L-shapes)
    (MG, MG, MG + L, MG + T), (MG, MG, MG + T, MG + L),                       # haut-gauche
    (1 - MG - L, MG, 1 - MG, MG + T), (1 - MG - T, MG, 1 - MG, MG + L),       # haut-droit
    (MG, 1 - MG - T, MG + L, 1 - MG), (MG, 1 - MG - L, MG + T, 1 - MG),       # bas-gauche
    (1 - MG - L, 1 - MG - T, 1 - MG, 1 - MG), (1 - MG - T, 1 - MG - L, 1 - MG, 1 - MG),  # bas-droit
    # motif QR au centre
    (0.40, 0.40, 0.48, 0.48), (0.52, 0.40, 0.60, 0.48),
    (0.40, 0.52, 0.48, 0.60), (0.53, 0.53, 0.60, 0.60),
]


def _png(taille):
    px = bytearray()
    rects = [(int(a * taille), int(b * taille), int(c * taille), int(d * taille)) for a, b, c, d in RECTS]
    for y in range(taille):
        px.append(0)  # filtre 0
        for x in range(taille):
            r, g, b = VERT
            for (x0, y0, x1, y1) in rects:
                if x0 <= x < x1 and y0 <= y < y1:
                    r, g, b = BLANC
                    break
            px += bytes((r, g, b, 255))

    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        return c + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", taille, taille, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(px), 9)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def main():
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "images", "app")
    os.makedirs(base, exist_ok=True)
    for t in (180, 192, 512):
        with open(os.path.join(base, f"icon-{t}.png"), "wb") as f:
            f.write(_png(t))
        print("ecrit", f"icon-{t}.png")


if __name__ == "__main__":
    main()
