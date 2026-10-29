"""分词 / 2-gram / 停用词（qoder/CONTRACTS.md §4.1、§4.4）。

规则（Python 与 JS 站点侧逐条一致，是 parity 测试的依据）：

1. ``unicodedata.normalize("NFKC", text)``（JS: ``s.normalize("NFKC")``）。
2. 按字符游程切词：CJK 游程 = CJK 扩展 A 区（U+3400-U+4DBF）与基本区
   （U+4E00-U+9FFF）的连续字符；ASCII 词 = ``[A-Za-z0-9]`` 连续；其余字符
   （空白、标点、全角符号、emoji）一律为分隔。
3. ASCII 词：小写后取长度 ≥ 2 的词，长度 1 丢弃；**长度 > 48 的整串丢弃**
   （真实笔记里会出现 data URI / base64 / 长哈希，如 439 字符的 ``phn2zy...``，
   属噪声且会撑爆 ``chunk_terms.term``；JS 侧同一规则）。
4. CJK 游程：取全部相邻 2-gram；游程长度为 1 时取该单字。
5. 过滤停用词：只过滤整词项；2-gram 即使含停用字也保留（如「的数」）。
6. :func:`tokenize` 返回按首次出现顺序去重的词项；:func:`tf_map` 返回词频。
"""

from __future__ import annotations

import unicodedata

# 契约 §4.4 停用词（按原列表顺序去重；重复项是契约刻意提醒）。
_STOPWORD_SOURCE: tuple[str, ...] = (
    "的", "了", "是", "在", "和", "与", "对", "用", "为", "及", "或", "等", "就",
    "都", "也", "要", "会", "能", "把", "被", "从", "而", "其", "之", "个", "中",
    "上", "下", "不", "有", "我", "你", "他", "这", "那", "有", "所", "以",
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are",
    "was", "were", "be", "been", "it", "this", "that", "with", "as", "at", "by",
    "from",
)

#: 去重后保持首现顺序的停用词表（导出 meta.stopwords 用此顺序）。
STOPWORDS: tuple[str, ...] = tuple(dict.fromkeys(_STOPWORD_SOURCE))

#: 停用词集合（只过滤整词项）。
STOPWORD_SET: frozenset[str] = frozenset(STOPWORDS)

#: 超长 ASCII 串上限：更长的整串视为 data URI / base64 / 哈希噪声，直接丢弃。
MAX_ASCII_TERM: int = 48

#: CJK 游程边界（U+3400-U+4DBF 与 U+4E00-U+9FFF，用 chr() 避免源码编码歧义）。
_CJK_LOW_1 = chr(0x3400)
_CJK_HIGH_1 = chr(0x4DBF)
_CJK_LOW_2 = chr(0x4E00)
_CJK_HIGH_2 = chr(0x9FFF)


def _is_cjk(char: str) -> bool:
    """CJK 统一表意文字游程判定（契约 §4.1）。"""

    return _CJK_LOW_1 <= char <= _CJK_HIGH_1 or _CJK_LOW_2 <= char <= _CJK_HIGH_2


def _is_ascii_alnum(char: str) -> bool:
    return "a" <= char <= "z" or "A" <= char <= "Z" or "0" <= char <= "9"


def _raw_terms(text: str) -> list[str]:
    """NFKC 归一化后按游程切词；结果含重复、未滤停用词。"""

    normalized = unicodedata.normalize("NFKC", text)
    terms: list[str] = []
    index = 0
    length = len(normalized)
    while index < length:
        char = normalized[index]
        if _is_cjk(char):
            start = index
            index += 1
            while index < length and _is_cjk(normalized[index]):
                index += 1
            run = normalized[start:index]
            if len(run) == 1:
                terms.append(run)
            else:
                terms.extend(run[i : i + 2] for i in range(len(run) - 1))
        elif _is_ascii_alnum(char):
            start = index
            index += 1
            while index < length and _is_ascii_alnum(normalized[index]):
                index += 1
            word = normalized[start:index].lower()
            if 2 <= len(word) <= MAX_ASCII_TERM:
                terms.append(word)
        else:
            index += 1
    return terms


def _filtered_terms(text: str) -> list[str]:
    return [term for term in _raw_terms(text) if term not in STOPWORD_SET]


def tokenize(text: str) -> list[str]:
    """归一化 + 切词 + 滤停用词 + 按首次出现顺序去重（契约 §4.1）。"""

    seen: set[str] = set()
    unique: list[str] = []
    for term in _filtered_terms(text):
        if term not in seen:
            seen.add(term)
            unique.append(term)
    return unique


def tf_map(text: str) -> dict[str, int]:
    """同一套分词的词频统计（含重复次数，契约 §4.1）。"""

    counts: dict[str, int] = {}
    for term in _filtered_terms(text):
        counts[term] = counts.get(term, 0) + 1
    return counts
