"""`ankikit word` — 用語・単語の JSON を読んでカードにし、Anki まで一気に反映する。

    uv run ankikit word terms.json --deck sre

やることは 4 つ。**どれかで転んでも、通るものは通す**（重複 1 件で全部止まらない）。

    1. JSON を検証して例文を空欄化   （壊れた行だけ落として理由を出す。例文が無ければ問答カード）
    2. 単語をキーに重複を除外         （デッキに既にある語 / ファイル内の重複）
    3. decks/<slug>/cards/YYYY-MM-DD.md に追記してコミット
    4. Anki へ push

**用語には決まった答えがあるので、面談で問い詰める意味が無い。** だから承認（ブランチ →
main のマージ）は飛ばす。代わりに **main 上でしか push しない**ようにして
「Anki に入っているもの = main にあるもの」を保つ。掘って初めて出てくる実践判断のほうは
`/anki-grill` が承認つきで作る。

`ankikit eng` はこのコマンドの別名（既定デッキが `english-vocab`）。
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from .. import approval, config, connect, sync, vocab
from ..deck import Deck, find_deck, load_decks
from ..parser import Card, parse_text
from . import common

NAME = "word"
HELP = "用語・単語の JSON をカードにして Anki まで反映"

WORD_TAG_PREFIX = "word::"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", help="用語 JSON のパス")
    parser.add_argument("--deck", help="対象デッキの slug（省略時は JSON の \"deck\" → anki.toml の [word] deck）")
    parser.add_argument("--tag", action="append", default=[], help="全カードに付けるタグ（複数可）")
    parser.add_argument("--date", help="書き込み先のカードファイル名（既定は今日 YYYY-MM-DD）")
    parser.add_argument("--dry-run", action="store_true", help="検証だけして何も書かない")
    parser.add_argument("--strict", action="store_true", help="不備が 1 件でもあれば何も登録しない")
    parser.add_argument("--no-commit", action="store_true", help="ファイルを書くだけでコミットしない")
    parser.add_argument("--no-push", action="store_true", help="Anki へ反映しない")
    parser.add_argument("-v", "--verbose", action="store_true", help="登録するカードを 1 枚ずつ表示")
    # `ankikit eng` が最後の砦として渡してくる既定デッキ。`word` 単体では持たない。
    parser.set_defaults(fallback_deck=None)


def run(args: argparse.Namespace) -> int:
    try:
        loaded = vocab.load_file(Path(args.file))
    except vocab.VocabError as exc:
        common.error(str(exc))
        return 2

    deck = _resolve_deck(args, loaded)
    if deck is None:
        return 2

    cards, read_errors = deck.load_cards()
    for err in read_errors:
        common.error(str(err))
    if read_errors:
        common.error(f"{common.describe(deck)}: 既存カードが読めないので中断します（`uv run ankikit lint` で確認）")
        return 2

    entries, dup_issues = vocab.dedupe(loaded.entries, _known_words(cards))
    issues = [*loaded.issues, *dup_issues]
    _report_issues(issues)

    broken = sum(1 for i in issues if i.level == "error")
    skipped = sum(1 for i in issues if i.level == "skip")
    print(f"{common.describe(deck)}: 入力 {len(loaded.entries) + broken} 件 / 登録 {len(entries)} / 重複 {skipped} / 不備 {broken}")

    if args.strict and issues:
        common.error("--strict 指定のため何も登録しません")
        return 1
    exit_code = 1 if broken or skipped else 0

    if not entries:
        print("登録するカードがありません")
        return exit_code
    if args.verbose:
        for entry in entries:
            print(f"  + {entry.front[:60]}  → {entry.word}")

    target = _card_file(deck, args.date)
    text = _compose(target, entries, loaded.tags + args.tag, Path(args.file).name)
    if not _verify(text, target, cards, len(entries)):
        return 2

    if args.dry_run:
        print(f"[dry-run] {target} に {len(entries)} 枚追記して Anki へ反映します")
        return exit_code

    if not args.no_push and not _ready_to_push(deck, target, args):
        return 2

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    print(f"{target} に {len(entries)} 枚追記しました")

    if not args.no_commit and not _commit(target, deck, len(entries)):
        return 1
    if args.no_push:
        print("--no-push 指定のため Anki には反映していません（`uv run ankikit push --deck "
              f"{deck.slug}` で反映できます）")
        return exit_code
    return _push(deck, args) or exit_code


# --------------------------------------------------------------------------- 準備


def _resolve_deck(args: argparse.Namespace, loaded: vocab.Loaded) -> Deck | None:
    """--deck → JSON の "deck" → 別名コマンドの既定 → anki.toml の [word] deck、の順に決める。

    別名（`ankikit eng`）の既定を先に見るのは、`eng` と打った時点で english-vocab の意図が
    はっきりしているから。汎用の `[word] deck` にそれを横取りさせない。
    """
    slug = args.deck or loaded.deck or getattr(args, "fallback_deck", None) or config.word_default_deck()
    available = ", ".join(d.slug for d in load_decks()) or "(なし)"
    if not slug:
        common.error("どのデッキに入れるか決まりません。--deck <slug> を付けるか、JSON に \"deck\" を書いてください")
        common.error(f"（毎回同じデッキなら anki.toml に [word] deck = \"<slug>\"。利用可能: {available}）")
        return None

    deck = find_deck(slug)
    if deck is not None:
        return deck
    common.error(f"デッキ '{slug}' が見つかりません。利用可能: {available}")
    common.error(f"（作るなら `uv run ankikit new {slug}`）")
    return None


def _known_words(cards: list[Card]) -> set[str]:
    """デッキに既にある単語のキー。カードの `word::<key>` タグから拾う。"""
    return {
        tag[len(WORD_TAG_PREFIX) :]
        for card in cards
        for tag in card.tags
        if tag.startswith(WORD_TAG_PREFIX) and tag[len(WORD_TAG_PREFIX) :]
    }


def _card_file(deck: Deck, date: str | None) -> Path:
    if date:
        return deck.cards_dir / f"{date}.md"
    return deck.cards_dir / f"{dt.date.today().isoformat()}.md"


def _ready_to_push(deck: Deck, target: Path, args: argparse.Namespace) -> bool:
    """「Anki にあるもの = ref（既定 main）にあるもの」を守れる状態か。

    push は作業ツリーのデッキをまるごと送るので、**このデッキに未コミットの変更が残っていると
    それも一緒に Anki へ入る**。書き込む前にここで止める。自分がこれから書く target と
    --no-commit で置いていく分は対象外（それは承知の上の操作なので警告にとどめる）。
    """
    if not approval.is_repo():
        common.warn("git リポジトリではないので、そのまま書き込みます")
        return True

    branch = approval.current_branch()
    if branch != args.ref:
        common.error(
            f"今は '{branch}' にいます。Anki に入るのは '{args.ref}' の内容だけなので、"
            f"`git switch {args.ref}` してから実行するか、--no-push を付けてください"
        )
        return False

    if args.no_commit:
        common.warn("--no-commit なので、コミットしていないカードが Anki に入ります")
        return True

    others = [p for p in approval.dirty_paths(f"decks/{deck.slug}") if Path(p).name != target.name]
    if others:
        common.error(
            f"{deck.slug} に未コミットの変更があります: {', '.join(others)}"
            f"\n  push はデッキ全体を送るので、これも Anki に入ってしまいます。"
            f"先にコミットするか、--no-push を付けてください"
        )
        return False
    return True


# --------------------------------------------------------------------------- 書き込み


def _report_issues(issues: list[vocab.Issue]) -> None:
    for issue in issues:
        if issue.level == "error":
            common.error(str(issue))
        elif issue.level == "skip":
            print(f"重複: {issue}")
        else:
            common.warn(str(issue))


def _compose(target: Path, entries: list[vocab.Entry], tags: list[str], source: str) -> str:
    """既存ファイルに追記した後の中身を組み立てる。まだ書かない。"""
    block = vocab.render(entries, tags, source)
    if not target.exists():
        return block
    current = target.read_text(encoding="utf-8").rstrip("\n")
    return f"{current}\n\n{block}"


def _verify(text: str, target: Path, existing: list[Card], expected: int) -> bool:
    """**書く前に** parser へ通す。壊れた追記をファイルに残さないため。

    表面が既存カードと衝突すると lint が落ちて push できなくなるので、それもここで見る。
    """
    parsed = parse_text(text, target)
    for err in parsed.errors:
        common.error(str(err))
    if parsed.errors:
        common.error(f"{target} の書式チェックに落ちたので書き込みません")
        return False
    if len(parsed.cards) < expected:
        common.error(f"{expected} 枚のはずが {len(parsed.cards)} 枚しか読めません")
        return False

    elsewhere = {card.uid: card for card in existing if card.source != target}
    clashes = [c for c in parsed.cards if c.uid in elsewhere]
    for card in clashes:
        common.error(f"表面が {elsewhere[card.uid].location()} と重複します: {card.front[:40]}")
    if clashes:
        common.error(f"{target} に書き込みません（例文を変えるか、既存カードを消してください）")
        return False
    return True


def _commit(target: Path, deck: Deck, count: int) -> bool:
    if not approval.is_repo():
        return True
    try:
        relative = target.relative_to(config.REPO_ROOT).as_posix()
    except ValueError:
        relative = str(target)
    try:
        approval.git("add", "--", relative)
        approval.git("commit", "-m", f"cards({deck.slug}): {count}枚 (ankikit word)", "--", relative)
    except approval.GitError as exc:
        common.error(f"コミットに失敗しました: {exc}")
        common.error(f"（カードは {target} に書けています。手でコミットしてください）")
        return False
    print(f"コミットしました: {relative}")
    return True


def _push(deck: Deck, args: argparse.Namespace) -> int:
    try:
        report = sync.push_deck(deck)
    except connect.AnkiUnavailable as exc:
        common.error(str(exc))
        common.error(f"（カードは書けています。Anki を起動して `uv run ankikit push --deck {deck.slug}`）")
        return 2

    print(
        f"Anki へ反映: 追加 {report.count('added')} / 更新 {report.count('updated')}"
        f" / 変更なし {report.count('unchanged')} / 失敗 {report.count('failed')}"
    )
    failed = 0
    for result in report.results:
        if result.action == "failed":
            common.error(f"失敗 {result.card.front[:40]}: {result.detail}")
            failed += 1
    return 1 if failed else 0
