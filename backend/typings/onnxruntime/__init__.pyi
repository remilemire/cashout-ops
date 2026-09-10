#
# onnxruntime ships no type information. This covers only the surface
# app/integrations/ocr/ppocr.py uses; extend it if that surface grows.

from collections.abc import Sequence
from typing import Any

class SessionOptions:
    intra_op_num_threads: int
    inter_op_num_threads: int
    def __init__(self) -> None: ...

class NodeArg:
    name: str
    shape: list[int | str | None]
    type: str

class InferenceSession:
    def __init__(
        self,
        path_or_bytes: str | bytes,
        sess_options: SessionOptions | None = None,
        providers: Sequence[str] | None = None,
    ) -> None: ...
    def get_inputs(self) -> list[NodeArg]: ...
    def get_outputs(self) -> list[NodeArg]: ...
    def run(
        self,
        output_names: Sequence[str] | None,
        input_feed: dict[str, Any],
    ) -> list[Any]: ...
