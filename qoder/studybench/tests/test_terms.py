"""terms.py 单测：归一化 / 游程切词 / 2-gram / 停用词（契约 §4.1、§4.4）。"""

from __future__ import annotations

from studybench import terms


def test_nfkc_and_ascii_words() -> None:
    """NFKC 全角转半角；ASCII 词小写、长度 ≥ 2 保留。"""

    assert terms.tokenize("ＡＢＣ １２") == ["abc", "12"]
    assert terms.tokenize("Seekdb BM25") == ["seekdb", "bm25"]
    assert terms.tokenize("a I x") == []  # 长度 1 丢弃
    assert terms.tokenize("ab cd") == ["ab", "cd"]


def test_cjk_bigrams_and_single_char_run() -> None:
    assert terms.tokenize("完全二叉树") == ["完全", "全二", "二叉", "叉树"]
    assert terms.tokenize("树") == ["树"]  # 游程长度 1 → 单字
    assert terms.tokenize("的") == []  # 单字停用词被滤
    assert terms.tokenize("的数") == ["的数"]  # 2-gram 含停用字仍保留（契约 §4.1.5）


def test_separators_and_mixed() -> None:
    """空白、标点、全角符号、emoji 均为分隔；CJK 与 ASCII 词相邻分开。"""

    assert terms.tokenize("树,二叉树!🌲ab") == ["树", "二叉", "叉树", "ab"]
    assert terms.tokenize("") == []
    assert terms.tokenize("!!!。。。？？") == []


def test_dedupe_keeps_first_occurrence_order() -> None:
    assert terms.tokenize("树树 树树 树") == ["树树", "树"]
    # 原始序列 [二叉, 树, 二叉, 叉树]，重复的「二叉」只保留首次出现。
    assert terms.tokenize("二叉 树 二叉树") == ["二叉", "树", "叉树"]


def test_stopword_table_shape() -> None:
    """契约 §4.4：列表去重；只过滤整词项。"""

    assert len(terms.STOPWORDS) == len(terms.STOPWORD_SET)
    for word in ("的", "在", "这", "the", "an", "from"):
        assert word in terms.STOPWORD_SET
    assert terms.tokenize("the") == []
    assert terms.tokenize("theory") == ["theory"]  # 不是整词命中不过滤
    assert terms.tokenize("that is") == []  # ASCII 停用词


def test_tf_map_counts_occurrences() -> None:
    assert terms.tf_map("树树 树") == {"树树": 1, "树": 1}
    assert terms.tf_map("完全 完全二叉树") == {"完全": 2, "全二": 1, "二叉": 1, "叉树": 1}
    assert terms.tf_map("!!!") == {}
