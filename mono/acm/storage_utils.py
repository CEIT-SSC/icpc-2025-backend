import os, uuid, mimetypes
from django.utils import timezone
from django.core.files.base import ContentFile, File
from django.core.files.storage import default_storage

class SaveResult(dict):
    @property
    def url(self): return self["url"]
    @property
    def key(self): return self["key"]

def s3_save_and_get_url(file_obj, *, folder="uploads", filename=None, content_type=None, overwrite=False) -> SaveResult:
    original_name = getattr(file_obj, "name", None)
    if isinstance(file_obj, (bytes, bytearray)):
        content = ContentFile(file_obj)
    elif hasattr(file_obj, "read"):
        content = file_obj if isinstance(file_obj, File) else File(file_obj)
    elif isinstance(file_obj, str) and os.path.exists(file_obj):
        with open(file_obj, "rb") as fh:
            content = ContentFile(fh.read())
        original_name = os.path.basename(file_obj)
    else:
        raise TypeError("file_obj must be bytes, a file-like object, or a valid file path")

    folder = (folder or "uploads").strip("/")
    if not filename:
        ext = os.path.splitext(original_name or "")[1].lower()
        if not ext and content_type:
            ext = mimetypes.guess_extension(content_type) or ""
        filename = f"{uuid.uuid4().hex}{ext}"

    dated = timezone.now().strftime("%Y/%m/%d")
    key = f"{folder}/{dated}/{filename}"

    if not content_type:
        content_type = getattr(file_obj, "content_type", None) or (mimetypes.guess_type(filename)[0] or "application/octet-stream")
    if not hasattr(content, "content_type"):
        setattr(content, "content_type", content_type)

    if overwrite and default_storage.exists(key):
        default_storage.delete(key)

    saved_key = default_storage.save(key, content)
    url = default_storage.url(saved_key)
    return SaveResult(key=saved_key, url=url)
