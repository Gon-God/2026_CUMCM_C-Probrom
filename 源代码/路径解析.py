"""附件目录定位（四个问题脚本共用）。

原先每个脚本各自硬编码 ``ROOT / '附件'`` 或 ``ROOT.parent / '附件'``，与
支撑材料实际目录结构不符，脚本无法独立运行。这里统一为：

1. 依次在若干候选目录下寻找 ``附件1.xlsx``；
2. 取第一个命中的目录作为附件目录；
3. 全部落空时抛出带排查指引的 ``FileNotFoundError``。

候选顺序（全部为相对路径，``SRC`` = 本文件所在目录，即 源代码/）：

    $MATHMODEL_ATT      环境变量（可选），换机器临时指定时用
    SRC/附件            附件与代码同目录（子目录分发时用）
    SRC/../附件         附件与 源代码/ 平级（本支撑材料的实际布局）
    SRC/../*/附件       上层目录下任意一层 附件/（如 26年国赛/C题/附件）
    CWD/附件            从项目根目录直接运行脚本时的当前工作目录

由于基准是 ``Path(__file__)`` 而非当前工作目录，且不出现任何盘符或绝对路径，
整个文件夹拷到别的机器、别的盘解压后，从任何位置启动结果都一致。
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ['SRC', 'find_att', 'ATT', 'REPORTS', 'FIGDIR', 'ensure_dir']

SRC = Path(__file__).resolve().parent

PROBE = '附件1.xlsx'


def _candidates() -> list[Path]:
    cands: list[Path] = []

    env = os.environ.get('MATHMODEL_ATT')
    if env:
        cands.append(Path(env).expanduser())

    cands.append(SRC / '附件')
    cands.append(SRC.parent / '附件')
    try:
        cands.extend(sorted(p for p in SRC.parent.glob('*/附件') if p.is_dir()))
    except OSError:
        pass
    cands.append(Path.cwd() / '附件')
    return cands


def find_att(probe: str = PROBE) -> Path:
    """返回包含 ``probe``（默认附件1.xlsx）的附件目录。"""
    tried: list[Path] = []
    seen: set[Path] = set()
    for c in _candidates():
        if c in seen:
            continue
        seen.add(c)
        tried.append(c)
        if (c / probe).is_file():
            return c.resolve()
    msg = [
        f'找不到附件目录（缺少 {probe}）。已尝试以下位置：',
        *[f'  - {t}' for t in tried],
        '解决办法（任选其一）：',
        f'  1. 把 附件1~4.xlsx 放到 {SRC / "附件"}；',
        '  2. 设置环境变量 MATHMODEL_ATT 指向附件所在目录，例如：',
        r'     set MATHMODEL_ATT=C:\path\to\附件',
    ]
    raise FileNotFoundError('\n'.join(msg))


ATT = find_att()

#: 各脚本共用的输出目录（相对 源代码/，避免依赖当前工作目录）
REPORTS = SRC / 'reports'
FIGDIR = SRC / 'figures'


def ensure_dir(p: Path) -> Path:
    """建目录并返回，便于 ``p = ensure_dir(x)`` 链式使用。"""
    Path(p).mkdir(parents=True, exist_ok=True)
    return Path(p)
