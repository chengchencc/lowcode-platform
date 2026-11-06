"""本地磁盘存储实现。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.core.config import settings


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, rel_path: str) -> Path:
        """把相对路径解析到根目录内，并挡住 `../` 逃逸。

        rel_path 由服务端生成（yyyy/MM/uuid.ext），本不该有异常值；
        但存储层不该假设调用方一定正确 —— 路径穿越是能读到任意文件的那类问题。
        """
        candidate = (self.root / rel_path).resolve()
        if not candidate.is_relative_to(self.root.resolve()):
            raise ValueError(f"非法的存储路径：{rel_path}")
        return candidate

    def save(self, rel_path: str, data: bytes) -> None:
        target = self._resolve(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        # 先写临时文件再改名：避免写到一半进程挂掉留下半截文件
        tmp = target.with_suffix(target.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(target)

    def read(self, rel_path: str) -> bytes:
        return self._resolve(rel_path).read_bytes()

    def delete(self, rel_path: str) -> None:
        self._resolve(rel_path).unlink(missing_ok=True)

    def exists(self, rel_path: str) -> bool:
        return self._resolve(rel_path).is_file()


@lru_cache
def get_storage() -> LocalStorage:
    return LocalStorage(settings.storage_path)
