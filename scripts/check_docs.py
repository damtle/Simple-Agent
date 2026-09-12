"""检查书稿的本地链接、代码围栏和带编号的标题层级；不访问网络。"""

from pathlib import Path
import re
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]


def check_file(path: Path) -> list[str]:
    errors = []
    fence = None
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        prefix = f"{path.relative_to(ROOT)}:{number}"
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker[1]
            if fence is None:
                fence = (token[0], len(token), number)
            elif token[0] == fence[0] and len(token) >= fence[1]:
                fence = None
            continue
        if fence:
            continue
        heading = re.match(r"^(#{2,6})\s+(\d+(?:\.\d+)+)\s", line)
        if heading and len(heading[1]) != len(heading[2].split(".")):
            errors.append(f"{prefix}: 标题编号与层级不一致")
        for target in re.findall(r"\]\(([^\s)]+)", line):
            if ":" in target or target.startswith("#"):
                continue
            target = unquote(target.split("#")[0])
            if not target:
                continue
            base = ROOT / "docs" if target.startswith("/") else path.parent
            resolved = base / target.lstrip("/")
            if not resolved.exists():
                errors.append(f"{prefix}: 本地链接不存在：{target}")
    if fence:
        errors.append(f"{path.relative_to(ROOT)}:{fence[2]}: 代码围栏未闭合")
    return errors


def main() -> int:
    files = sorted((ROOT / "docs").rglob("*.md"))
    files += sorted((ROOT / "code").glob("chapter*/README.md"))
    files += sorted((ROOT / "examples").glob("*/README.md"))
    files += [ROOT / "README.md", ROOT / "CONTRIBUTING.md"]
    errors = [error for path in files for error in check_file(path)]
    if errors:
        print("\n".join(errors))
        return 1
    print(f"文档检查通过：{len(files)} 个文件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
