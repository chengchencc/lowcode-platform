"""存储协议。"""

from __future__ import annotations

from typing import Protocol


class Storage(Protocol):
    """附件本体的读写。路径一律是相对根目录的 posix 风格路径（如 `2026/09/ab12.pdf`）。"""

    def save(self, rel_path: str, data: bytes) -> None:
        """写入。已存在时覆盖。"""

    def read(self, rel_path: str) -> bytes:
        """读取。不存在时抛 `FileNotFoundError`。"""

    def delete(self, rel_path: str) -> None:
        """删除。不存在时静默返回（便于幂等清理）。"""

    def exists(self, rel_path: str) -> bool: ...
