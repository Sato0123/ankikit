"""`ankikit word` — 用語・単語の JSON を読んでカードにし、Anki まで一気に反映する。

    uv run ankikit word terms.json --deck sre

やることは 4 つ。**どれかで転んでも、通るものは通す**（重複 1 件で全部止まらない）。

    1. JSON を検証して例文を空欄化   （壊れた行だけ落として理由を出す。例文が無ければ問答カード）
    2. 単語をキーに重複を除外         （デッキに既にある語 / ファイル内の重複）
    3. decks/<slug>/cards/YYYY-MM-DD.md に追記してコミット（**デッキが無ければ作る**）
    4. **今書いた分だけ** Anki へ push

**用語には決まった答えがあるので、面談で問い詰める意味が無い。** だから承認（ブランチ →
main のマージ）は飛ばす。ブランチも作業ツリーの汚れも見ないので、叩けばそのまま入る。
それでも「承認していないカードが混ざる」ことが起きないのは、**push するのがデッキ全体ではなく
今書いた枚数だけ**だから。掘って初めて出てくる実践判断のほうは `/anki-grill` が承認つきで作る。

`ankikit eng` はこのコマンドの別名（既定デッキが `english-vocab`）。
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from .. import approval, config, connect, sync, vocab
from ..deck import Deck, find_deck, load_decks
from ..parser import Card, parse_text
from . import common, new

NAME = "word"
HELP = "用語・単語の JSON をカードにして Anki まで反映"

WORD_TAG_PREFIX = "word::"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", help="用語 JSON のパス")
    parser.add_argument("--deck", help="対象デッキの slug（無ければ作る。`.` 区切りでサブデッキ。省略時は JSON の \"deck\" → anki.toml の [word] deck）")
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

    resolved = _resolve_deck(args, loaded)
    if resolved is None:
        return 2
    deck, created = resolved

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
    block = vocab.render(entries, loaded.tags + args.tag, Path(args.file).name)
    text = _compose(target, block)
    if not _verify(text, target, cards, len(entries)):
        return 2

    if args.dry_run:
        print(f"[dry-run] {target} に {len(entries)} 枚追記して Anki へ反映します")
        return exit_code

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    print(f"{target} に {len(entries)} 枚追記しました")

    written = [target, *([deck.readme] if created else [])]
    if not args.no_commit and not _commit(written, deck, len(entries)):
        return 1
    if args.no_push:
        print("--no-push 指定のため Anki には反映していません（`uv run ankikit push --deck "
              f"{deck.slug}` で反映できます）")
        return exit_code
    return _push(deck, _added_cards(deck, block, target)) or exit_code


# --------------------------------------------------------------------------- 準備


def _resolve_deck(args: argparse.Namespace, loaded: vocab.Loaded) -> tuple[Deck, bool] | None:
    """--deck → JSON の "deck" → 別名コマンドの既定 → anki.toml の [word] deck、の順に決める。

    別名（`ankikit eng`）の既定を先に見るのは、`eng` と打った時点で english-vocab の意図が
    はっきりしているから。汎用の `[word] deck` にそれを横取りさせない。

    **決まった slug のデッキが無ければその場で作る。** 単語を入れたいだけなのに
    `ankikit new` を挟ませる理由が無い。`english.duo` のように `.` で区切れば
    Anki 側は `english::duo` のサブデッキになる。戻り値の 2 つ目が「今作った」かどうか
    （作ったなら README も一緒にコミットする）。
    """
    slug = args.deck or loaded.deck or getattr(args, "fallback_deck", None) or config.word_default_deck()
    if not slug:
        common.error("どのデッキに入れるか決まりません。--deck <slug> を付けるか、JSON に \"deck\" を書いてください")
        common.error(f"（毎回同じデッキなら anki.toml に [word] deck = \"<slug>\"。利用可能: {_available()}）")
        return None

    deck = find_deck(slug)
    if deck is not None:
        return deck, False

    # ここから先は「無いので作る」。`english::duo` と書かれてもディレクトリ名は `.` に寄せる。
    normalized = new.normalize_slug(slug)
    if normalized != slug:
        deck = find_deck(normalized)
        if deck is not None:
            return deck, False
        slug = normalized

    problem = new.slug_problem(slug)
    if problem:
        common.error(problem)
        return None

    anki_deck = new.anki_deck_name(slug)
    if args.dry_run:
        print(f"[dry-run] デッキ '{slug}' はまだ無いので作ります（Anki 上: {anki_deck}）")
        return Deck(slug=slug, path=config.DECKS_DIR / slug, anki_deck=anki_deck), True

    new.create(slug)
    print(f"デッキ '{slug}' が無かったので作りました: {config.DECKS_DIR / slug}/README.md"
          f"（Anki 上のデッキ名: {anki_deck}）")
    created = find_deck(slug)
    if created is None:  # 作った直後に見つからないのは異常。黙って別の場所へ入れない。
        common.error(f"デッキ '{slug}' を作りましたが読み込めません")
        return None
    return created, True


def _available() -> str:
    """エラー文に添えるデッキ一覧。**転んだときにしか呼ばない**（成功パスで走査したくない）。"""
    return ", ".join(d.slug for d in load_decks()) or "(なし)"


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


# --------------------------------------------------------------------------- 書き込み


def _report_issues(issues: list[vocab.Issue]) -> None:
    """不備を出す。**同じ code の警告はまとめて 1 行**（語の一覧だけ添える）。

    自由記述の欄で普通に起きることを行数分並べると、本当に見てほしいエラーが流れる。
    """
    grouped: dict[str, list[vocab.Issue]] = {}
    for issue in issues:
        if issue.level == "error":
            common.error(str(issue))
        elif issue.level == "skip":
            print(f"重複: {issue}")
        elif issue.code:
            grouped.setdefault(issue.code, []).append(issue)
        else:
            common.warn(str(issue))

    for code, group in grouped.items():
        words = [i.word for i in group if i.word]
        shown = ", ".join(words[:8]) + (f" ほか {len(words) - 8} 件" if len(words) > 8 else "")
        common.warn(f"{len(group)} 件: {vocab.ISSUE_SUMMARIES.get(code, code)}: {shown}")


def _compose(target: Path, block: str) -> str:
    """既存ファイルに追記した後の中身を組み立てる。まだ書かない。"""
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


def _added_cards(deck: Deck, block: str, target: Path) -> list[Card]:
    """今書いた分のカードだけを、デッキのタグまで乗った状態で取り出す。

    **push に渡すのはこれだけ。** デッキ全体を送らないので、承認前のカードが
    同じブランチに置いてあっても Anki には流れない。
    """
    fresh = {card.uid for card in parse_text(block, target).cards}
    cards, _ = deck.load_cards()
    return [card for card in cards if card.uid in fresh]


def _commit(paths: list[Path], deck: Deck, count: int) -> bool:
    if not approval.is_repo():
        return True
    relative = []
    for path in paths:
        try:
            relative.append(path.relative_to(config.REPO_ROOT).as_posix())
        except ValueError:
            relative.append(str(path))
    try:
        approval.git("add", "--", *relative)
        approval.git("commit", "-m", f"cards({deck.slug}): {count}枚 (ankikit word)", "--", *relative)
    except approval.GitError as exc:
        common.error(f"コミットに失敗しました: {exc}")
        common.error(f"（カードは {paths[0]} に書けています。手でコミットしてください）")
        return False
    print(f"コミットしました: {', '.join(relative)}")
    return True


def _push(deck: Deck, cards: list[Card]) -> int:
    try:
        report = sync.push_deck(deck, cards=cards)
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
