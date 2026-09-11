#
# google-cloud-storage ships no type information. This covers only the surface
# app/integrations/storage/gcs.py and its lifespan use; extend it if that
# surface grows.

from google.auth.credentials import Credentials

class Blob:
    def download_as_bytes(self) -> bytes: ...
    def upload_from_string(
        self, data: bytes | str, content_type: str = "text/plain"
    ) -> None: ...
    def delete(self) -> None: ...

class Bucket:
    name: str
    def blob(self, blob_name: str) -> Blob: ...

class Client:
    def __init__(
        self,
        project: str | None = ...,
        credentials: Credentials | None = None,
    ) -> None: ...
    def bucket(self, bucket_name: str) -> Bucket: ...
