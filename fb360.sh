#!/bin/bash
#
# fb360.sh - Konvertera valfri bild till Facebook 360-kompatibelt format
#
# Användning: ./fb360.sh <input_image> [output_image] [options]
#
# Alternativ:
#   -r, --resolution WxH   Ange upplösning (standard: 6000x3000)
#   -m, --mode MODE        Läge: stretch, crop, pad (standard: pad)
#   -b, --background COL   Bakgrundsfärg för pad-läge (standard: black)
#   -q, --quality Q        JPEG-kvalitet 1-100 (standard: 95)
#   -h, --help             Visa hjälp
#
# Exempel:
#   ./fb360.sh photo.jpg                    # Skapa photo_360.jpg
#   ./fb360.sh photo.jpg output.jpg         # Ange utfil
#   ./fb360.sh photo.jpg -m crop            # Beskär till 2:1
#   ./fb360.sh photo.jpg -r 7200x3600       # Högre upplösning

set -e

# Standardvärden
DEFAULT_WIDTH=6000
DEFAULT_HEIGHT=3000
MODE="pad"
BACKGROUND="black"
QUALITY=95
VERBOSE=false

# Färger för output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_help() {
    cat << 'EOF'
╔═══════════════════════════════════════════════════════════════════════╗
║                    FB360 - Facebook 360 Photo Creator                  ║
╠═══════════════════════════════════════════════════════════════════════╣
║  Konverterar valfri bild till Facebook 360-kompatibelt format         ║
║  genom att justera dimensioner och injicera GPano XMP-metadata.       ║
╚═══════════════════════════════════════════════════════════════════════╝

ANVÄNDNING:
    fb360.sh <input_image> [output_image] [options]

ALTERNATIV:
    -r, --resolution WxH   Målupplösning (standard: 6000x3000)
                           Måste vara 2:1 förhållande

    -m, --mode MODE        Hur bilden anpassas till 2:1:
                           • pad    - Lägg till svarta kanter (standard)
                           • crop   - Beskär till 2:1
                           • stretch - Sträck bilden (förvränger)

    -b, --background COL   Bakgrundsfärg för pad-läge
                           Exempel: black, white, #ff0000, "rgb(50,50,50)"

    -q, --quality Q        JPEG-kvalitet 1-100 (standard: 95)

    -v, --verbose          Visa detaljerad information

    -h, --help             Visa denna hjälp

EXEMPEL:
    # Grundläggande användning
    fb360.sh semester.jpg

    # Ange utfil
    fb360.sh foto.jpg panorama_360.jpg

    # Beskär istället för att padda
    fb360.sh landskap.jpg -m crop

    # Högre upplösning med vit bakgrund
    fb360.sh bild.png -r 7200x3600 -b white

    # Batch-konvertering
    for f in *.jpg; do fb360.sh "$f"; done

STÖDDA FORMAT:
    Input:  JPEG, PNG, TIFF, BMP, GIF, WebP, HEIC
    Output: JPEG (krävs för Facebook 360)

TEKNISK INFO:
    • Facebook kräver 2:1 aspektförhållande (equirectangular)
    • GPano XMP-metadata injiceras automatiskt
    • ProjectionType sätts till "equirectangular"
    • Metadata bevaras (EXIF kopieras från original)

EOF
}

log_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1" >&2
}

# Kontrollera beroenden
check_dependencies() {
    local missing=()

    if ! command -v magick &> /dev/null; then
        missing+=("imagemagick")
    fi

    if ! command -v exiftool &> /dev/null; then
        missing+=("exiftool")
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        log_error "Saknade beroenden: ${missing[*]}"
        echo "Installera med: brew install ${missing[*]}"
        exit 1
    fi
}

# Validera 2:1 förhållande
validate_resolution() {
    local width=$1
    local height=$2

    if [ $((width / height)) -ne 2 ] || [ $((width % height)) -ne 0 ]; then
        log_error "Upplösning måste ha exakt 2:1 förhållande"
        log_error "Angiven: ${width}x${height} (förhållande: $(echo "scale=2; $width / $height" | bc))"
        echo "Exempel på giltiga upplösningar: 6000x3000, 4000x2000, 7200x3600"
        exit 1
    fi
}

# Hämta bilddimensioner
get_dimensions() {
    local image=$1
    magick identify -format "%w %h" "$image" 2>/dev/null
}

# Huvudfunktion för bildkonvertering
process_image() {
    local input=$1
    local output=$2
    local target_width=$3
    local target_height=$4

    # Hämta originaldimensioner
    read -r orig_width orig_height <<< "$(get_dimensions "$input")"

    if [ -z "$orig_width" ] || [ -z "$orig_height" ]; then
        log_error "Kunde inte läsa bilddimensioner"
        exit 1
    fi

    local orig_ratio=$(echo "scale=4; $orig_width / $orig_height" | bc)
    local target_ratio="2.0000"

    if $VERBOSE; then
        log_info "Original: ${orig_width}x${orig_height} (ratio: $orig_ratio)"
        log_info "Mål: ${target_width}x${target_height} (ratio: $target_ratio)"
        log_info "Läge: $MODE"
    fi

    # Skapa temporär fil
    local temp_file=$(mktemp /tmp/fb360_XXXXXX.jpg)
    trap "rm -f $temp_file" EXIT

    case $MODE in
        pad)
            # Beräkna hur bilden ska skalas för att passa inuti 2:1
            # och sedan centrera med padding
            log_info "Anpassar bild med padding..."
            magick "$input" \
                -resize "${target_width}x${target_height}" \
                -gravity center \
                -background "$BACKGROUND" \
                -extent "${target_width}x${target_height}" \
                -quality "$QUALITY" \
                "$temp_file"
            ;;
        crop)
            # Beskär till 2:1 från mitten
            log_info "Beskär bild till 2:1..."
            magick "$input" \
                -resize "${target_width}x${target_height}^" \
                -gravity center \
                -crop "${target_width}x${target_height}+0+0" \
                +repage \
                -quality "$QUALITY" \
                "$temp_file"
            ;;
        stretch)
            # Sträck bilden (förvränger)
            log_warn "Stretch-läge förvränger bilden!"
            magick "$input" \
                -resize "${target_width}x${target_height}!" \
                -quality "$QUALITY" \
                "$temp_file"
            ;;
        *)
            log_error "Okänt läge: $MODE"
            exit 1
            ;;
    esac

    # Verifiera dimensioner
    read -r new_width new_height <<< "$(get_dimensions "$temp_file")"

    if [ "$new_width" -ne "$target_width" ] || [ "$new_height" -ne "$target_height" ]; then
        log_error "Dimensionsfel! Fick ${new_width}x${new_height}, förväntade ${target_width}x${target_height}"
        exit 1
    fi

    # Kopiera till utfil
    cp "$temp_file" "$output"

    log_success "Bild konverterad: ${new_width}x${new_height}"
}

# Injicera GPano metadata
inject_metadata() {
    local image=$1
    local width=$2
    local height=$3

    log_info "Injicerar GPano XMP-metadata..."

    # Kopiera ursprunglig EXIF-data om möjlig och lägg till GPano-metadata
    exiftool -overwrite_original \
        -XMP-GPano:ProjectionType="equirectangular" \
        -XMP-GPano:UsePanoramaViewer="True" \
        -XMP-GPano:FullPanoWidthPixels="$width" \
        -XMP-GPano:FullPanoHeightPixels="$height" \
        -XMP-GPano:CroppedAreaImageWidthPixels="$width" \
        -XMP-GPano:CroppedAreaImageHeightPixels="$height" \
        -XMP-GPano:CroppedAreaLeftPixels="0" \
        -XMP-GPano:CroppedAreaTopPixels="0" \
        -XMP-GPano:InitialViewHeadingDegrees="180" \
        -XMP-GPano:InitialViewPitchDegrees="0" \
        -XMP-GPano:InitialViewRollDegrees="0" \
        -XMP-GPano:InitialHorizontalFOVDegrees="90" \
        "$image" > /dev/null 2>&1

    log_success "GPano-metadata injicerad"
}

# Verifiera resultat
verify_result() {
    local image=$1

    log_info "Verifierar resultat..."

    # Kontrollera att metadata finns
    local projection=$(exiftool -s -s -s -XMP-GPano:ProjectionType "$image" 2>/dev/null)

    if [ "$projection" = "equirectangular" ]; then
        log_success "ProjectionType: equirectangular ✓"
    else
        log_error "ProjectionType saknas eller felaktig!"
        return 1
    fi

    # Visa sammanfattning
    if $VERBOSE; then
        echo ""
        echo "═══════════════════════════════════════"
        echo "GPano Metadata:"
        exiftool -G1 -XMP-GPano:all "$image" 2>/dev/null | sed 's/^/  /'
        echo "═══════════════════════════════════════"
    fi

    return 0
}

# Huvudprogram
main() {
    local input=""
    local output=""
    local width=$DEFAULT_WIDTH
    local height=$DEFAULT_HEIGHT

    # Parsea argument
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                print_help
                exit 0
                ;;
            -r|--resolution)
                if [[ $2 =~ ^([0-9]+)x([0-9]+)$ ]]; then
                    width="${BASH_REMATCH[1]}"
                    height="${BASH_REMATCH[2]}"
                else
                    log_error "Ogiltigt upplösningsformat: $2"
                    echo "Använd format: WIDTHxHEIGHT (t.ex. 6000x3000)"
                    exit 1
                fi
                shift 2
                ;;
            -m|--mode)
                MODE="$2"
                if [[ ! "$MODE" =~ ^(pad|crop|stretch)$ ]]; then
                    log_error "Ogiltigt läge: $MODE"
                    echo "Giltiga lägen: pad, crop, stretch"
                    exit 1
                fi
                shift 2
                ;;
            -b|--background)
                BACKGROUND="$2"
                shift 2
                ;;
            -q|--quality)
                QUALITY="$2"
                if [[ ! "$QUALITY" =~ ^[0-9]+$ ]] || [ "$QUALITY" -lt 1 ] || [ "$QUALITY" -gt 100 ]; then
                    log_error "Kvalitet måste vara 1-100"
                    exit 1
                fi
                shift 2
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -*)
                log_error "Okänt alternativ: $1"
                echo "Använd --help för hjälp"
                exit 1
                ;;
            *)
                if [ -z "$input" ]; then
                    input="$1"
                elif [ -z "$output" ]; then
                    output="$1"
                else
                    log_error "För många argument"
                    exit 1
                fi
                shift
                ;;
        esac
    done

    # Validera input
    if [ -z "$input" ]; then
        log_error "Ingen inputbild angiven"
        echo "Användning: fb360.sh <input_image> [output_image] [options]"
        echo "Använd --help för mer information"
        exit 1
    fi

    if [ ! -f "$input" ]; then
        log_error "Filen finns inte: $input"
        exit 1
    fi

    # Generera utfilnamn om inte angivet
    if [ -z "$output" ]; then
        local basename="${input%.*}"
        output="${basename}_360.jpg"
    fi

    # Se till att utfilen har .jpg-ändelse
    if [[ ! "$output" =~ \.[jJ][pP][eE]?[gG]$ ]]; then
        output="${output}.jpg"
    fi

    echo ""
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║              FB360 - Facebook 360 Photo Creator               ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo ""

    # Kör pipeline
    check_dependencies
    validate_resolution "$width" "$height"

    log_info "Input: $input"
    log_info "Output: $output"

    process_image "$input" "$output" "$width" "$height"
    inject_metadata "$output" "$width" "$height"
    verify_result "$output"

    echo ""
    log_success "Klar! Filen är redo för Facebook 360:"
    echo "    $output"
    echo ""

    # Visa filstorlek
    local size=$(du -h "$output" | cut -f1)
    log_info "Filstorlek: $size"
}

main "$@"
