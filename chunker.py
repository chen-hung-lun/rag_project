"""把長文字切成有重疊的小段，盡量切在句子結尾。

為什麼要切塊：
- 向量模型一次能讀的長度有限，整份文件轉成一個向量會把重點稀釋掉。
- 回答模型的上下文也有限，只能放進最相關的幾段。

切法（由大到小）：
1. 先用句號、問號、分號、換行切成句子。
2. 句子太長，改用逗號、頓號切。
3. 還是太長，才按字數硬切（滑動視窗）。
4. 把這些小單位依序裝進塊裡，裝滿 size 字就換下一塊。
5. 新的一塊開頭放上一塊結尾的幾句（overlap），避免答案剛好被切在兩塊中間。
"""
import re

# (?<=...) 是「後面接著」的位置，切開時標點會留在前一句，不會被丟掉
SENTENCE_END = re.compile(r"(?<=[。！？；!?;\n])")
PHRASE_END = re.compile(r"(?<=[，、,\s])")


def _sliding_window(text: str, size: int, overlap: int) -> list[str]:
    """最後手段：每 size 字切一段，相鄰兩段重疊 overlap 字。"""
    pieces = []
    step = size - overlap  # 每次往前移動的字數
    start = 0

    while start < len(text):
        end = start + size
        pieces.append(text[start:end])
        if end >= len(text):
            break
        start += step

    return pieces


def _split_units(text: str, size: int, overlap: int) -> list[str]:
    """先切成句子；太長的句子改切逗號；還是太長才按字數切。

    回傳的每個單位都不超過 size 字，之後再組合成塊。
    """
    units = []
    for sentence in SENTENCE_END.split(text):
        if len(sentence) <= size:
            units.append(sentence)
            continue
        for phrase in PHRASE_END.split(sentence):
            if len(phrase) <= size:
                units.append(phrase)
            else:
                units.extend(_sliding_window(phrase, size, overlap))
    # 去掉只有空白的單位
    return [unit for unit in units if unit.strip()]


def _overlap_tail(units: list[str], overlap: int) -> list[str]:
    """取上一塊結尾的完整句子當重疊，不把句子切開。

    從最後一句往前收，總長度超過 overlap 就停。
    """
    tail = []
    length = 0
    for unit in reversed(units):
        if length + len(unit) > overlap:
            break
        tail.insert(0, unit)
        length += len(unit)
    return tail


def chunk_text(text: str, size: int = 500, overlap: int = 100) -> list[str]:
    """把文字切成每塊最多 size 字、相鄰塊重疊約 overlap 字的清單。"""
    if size <= 0:
        raise ValueError("size 必須大於 0")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap 必須大於等於 0，且小於 size")

    chunks = []
    current: list[str] = []  # 目前這一塊已經裝進去的句子

    for unit in _split_units(text, size, overlap):
        # 再放這句就會超過上限：先把目前這塊存起來，開新的一塊
        if current and sum(map(len, current)) + len(unit) > size:
            chunks.append("".join(current).strip())
            current = _overlap_tail(current, overlap)
            # 重疊加新句子超過上限時，優先保留新句子，迴圈才一定會往前
            while current and sum(map(len, current)) + len(unit) > size:
                current.pop(0)
        current.append(unit)

    # 最後一塊還沒存
    if current:
        chunks.append("".join(current).strip())
    return chunks
