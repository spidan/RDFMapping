"""Optional pre-processing for Formex before RML mapping.

- drops footnotes (NOTE) so they do not leak into running text
- inserts a space after block-level elements so words do not get glued together
- adds N="<digits>" to recitals (CONSID) so they get clean URIs
  (recital_1 instead of recital_%281%29)

Usage (command line):  python clean_formex.py input.xml > cleaned.xml
Usage (as a module):   from app.clean_formex import clean;  cleaned_bytes = clean(xml_bytes)
"""
import re
import sys

from lxml import etree

BLOCK = {"P", "TXT", "ALINEA", "NP", "ITEM", "NO.P", "NO.PARAG", "TI.ART", "STI.ART",
         "TI", "STI", "LIST", "PARAG", "ARTICLE", "TITLE", "CONSID", "VISA", "TI.CJT", "NO.CJT"}


def clean(xml_bytes: bytes) -> bytes:
    root = etree.fromstring(xml_bytes)

    # 1) remove footnotes, keeping the text that follows them
    for note in list(root.iter("NOTE")):
        parent, tail = note.getparent(), note.tail
        prev = note.getprevious()
        if tail:
            if prev is not None:
                prev.tail = (prev.tail or "") + tail
            else:
                parent.text = (parent.text or "") + tail
        parent.remove(note)

    # 2) separate block-level elements with a space
    for el in root.iter():
        if isinstance(el.tag, str) and el.tag in BLOCK:
            el.tail = (el.tail or "") + " "

    # 3) clean recital numbers for URIs
    for c in root.iter("CONSID"):
        no = c.find("NP/NO.P")
        if no is not None:
            m = re.search(r"\d+", "".join(no.itertext()))
            if m:
                c.set("N", m.group(0))

    return etree.tostring(root, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    sys.stdout.buffer.write(clean(open(sys.argv[1], "rb").read()))
