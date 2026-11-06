"""附件存储抽象。

当前只有本地磁盘实现。换对象存储（S3 / OSS / MinIO）时新增一个类并改
`get_storage()` 的装配即可，DB 结构与调用方都不用动（PRD §10 #4）。
"""

from app.storage.base import Storage
from app.storage.local import LocalStorage, get_storage

__all__ = ["LocalStorage", "Storage", "get_storage"]
