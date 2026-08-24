__version__ = "2.8.9"

# Python 3.13 兼容：Path.glob 返回可迭代对象（如 map），
# 这里统一转为 list，保证与项目内既有用法（可拼接、可重复遍历）一致。
from pathlib import Path

_orig_glob = Path.glob
if not isinstance(Path(".").glob("*"), list):

    def _glob_list(self: Path, pattern: str):  # type: ignore[override]
        return list(_orig_glob(self, pattern))

    Path.glob = _glob_list  # type: ignore[assignment]

from outlook_web.app import create_app

__all__ = ["__version__", "create_app"]
