import os
from flask import Blueprint, jsonify, send_file, abort
from config import IMAGE_PATHS, IMAGE_CATEGORY_DIR
from services import list_files_from_url, download_file

image_bp = Blueprint("image", __name__, url_prefix="/api/images")


@image_bp.get("/categories")
def get_categories():
    """Trả về cấu trúc category → [sites]."""
    result = {cat: list(sites.keys()) for cat, sites in IMAGE_PATHS.items()}
    return jsonify(result)


@image_bp.get("/<category>/<site>")
def get_images(category: str, site: str):
    """Trả về danh sách ảnh của một category/site với URL để tải."""
    cat  = category.upper()
    s    = site.upper()

    if cat not in IMAGE_PATHS or s not in IMAGE_PATHS[cat]:
        return jsonify({"error": f"Không có {cat}/{s}"}), 404

    folder_path = IMAGE_PATHS[cat][s]
    if not folder_path:
        return jsonify([])

    files = list_files_from_url(folder_path)
    result = [
        {
            "id":   f["id"],
            "name": f["name"],
            "url":  f"/api/images/file/{cat}/{s}/{f['name']}",
        }
        for f in files
    ]
    return jsonify(result)


@image_bp.get("/file/<category>/<site>/<filename>")
def serve_image(category: str, site: str, filename: str):
    """Serve file ảnh local."""
    cat       = category.upper()
    s         = site.upper()
    save_dir  = IMAGE_CATEGORY_DIR.get(cat)

    if not save_dir:
        abort(404)

    local_path = os.path.join(save_dir, filename)

    # Nếu chưa tải về → tải về từ OneDrive
    if not os.path.exists(local_path):
        folder_path = IMAGE_PATHS.get(cat, {}).get(s, "")
        if folder_path:
            files = list_files_from_url(folder_path)
            target = next((f for f in files if f["name"] == filename), None)
            if target:
                download_file(target, save_dir=save_dir)

    if not os.path.exists(local_path):
        abort(404)

    return send_file(local_path)
