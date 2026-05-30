import os
import re
from flask import Blueprint, jsonify, request, send_file, abort
from config import DOCUMENTARY_PATH, DOCUMENTARY_ARCHIVE_DIR
from services import list_files_from_url, download_file

docs_bp = Blueprint("docs", __name__, url_prefix="/api/docs")

_CACHED_FILES: list = []


def _get_files() -> list:
    global _CACHED_FILES
    if not _CACHED_FILES:
        _CACHED_FILES = list_files_from_url(DOCUMENTARY_PATH)
    return _CACHED_FILES


def _extract_tags(filename: str) -> str:
    tags = re.findall(r'\(([^)]+)\)', filename)
    return ", ".join(tags) if tags else "Khác"


# -----------------------------------------------------------
@docs_bp.get("")
def list_docs():
    """
    Trả về danh sách tài liệu, kèm trạng thái đã tải hay chưa.
    Query params: q (tìm kiếm), mode (name|type|number)
    """
    q    = request.args.get("q", "").lower().strip()
    mode = request.args.get("mode", "name")

    files = _get_files()
    result = []

    for idx, f in enumerate(files, start=1):
        # Filter
        if mode == "name" and q and q not in f["name"].lower():
            continue
        if mode == "type" and q and q not in _extract_tags(f["name"]).lower():
            continue
        if mode == "number":
            if q.isdigit() and int(q) != idx:
                continue
            elif not q.isdigit() and q:
                continue

        local_path    = os.path.join(DOCUMENTARY_ARCHIVE_DIR, f["name"])
        is_downloaded = os.path.exists(local_path)

        result.append({
            "stt":           idx,
            "id":            f["id"],
            "name":          f["name"],
            "tags":          _extract_tags(f["name"]),
            "is_downloaded": is_downloaded,
        })

    return jsonify(result)


@docs_bp.post("/download/<doc_id>")
def download_doc(doc_id: str):
    """Trigger tải file từ OneDrive về DOCUMENTARY_ARCHIVE_DIR."""
    files  = _get_files()
    target = next((f for f in files if f["id"] == doc_id), None)

    if not target:
        return jsonify({"error": "Không tìm thấy file"}), 404

    local_path = download_file(target, save_dir=DOCUMENTARY_ARCHIVE_DIR)
    if not local_path:
        return jsonify({"error": "Tải file thất bại"}), 500

    return jsonify({"message": "Đã tải thành công", "path": local_path})


@docs_bp.get("/file/<doc_id>")
def serve_doc(doc_id: str):
    """Serve file tài liệu local."""
    files  = _get_files()
    target = next((f for f in files if f["id"] == doc_id), None)

    if not target:
        abort(404)

    local_path = os.path.join(DOCUMENTARY_ARCHIVE_DIR, target["name"])
    if not os.path.exists(local_path):
        abort(404, description="File chưa được tải về")

    return send_file(local_path, as_attachment=True, download_name=target["name"])


@docs_bp.post("/refresh")
def refresh_docs():
    """Làm mới cache danh sách tài liệu từ OneDrive."""
    global _CACHED_FILES
    _CACHED_FILES = list_files_from_url(DOCUMENTARY_PATH)
    return jsonify({"count": len(_CACHED_FILES)})
