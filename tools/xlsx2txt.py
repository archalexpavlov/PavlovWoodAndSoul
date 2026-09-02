#!/usr/bin/env python3
"""
xlsx -> текст, построчно по ячейкам. Нужен git-у как textconv,
чтобы `git diff` на .xlsx показывал изменения по ячейкам, а не
"Binary files differ".

Формат строки:   Лист!A1<TAB>значение
Переводы строк внутри ячейки заменяются на \n, поэтому одна
изменённая ячейка = одна изменённая строка в диффе.

Только стандартная библиотека — работает на любой машине с python.
Подключается так (из корня репозитория):
    git config diff.xlsx.textconv "python tools/xlsx2txt.py"
    git config diff.xlsx.cachetextconv true
"""
import io
import sys
import zipfile
import datetime
from xml.etree import ElementTree as ET

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
PKGREL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
DOCREL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

# номера встроенных форматов, которые Excel считает датой/временем
BUILTIN_DATE_FMTS = set(range(14, 23)) | set(range(45, 48)) | {27, 30, 36, 50, 57}


def cell_text(node):
    """Собрать текст из <si> или <is> с учётом rich text (несколько <t>)."""
    return "".join(t.text or "" for t in node.iter(MAIN + "t"))


def load_shared_strings(z):
    try:
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return [cell_text(si) for si in root.findall(MAIN + "si")]


def load_date_styles(z):
    """Индексы стилей (s="N"), у которых числовой формат — дата."""
    try:
        root = ET.fromstring(z.read("xl/styles.xml"))
    except KeyError:
        return set()

    custom_date = set()
    for fmt in root.iter(MAIN + "numFmt"):
        code = (fmt.get("formatCode") or "").lower()
        stripped = code.split(";")[0]
        if any(ch in stripped for ch in ("y", "d", "h", "s")) and "\\" not in stripped:
            custom_date.add(int(fmt.get("numFmtId")))

    date_styles = set()
    cell_xfs = root.find(MAIN + "cellXfs")
    if cell_xfs is None:
        return date_styles
    for idx, xf in enumerate(cell_xfs.findall(MAIN + "xf")):
        num_fmt = int(xf.get("numFmtId") or 0)
        if num_fmt in BUILTIN_DATE_FMTS or num_fmt in custom_date:
            date_styles.add(idx)
    return date_styles


def serial_to_date(value, date1904):
    """Excel-серийный номер -> ISO-строка."""
    base = datetime.datetime(1904, 1, 1) if date1904 else datetime.datetime(1899, 12, 30)
    try:
        dt = base + datetime.timedelta(days=float(value))
    except (ValueError, OverflowError):
        return value
    if dt.time() == datetime.time(0, 0):
        return dt.strftime("%Y-%m-%d")
    return dt.strftime("%Y-%m-%d %H:%M")


def sheet_list(z):
    """[(имя листа, путь к xml)] в порядке вкладок."""
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    date1904 = False
    pr = wb.find(MAIN + "workbookPr")
    if pr is not None and pr.get("date1904") in ("1", "true"):
        date1904 = True

    rels = {}
    try:
        rel_root = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        for rel in rel_root.findall(PKGREL + "Relationship"):
            target = rel.get("Target")
            if target.startswith("/"):
                target = target.lstrip("/")
            elif not target.startswith("xl/"):
                target = "xl/" + target
            rels[rel.get("Id")] = target
    except KeyError:
        pass

    sheets = []
    for i, sh in enumerate(wb.iter(MAIN + "sheet"), 1):
        rid = sh.get(DOCREL + "id")
        path = rels.get(rid) or "xl/worksheets/sheet%d.xml" % i
        if path not in z.namelist():
            path = "xl/worksheets/sheet%d.xml" % i
        sheets.append((sh.get("name") or "Sheet%d" % i, path))
    return sheets, date1904


def dump(path, out):
    with zipfile.ZipFile(path) as z:
        shared = load_shared_strings(z)
        date_styles = load_date_styles(z)
        sheets, date1904 = sheet_list(z)

        for name, xml_path in sheets:
            out.write("### %s\n" % name)
            try:
                ws = ET.fromstring(z.read(xml_path))
            except KeyError:
                out.write("(лист не прочитан: %s)\n" % xml_path)
                continue

            for c in ws.iter(MAIN + "c"):
                ref = c.get("r") or "?"
                ctype = c.get("t")
                formula = c.find(MAIN + "f")
                v = c.find(MAIN + "v")

                if ctype == "inlineStr":
                    text = cell_text(c)
                elif ctype == "s":
                    idx = int(v.text) if v is not None and v.text else -1
                    text = shared[idx] if 0 <= idx < len(shared) else ""
                elif ctype == "b":
                    text = "TRUE" if (v is not None and v.text == "1") else "FALSE"
                elif v is not None:
                    text = v.text or ""
                    style = c.get("s")
                    if style is not None and int(style) in date_styles:
                        text = serial_to_date(text, date1904)
                else:
                    text = ""

                if formula is not None and formula.text:
                    text = "=%s  ->  %s" % (formula.text, text)

                if text.strip():
                    flat = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
                    out.write("%s!%s\t%s\n" % (name, ref, flat))
            out.write("\n")


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("usage: xlsx2txt.py <file.xlsx>\n")
        return 2
    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")
    try:
        dump(sys.argv[1], out)
    except Exception as exc:                      # git не должен падать из-за диффа
        out.write("(не удалось прочитать xlsx: %s)\n" % exc)
    try:                                          # приёмник мог закрыть канал раньше (head, less)
        out.flush()
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
