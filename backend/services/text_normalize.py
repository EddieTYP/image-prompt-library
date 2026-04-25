def to_traditional(text: str) -> str:
    try:
        from opencc import OpenCC
        return OpenCC("s2t").convert(text)
    except Exception:
        table = str.maketrans({"红":"紅","龙":"龍","图":"圖","画":"畫","风":"風","华":"華","汉":"漢","语":"語","体":"體","云":"雲","发":"發","后":"後"})
        return text.translate(table)
