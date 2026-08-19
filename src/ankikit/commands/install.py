"""`ankikit install` — カード側のリポジトリにスキルを配る。

ankikit を `uv add` で入れると、コマンドは使えるがスキル（`/anki-grill` /
`/anki-initialize`）が付いてこない。スキルはパッケージに同梱してあるので、
それをカード側の `.claude/skills/` に展開するのがこのコマンド。

    uv run ankikit install            # 入れる／更新する
    uv run ankikit install --list     # 何が入るかだけ見る
    uv run ankikit install --force    # 手で直したものも上書きする

いまは Claude Code（`.claude/skills/`）だけ。他のエージェントを足すときは
AGENTS に 1 行足す。
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from .. import config
from . import common

NAME = "install"
HELP = "スキルをこのリポジトリに配置（/anki-grill, /anki-initialize）"
# decks/ がまだ無いリポジトリでも使う（むしろ最初に叩くコマンド）。
NEEDS_DECKS = False


@dataclass(frozen=True)
class Agent:
    """スキルの置き場が分かればいいので、名前と相対パスだけ持つ。"""

    name: str
    skills_dir: str


AGENTS = {
    "claude-code": Agent(name="claude-code", skills_dir=".claude/skills"),
}
DEFAULT_AGENT = "claude-code"


def bundled_skills() -> list[str]:
    """パッケージに同梱されているスキル名。"""
    root = resources.files("ankikit") / "skills"
    return sorted(entry.name for entry in root.iterdir() if (entry / "SKILL.md").is_file())


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--agent",
        default=DEFAULT_AGENT,
        choices=sorted(AGENTS),
        help=f"配置先のエージェント（既定 {DEFAULT_AGENT}）",
    )
    parser.add_argument(
        "--target",
        type=Path,
        help="配置先のリポジトリ（既定はカードの置き場）",
    )
    parser.add_argument("--list", action="store_true", help="配置せず、入るものだけ表示")
    parser.add_argument("--force", action="store_true", help="手で変更したスキルも上書きする")


def run(args: argparse.Namespace) -> int:
    agent = AGENTS[args.agent]
    skills = bundled_skills()

    if args.list:
        print(f"同梱スキル（{args.agent} → {agent.skills_dir}/）:")
        for name in skills:
            print(f"  {name}")
        return 0

    target = (args.target or config.REPO_ROOT).expanduser().resolve()
    if not target.is_dir():
        common.error(f"{target} がありません")
        return 1

    dest_root = target / agent.skills_dir
    source_root = resources.files("ankikit") / "skills"

    installed, updated, skipped = [], [], []
    for name in skills:
        source = Path(str(source_root / name / "SKILL.md"))
        dest = dest_root / name / "SKILL.md"

        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            installed.append(name)
        elif filecmp.cmp(source, dest, shallow=False):
            skipped.append(name)  # 既に同じ内容
        elif args.force:
            shutil.copyfile(source, dest)
            updated.append(name)
        else:
            skipped.append(f"{name}（内容が違う。上書きするなら --force）")

    print(f"配置先: {dest_root}")
    for label, names in (("追加", installed), ("更新", updated), ("そのまま", skipped)):
        if names:
            print(f"  {label} {len(names)}: {', '.join(names)}")

    if installed or updated:
        print("Claude Code を開き直すと /anki-grill と /anki-initialize が使えます。")
    return 0
