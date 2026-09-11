"""
Cloudinary Image Service for Waqar Store
Provides persistent image uploads and deletions via Cloudinary CDN.
Supports fallback to local storage when Cloudinary credentials are not set.
"""
import os
import re
import uuid
from werkzeug.utils import secure_filename

# Try importing cloudinary
try:
    import cloudinary
    import cloudinary.uploader
    import cloudinary.api
    CLOUDINARY_AVAILABLE = True
except ImportError:
    CLOUDINARY_AVAILABLE = False

_configured = False

def is_cloudinary_configured():
    """Check if Cloudinary credentials exist in environment variables."""
    if not CLOUDINARY_AVAILABLE:
        return False
    
    # 1. Check CLOUDINARY_URL
    if os.environ.get('CLOUDINARY_URL'):
        return True

    # 2. Check individual credentials
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME')
    api_key = os.environ.get('CLOUDINARY_API_KEY')
    api_secret = os.environ.get('CLOUDINARY_API_SECRET')
    return bool(cloud_name and api_key and api_secret)

def _init_cloudinary():
    """Initialize Cloudinary configuration from environment variables."""
    global _configured
    if not is_cloudinary_configured() or _configured:
        return

    if os.environ.get('CLOUDINARY_URL'):
        cloudinary.config(secure=True)
    else:
        cloudinary.config(
            cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
            api_key=os.environ.get('CLOUDINARY_API_KEY'),
            api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
            secure=True
        )
    _configured = True

def extract_public_id(image_url):
    """
    Extract Cloudinary public_id from URL.
    E.g.: https://res.cloudinary.com/demo/image/upload/v1612345678/waqar_store/products/prod_1.jpg
    Returns: waqar_store/products/prod_1
    """
    if not image_url or 'res.cloudinary.com' not in image_url:
        return None

    # Matches /upload/(optional v12345/)(public_id).(ext)
    match = re.search(r'/upload/(?:v\d+/)?(.+?)(?:\.[a-zA-Z0-9]+)?$', image_url)
    if match:
        return match.group(1)
    return None

def upload_image(file_storage, folder="waqar_store/products", prefix="img"):
    """
    Upload an image file.
    - If Cloudinary is configured -> Uploads to Cloudinary and returns permanent HTTPS URL.
    - If Cloudinary is NOT configured -> Saves locally to static/uploads (local fallback).
    
    Args:
        file_storage: Werkzeug FileStorage object from request.files.
        folder: Cloudinary folder name.
        prefix: Prefix for unique file name.
    
    Returns:
        str: Permanent URL of the uploaded image, or None if invalid.
    """
    if not file_storage or not file_storage.filename:
        return None

    fname = secure_filename(file_storage.filename)
    unique_id = f"{prefix}_{uuid.uuid4().hex[:8]}"

    if is_cloudinary_configured():
        _init_cloudinary()
        try:
            # Upload directly to Cloudinary
            response = cloudinary.uploader.upload(
                file_storage,
                folder=folder,
                public_id=f"{unique_id}_{os.path.splitext(fname)[0]}",
                resource_type="image"
            )
            secure_url = response.get('secure_url')
            if secure_url:
                print(f"[Cloudinary] Uploaded successfully: {secure_url}")
                return secure_url
        except Exception as e:
            print(f"[Cloudinary ERROR] Upload failed: {e}. Falling back to local storage.")

    # Fallback to local storage
    try:
        from flask import current_app
        upload_folder = current_app.config.get('UPLOAD_FOLDER', os.path.join(os.getcwd(), 'static', 'uploads'))
    except Exception:
        upload_folder = os.path.join(os.getcwd(), 'static', 'uploads')

    os.makedirs(upload_folder, exist_ok=True)
    local_name = f"{unique_id}_{fname}"
    save_path = os.path.join(upload_folder, local_name)
    file_storage.seek(0)
    file_storage.save(save_path)
    print(f"[Local Fallback] Saved image locally: /static/uploads/{local_name}")
    return f"/static/uploads/{local_name}"

def delete_image(image_url):
    """
    Delete image from Cloudinary or local disk.
    Leaves Unsplash and external third-party images untouched.
    """
    if not image_url:
        return

    # Case 1: Cloudinary Image
    if 'res.cloudinary.com' in image_url:
        public_id = extract_public_id(image_url)
        if public_id and is_cloudinary_configured():
            _init_cloudinary()
            try:
                cloudinary.uploader.destroy(public_id)
                print(f"[Cloudinary] Deleted image: {public_id}")
            except Exception as e:
                print(f"[Cloudinary Note] Delete warning: {e}")
        return

    # Case 2: Local Upload Image
    if image_url.startswith('/static/uploads/'):
        try:
            from flask import current_app
            local_rel = image_url.lstrip('/')
            local_path = os.path.join(current_app.root_path, local_rel)
            if os.path.exists(local_path):
                os.remove(local_path)
                print(f"[Local Storage] Deleted local image: {local_path}")
        except Exception as e:
            print(f"[Local Storage] Delete warning: {e}")
        return

    # Case 3: External URLs (Unsplash, etc.) -> Never delete external URLs

