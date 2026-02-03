#!/usr/bin/env python3
"""
FB360 Server - 360° Viewer with AI Image Generation

Serves the viewer and provides an API endpoint for Gemini image-to-image generation.
Automatically fixes aspect ratio to 2:1 and injects GPano metadata.
"""

import base64
import io
import os
import subprocess
import sys
import uuid
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, send_file

try:
    from openai import OpenAI
except ImportError:
    print("ERROR: openai package not installed. Run: pip install openai")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow package not installed. Run: pip install Pillow")
    sys.exit(1)

# Register HEIC support
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_SUPPORTED = True
except ImportError:
    HEIC_SUPPORTED = False
    print("WARNING: pillow-heif not installed. HEIC support disabled.")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__, static_folder='.')

# Output directory for generated images
OUTPUT_DIR = Path(__file__).parent / "generated"
OUTPUT_DIR.mkdir(exist_ok=True)

# Gallery directory for all processed images
GALLERY_DIR = Path(__file__).parent / "gallery"
GALLERY_DIR.mkdir(exist_ok=True)

# Thumbnails directory
THUMBS_DIR = GALLERY_DIR / "thumbs"
THUMBS_DIR.mkdir(exist_ok=True)

# Thumbnail dimensions
THUMB_WIDTH = 300
THUMB_HEIGHT = 150

# Default target resolution
DEFAULT_WIDTH = 6000
DEFAULT_HEIGHT = 3000


def get_client():
    """Initialize OpenAI client with OpenRouter configuration."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")

    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


def fix_aspect_ratio(image_data: bytes, mode: str = "pad", bg_color: str = "black") -> bytes:
    """
    Fix image to 2:1 aspect ratio for equirectangular projection.

    Args:
        image_data: Raw image bytes
        mode: "pad" (add letterbox/pillarbox), "crop" (crop to fit), "stretch"
        bg_color: Background color for padding

    Returns:
        Processed image as JPEG bytes
    """
    img = Image.open(io.BytesIO(image_data))

    # Convert to RGB if necessary (for JPEG output)
    if img.mode in ('RGBA', 'P'):
        background = Image.new('RGB', img.size, bg_color)
        if img.mode == 'RGBA':
            background.paste(img, mask=img.split()[-1])
        else:
            background.paste(img)
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    width, height = img.size
    current_ratio = width / height
    target_ratio = 2.0

    # Check if already 2:1
    if abs(current_ratio - target_ratio) < 0.01:
        # Already good, just ensure reasonable size
        if width < DEFAULT_WIDTH:
            new_width = DEFAULT_WIDTH
            new_height = DEFAULT_HEIGHT
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        output = io.BytesIO()
        img.save(output, format='JPEG', quality=95)
        return output.getvalue()

    if mode == "stretch":
        # Simple stretch to 2:1
        new_width = width
        new_height = width // 2
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    elif mode == "crop":
        # Crop from center to achieve 2:1
        if current_ratio > target_ratio:
            # Too wide - crop sides
            new_width = int(height * target_ratio)
            left = (width - new_width) // 2
            img = img.crop((left, 0, left + new_width, height))
        else:
            # Too tall - crop top/bottom
            new_height = int(width / target_ratio)
            top = (height - new_height) // 2
            img = img.crop((0, top, width, top + new_height))

    else:  # mode == "pad"
        # Add padding to achieve 2:1
        if current_ratio > target_ratio:
            # Too wide - add top/bottom padding
            new_height = int(width / target_ratio)
            new_img = Image.new('RGB', (width, new_height), bg_color)
            paste_y = (new_height - height) // 2
            new_img.paste(img, (0, paste_y))
            img = new_img
        else:
            # Too tall - add left/right padding
            new_width = int(height * target_ratio)
            new_img = Image.new('RGB', (new_width, height), bg_color)
            paste_x = (new_width - width) // 2
            new_img.paste(img, (paste_x, 0))
            img = new_img

    # Scale to target resolution if smaller
    width, height = img.size
    if width < DEFAULT_WIDTH:
        img = img.resize((DEFAULT_WIDTH, DEFAULT_HEIGHT), Image.Resampling.LANCZOS)

    output = io.BytesIO()
    img.save(output, format='JPEG', quality=95)
    return output.getvalue()


def inject_gpano_metadata(filepath: Path) -> bool:
    """
    Inject GPano XMP metadata for Facebook 360 compatibility.
    Requires exiftool to be installed.
    """
    # Get image dimensions
    try:
        with Image.open(filepath) as img:
            width, height = img.size
    except Exception as e:
        print(f"Could not read image dimensions: {e}")
        return False

    # Build exiftool command
    xmp_args = [
        'exiftool',
        '-overwrite_original',
        f'-XMP-GPano:ProjectionType=equirectangular',
        f'-XMP-GPano:UsePanoramaViewer=True',
        f'-XMP-GPano:FullPanoWidthPixels={width}',
        f'-XMP-GPano:FullPanoHeightPixels={height}',
        f'-XMP-GPano:CroppedAreaImageWidthPixels={width}',
        f'-XMP-GPano:CroppedAreaImageHeightPixels={height}',
        f'-XMP-GPano:CroppedAreaLeftPixels=0',
        f'-XMP-GPano:CroppedAreaTopPixels=0',
        f'-XMP-GPano:InitialViewHeadingDegrees=180',
        f'-XMP-GPano:InitialViewPitchDegrees=0',
        f'-XMP-GPano:InitialViewRollDegrees=0',
        f'-XMP-GPano:InitialHorizontalFOVDegrees=90',
        str(filepath)
    ]

    try:
        result = subprocess.run(xmp_args, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"exiftool error: {result.stderr}")
            return False
        return True
    except FileNotFoundError:
        print("exiftool not found - GPano metadata not injected")
        return False
    except Exception as e:
        print(f"Error running exiftool: {e}")
        return False


def create_thumbnail(image_path: Path) -> Path:
    """Create a thumbnail for a gallery image."""
    thumb_path = THUMBS_DIR / image_path.name

    try:
        with Image.open(image_path) as img:
            # Convert to RGB if needed
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # Create thumbnail maintaining aspect ratio
            img.thumbnail((THUMB_WIDTH, THUMB_HEIGHT), Image.Resampling.LANCZOS)
            img.save(thumb_path, format='JPEG', quality=80)

        return thumb_path
    except Exception as e:
        print(f"Error creating thumbnail: {e}")
        return None


def generate_panorama(input_base64: str, mime_type: str, prompt: str,
                      fix_ratio: bool = True, ratio_mode: str = "pad",
                      input_width: int = None, input_height: int = None) -> dict:
    """Generate a new panorama image from input image and prompt."""
    try:
        client = get_client()
    except ValueError as e:
        return {"error": str(e)}

    # Create full prompt for panorama generation
    full_prompt = f"""Generate an image: {prompt}

Use the first image as the reference for final aspect ratio. This is an equirectangular panorama photo. Keep all the details and composition but transform the style/setting as described."""

    try:
        response = client.chat.completions.create(
            model="google/gemini-3-pro-image-preview",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": full_prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{input_base64}"
                            }
                        }
                    ]
                }
            ],
        )

        message = response.choices[0].message

        # Print any textual content for debugging
        if message.content:
            print(f"Model response: {message.content}")

        # Check for images in response (exact logic from generate_image.py)
        if hasattr(message, 'images') and message.images:
            for image_data in message.images:
                if image_data["type"] == "image_url" and image_data["image_url"]["url"].startswith("data:image"):
                    # Extract base64 data from data URL
                    data_url = image_data["image_url"]["url"]
                    # Format: data:image/png;base64,<base64_data>
                    base64_data = data_url.split(',', 1)[1]
                    raw_image = base64.b64decode(base64_data)

                    # Fix aspect ratio if requested
                    if fix_ratio:
                        try:
                            processed_image = fix_aspect_ratio(raw_image, mode=ratio_mode)
                        except Exception as e:
                            print(f"Error fixing aspect ratio: {e}")
                            processed_image = raw_image
                    else:
                        processed_image = raw_image

                    # Save to gallery
                    filename = f"ai_generated_{uuid.uuid4().hex[:8]}_360.jpg"
                    filepath = GALLERY_DIR / filename

                    with open(filepath, "wb") as f:
                        f.write(processed_image)

                    # Inject GPano metadata
                    gpano_success = inject_gpano_metadata(filepath)

                    # Create thumbnail
                    create_thumbnail(filepath)

                    # Re-read file after metadata injection
                    with open(filepath, "rb") as f:
                        final_image = f.read()

                    return {
                        "success": True,
                        "image": base64.b64encode(final_image).decode('utf-8'),
                        "filename": filename,
                        "filepath": str(filepath),
                        "gallery_url": f"/gallery/{filename}",
                        "thumb_url": f"/gallery/thumbs/{filename}",
                        "gpano_injected": gpano_success,
                        "message": message.content if message.content else "Image generated successfully"
                    }

        # No image found
        return {
            "error": "No image generated",
            "message": message.content if message.content else "Model did not return an image"
        }

    except Exception as e:
        return {"error": str(e)}


# Routes
@app.route('/')
def index():
    return send_file('viewer.html')


@app.route('/viewer.html')
def viewer():
    return send_file('viewer.html')


@app.route('/generated/<filename>')
def serve_generated(filename):
    return send_from_directory(OUTPUT_DIR, filename)


@app.route('/api/generate', methods=['POST'])
def api_generate():
    """API endpoint for panorama generation.

    Expects JSON body with:
    - image: base64 encoded image data (without data: prefix)
    - mime_type: image MIME type (e.g., "image/jpeg")
    - prompt: text prompt for transformation
    - fix_ratio: (optional) whether to fix aspect ratio to 2:1 (default: true)
    - ratio_mode: (optional) "pad", "crop", or "stretch" (default: "pad")
    - width: (optional) input image width for dimension matching
    - height: (optional) input image height for dimension matching
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "No JSON data provided"}), 400

    image_data = data.get('image')
    mime_type = data.get('mime_type', 'image/jpeg')
    prompt = data.get('prompt')
    fix_ratio = data.get('fix_ratio', True)
    ratio_mode = data.get('ratio_mode', 'pad')
    input_width = data.get('width')
    input_height = data.get('height')

    if not image_data:
        return jsonify({"error": "No image provided"}), 400

    if not prompt:
        return jsonify({"error": "No prompt provided"}), 400

    # Remove data URL prefix if present
    if ',' in image_data:
        image_data = image_data.split(',', 1)[1]

    result = generate_panorama(image_data, mime_type, prompt, fix_ratio, ratio_mode, input_width, input_height)

    if "error" in result:
        return jsonify(result), 500

    return jsonify(result)


@app.route('/api/fix-ratio', methods=['POST'])
def api_fix_ratio():
    """Fix aspect ratio of an uploaded image without AI generation.

    Expects JSON body with:
    - image: base64 encoded image data
    - mode: (optional) "pad", "crop", or "stretch" (default: "pad")
    - name: (optional) original filename for gallery
    - save_to_gallery: (optional) whether to save to gallery (default: true)
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "No JSON data provided"}), 400

    image_data = data.get('image')
    mode = data.get('mode', 'pad')
    original_name = data.get('name', 'image')
    save_to_gallery = data.get('save_to_gallery', True)

    if not image_data:
        return jsonify({"error": "No image provided"}), 400

    # Remove data URL prefix if present
    if ',' in image_data:
        image_data = image_data.split(',', 1)[1]

    try:
        raw_image = base64.b64decode(image_data)
        processed_image = fix_aspect_ratio(raw_image, mode=mode)

        # Create filename based on original name
        base_name = Path(original_name).stem
        filename = f"{base_name}_360.jpg"

        # Save to gallery
        if save_to_gallery:
            gallery_path = GALLERY_DIR / filename
            # Avoid overwriting
            counter = 1
            while gallery_path.exists():
                filename = f"{base_name}_360_{counter}.jpg"
                gallery_path = GALLERY_DIR / filename
                counter += 1

            with open(gallery_path, "wb") as f:
                f.write(processed_image)

            # Inject GPano metadata
            gpano_success = inject_gpano_metadata(gallery_path)

            # Create thumbnail
            create_thumbnail(gallery_path)

            # Re-read file after metadata injection
            with open(gallery_path, "rb") as f:
                final_image = f.read()
        else:
            # Just process without saving
            final_image = processed_image
            gpano_success = False

        return jsonify({
            "success": True,
            "image": base64.b64encode(final_image).decode('utf-8'),
            "filename": filename,
            "gpano_injected": gpano_success,
            "gallery_url": f"/gallery/{filename}" if save_to_gallery else None,
            "thumb_url": f"/gallery/thumbs/{filename}" if save_to_gallery else None
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/gallery', methods=['GET'])
def api_gallery_list():
    """List all images in the gallery."""
    images = []
    for filepath in sorted(GALLERY_DIR.glob('*.jpg'), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = filepath.stat()
        thumb_path = THUMBS_DIR / filepath.name

        # Create thumbnail if missing
        if not thumb_path.exists():
            create_thumbnail(filepath)

        images.append({
            "filename": filepath.name,
            "size": stat.st_size,
            "created": stat.st_mtime,
            "url": f"/gallery/{filepath.name}",
            "thumb_url": f"/gallery/thumbs/{filepath.name}"
        })
    return jsonify({"images": images})


@app.route('/api/gallery', methods=['POST'])
def api_gallery_save():
    """Save an image to the gallery.

    Expects JSON body with:
    - image: base64 encoded image data
    - name: (optional) filename to use
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "No JSON data provided"}), 400

    image_data = data.get('image')
    name = data.get('name', f"image_{uuid.uuid4().hex[:8]}")

    if not image_data:
        return jsonify({"error": "No image provided"}), 400

    # Remove data URL prefix if present
    if ',' in image_data:
        image_data = image_data.split(',', 1)[1]

    # Ensure .jpg extension
    if not name.endswith('.jpg'):
        name = name.rsplit('.', 1)[0] + '.jpg'

    filepath = GALLERY_DIR / name

    # Avoid overwriting - add suffix if exists
    counter = 1
    original_name = name
    while filepath.exists():
        name = original_name.rsplit('.', 1)[0] + f"_{counter}.jpg"
        filepath = GALLERY_DIR / name
        counter += 1

    try:
        with open(filepath, "wb") as f:
            f.write(base64.b64decode(image_data))

        return jsonify({
            "success": True,
            "filename": name,
            "url": f"/gallery/{name}"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/gallery/<filename>', methods=['DELETE'])
def api_gallery_delete(filename):
    """Delete an image from the gallery."""
    filepath = GALLERY_DIR / filename
    if not filepath.exists():
        return jsonify({"error": "File not found"}), 404

    try:
        filepath.unlink()

        # Also delete thumbnail if exists
        thumb_path = THUMBS_DIR / filename
        if thumb_path.exists():
            thumb_path.unlink()

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/gallery/<filename>')
def serve_gallery(filename):
    """Serve a gallery image."""
    return send_from_directory(GALLERY_DIR, filename)


@app.route('/gallery/thumbs/<filename>')
def serve_thumbnail(filename):
    """Serve a thumbnail image."""
    return send_from_directory(THUMBS_DIR, filename)


@app.route('/api/convert-heic', methods=['POST'])
def api_convert_heic():
    """Convert HEIC image to JPEG.

    Expects JSON body with:
    - image: base64 encoded HEIC image data
    """
    if not HEIC_SUPPORTED:
        return jsonify({"error": "HEIC support not available. Install pillow-heif."}), 500

    data = request.get_json()

    if not data:
        return jsonify({"error": "No JSON data provided"}), 400

    image_data = data.get('image')

    if not image_data:
        return jsonify({"error": "No image provided"}), 400

    # Remove data URL prefix if present
    if ',' in image_data:
        image_data = image_data.split(',', 1)[1]

    try:
        raw_image = base64.b64decode(image_data)
        img = Image.open(io.BytesIO(raw_image))

        # Convert to RGB if necessary
        if img.mode in ('RGBA', 'P'):
            background = Image.new('RGB', img.size, 'black')
            if img.mode == 'RGBA':
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Save as JPEG
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=95)
        jpeg_data = output.getvalue()

        return jsonify({
            "success": True,
            "image": base64.b64encode(jpeg_data).decode('utf-8'),
            "width": img.width,
            "height": img.height,
            "mime_type": "image/jpeg"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/status')
def api_status():
    """Check if API key is configured."""
    api_key = os.getenv("OPENROUTER_API_KEY")

    # Check for exiftool
    try:
        subprocess.run(['exiftool', '-ver'], capture_output=True)
        exiftool_available = True
    except FileNotFoundError:
        exiftool_available = False

    return jsonify({
        "api_configured": bool(api_key),
        "exiftool_available": exiftool_available,
        "heic_supported": HEIC_SUPPORTED,
        "message": "Ready" if api_key else "OPENROUTER_API_KEY not set"
    })


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='FB360 Server')
    parser.add_argument('--port', '-p', type=int, default=8360, help='Port to run on')
    parser.add_argument('--host', '-H', default='127.0.0.1', help='Host to bind to')
    args = parser.parse_args()

    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║              FB360 Viewer + AI Generation                     ║")
    print("╚═══════════════════════════════════════════════════════════════╝")
    print()
    print(f"  🌐 http://{args.host}:{args.port}/")
    print()

    # Check API key
    if os.getenv("OPENROUTER_API_KEY"):
        print("  ✓ OPENROUTER_API_KEY is set")
    else:
        print("  ⚠️  OPENROUTER_API_KEY not set - AI generation disabled")
        print("     Set it with: export OPENROUTER_API_KEY='your-key'")

    # Check exiftool
    try:
        subprocess.run(['exiftool', '-ver'], capture_output=True)
        print("  ✓ exiftool is available")
    except FileNotFoundError:
        print("  ⚠️  exiftool not found - GPano metadata will not be injected")
        print("     Install with: brew install exiftool")

    print()
    print("  Tryck Ctrl+C för att avsluta.")
    print()

    app.run(host=args.host, port=args.port, debug=True)
