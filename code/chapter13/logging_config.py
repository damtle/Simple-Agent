"""第十三章：由程序入口统一配置 Python logging。"""

import logging


def configure_logging(
    level: str = "INFO",
) -> None:
    """配置根 logger，不让日志级别影响程序行为。"""
    if not isinstance(level, str) or not level.strip():
        raise ValueError("日志级别不能为空。")

    numeric_level = getattr(
        logging,
        level.strip().upper(),
        None,
    )

    if not isinstance(numeric_level, int):
        raise ValueError(
            f"未知日志级别：{level!r}。"
        )

    logging.basicConfig(
        level=numeric_level,
        format=(
            "%(asctime)s "
            "%(levelname)s "
            "%(name)s "
            "%(message)s"
        ),
        force=True,
    )
