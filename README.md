# FB360 - Facebook 360 Photo Creator

Konverterar valfri bild till Facebook 360-kompatibelt format genom att justera dimensioner till 2:1 och injicera GPano XMP-metadata.

## Installation

### Beroenden

```bash
brew install exiftool imagemagick
```

### Skriptet

```bash
# Klona eller kopiera fb360.sh
chmod +x fb360.sh

# Valfritt: lägg till i PATH
sudo ln -s $(pwd)/fb360.sh /usr/local/bin/fb360
```

## Användning

```bash
# Grundläggande - skapar bild_360.jpg
./fb360.sh bild.jpg

# Ange utfilnamn
./fb360.sh foto.jpg panorama_360.jpg

# Med crop istället för padding
./fb360.sh landskap.jpg -m crop

# Högre upplösning med vit bakgrund
./fb360.sh bild.png -r 7200x3600 -b white

# Batch-konvertering
for f in *.jpg; do ./fb360.sh "$f"; done
```

## Alternativ

| Flag | Beskrivning | Standard |
|------|-------------|----------|
| `-r, --resolution WxH` | Målupplösning (måste vara 2:1) | 6000x3000 |
| `-m, --mode MODE` | Anpassningsläge: `pad`, `crop`, `stretch` | pad |
| `-b, --background COL` | Bakgrundsfärg för pad-läge | black |
| `-q, --quality Q` | JPEG-kvalitet 1-100 | 95 |
| `-v, --verbose` | Visa detaljerad information | - |
| `-h, --help` | Visa hjälp | - |

## Anpassningslägen

### `pad` (standard)
Skalar bilden så den passar inuti 2:1-formatet och lägger till kanter (letterbox/pillarbox).

```
┌────────────────────────┐
│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│  ← padding
│                        │
│      Original bild     │
│                        │
│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│  ← padding
└────────────────────────┘
```

### `crop`
Skalar och beskär bilden från mitten för att fylla hela 2:1-formatet.

```
  ┌──────────────────┐
  │    beskärs       │
┌─┼──────────────────┼─┐
│ │                  │ │
│ │  Behålls (2:1)   │ │
│ │                  │ │
└─┼──────────────────┼─┘
  │    beskärs       │
  └──────────────────┘
```

### `stretch`
Sträcker bilden till 2:1 (förvränger proportionerna).

## Stödda format

**Input:** JPEG, PNG, TIFF, BMP, GIF, WebP, HEIC

**Output:** JPEG (krävs för Facebook 360)

## Teknisk bakgrund

### Varför 2:1?

Facebook 360-foton använder **equirectangular projection** - samma format som används för att platta ut en sfär till en rektangel (tänk världskartor). Detta kräver exakt 2:1 aspektförhållande där:

- Bredden representerar 360° horisontellt
- Höjden representerar 180° vertikalt

### GPano XMP-metadata

Skriptet injicerar följande metadata som Facebook läser:

```
ProjectionType              : equirectangular
UsePanoramaViewer           : True
FullPanoWidthPixels         : 6000
FullPanoHeightPixels        : 3000
CroppedAreaImageWidthPixels : 6000
CroppedAreaImageHeightPixels: 3000
CroppedAreaLeftPixels       : 0
CroppedAreaTopPixels        : 0
InitialViewHeadingDegrees   : 180
InitialViewPitchDegrees     : 0
InitialViewRollDegrees      : 0
InitialHorizontalFOVDegrees : 90
```

### Verifiera metadata

```bash
exiftool -XMP-GPano:all bild_360.jpg
```

## Rekommenderade upplösningar

| Upplösning | Pixlar | Användning |
|------------|--------|------------|
| 4000×2000 | 8 MP | Snabb uppladdning |
| 6000×3000 | 18 MP | **Rekommenderad** |
| 7200×3600 | 26 MP | Hög kvalitet |
| 8000×4000 | 32 MP | Max kvalitet |

## Felsökning

### "Bilden visas inte som 360 på Facebook"

1. Kontrollera att metadata finns:
   ```bash
   exiftool -XMP-GPano:ProjectionType bild_360.jpg
   ```
   Ska visa: `equirectangular`

2. Kontrollera dimensioner:
   ```bash
   exiftool -ImageWidth -ImageHeight bild_360.jpg
   ```
   Ratio måste vara exakt 2:1

3. Ladda upp via Facebook-appen eller webbläsare (inte via API)

### "Bilden ser förvrängd ut"

360-foton ser alltid "böjda" ut som platta bilder - det är normalt. De ser rätt ut först när de visas i Facebooks 360-visare.

## Licens

MIT

## Se även

- [Facebook 360 Photos](https://www.facebook.com/help/392707984198498)
- [Photo Sphere XMP Metadata](https://developers.google.com/streetview/spherical-metadata)
- [ExifTool GPano Tags](https://exiftool.org/TagNames/XMP.html#GPano)
