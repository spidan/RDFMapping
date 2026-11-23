"""Fetch the Formex of an EU legal act from Cellar by its CELEX number.

Cellar returns the Formex of an act as a zip package (the act, annexes, a table
of contents and a manifest). The parts listed in the manifest are put together
into one COMBINED.FMX document, the same shape as a combined Formex file, so
that a mapping written for COMBINED.FMX works unchanged.
"""
import io
import os
import posixpath
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from lxml import etree

CELLAR_BASE = os.environ.get("CELLAR_BASE_URL", "https://publications.europa.eu/resource/celex/")
TIMEOUT_SECONDS = 60
MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_UNZIPPED_BYTES = 200 * 1024 * 1024
MAX_ENTRIES = 500

CELEX_RE = re.compile(r"^[0-9][0-9A-Z_-]{4,}(?:\([0-9A-Z]{1,4}\))?$")
LANG_RE = re.compile(r"^[A-Za-z]{3}$")


class CellarError(Exception):
    """An error that can be shown to the caller, with the HTTP status to use."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def check_celex(celex: str) -> str:
    celex = (celex or "").strip().upper()
    if not CELEX_RE.match(celex):
        raise CellarError(400, f"'{celex}' does not look like a CELEX number (example: 32016R0679)")
    return celex


def check_lang(lang: str) -> str:
    if not LANG_RE.match(lang or ""):
        raise CellarError(400, "lang must be a three-letter language code such as ENG or DEU")
    return lang.lower()


def _download(celex: str, lang: str) -> bytes:
    url = CELLAR_BASE + urllib.parse.quote(celex, safe="")
    req = urllib.request.Request(url, headers={
        "Accept": "application/zip;mtype=fmx4",
        "Accept-Language": lang,
        "User-Agent": "RDFMapping-service/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            status = resp.status
            data = resp.read(MAX_ZIP_BYTES + 1)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise CellarError(404, f"Cellar has no Formex for {celex} in language {lang.upper()}")
        if e.code == 300:
            raise CellarError(502, f"Cellar offers several representations for {celex} and did not pick one")
        raise CellarError(502, f"Cellar answered HTTP {e.code} for {celex}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise CellarError(502, f"Could not reach Cellar: {e}")
    if len(data) > MAX_ZIP_BYTES:
        raise CellarError(502, "The Formex package from Cellar is too large")
    if not data:
        raise CellarError(502, f"Cellar sent an empty answer (HTTP {status}); it may be asking for a browser check")
    return data


def _parser() -> etree.XMLParser:
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)


def _parse(xml_bytes: bytes, what: str) -> etree._Element:
    try:
        return etree.fromstring(xml_bytes, _parser())
    except etree.XMLSyntaxError as e:
        raise CellarError(502, f"{what} from Cellar is not valid XML: {e}")


def _combine(roots: list) -> bytes:
    combined = etree.Element("COMBINED.FMX")
    for root in roots:
        combined.append(root)
    return etree.tostring(combined, encoding="utf-8", xml_declaration=True)


def build_combined(data: bytes) -> bytes:
    """Turn what Cellar sent (a zip package, or plain Formex XML) into a COMBINED.FMX document."""
    if not data.startswith(b"PK"):
        root = _parse(data, "The document")
        if root.tag == "COMBINED.FMX":
            return data
        return _combine([root])

    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise CellarError(502, "Cellar did not send a valid zip package")
    with z:
        infos = [i for i in z.infolist() if not i.is_dir()]
        if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_UNZIPPED_BYTES:
            raise CellarError(502, "The Formex package from Cellar is too large")
        # entries are read from memory by name; nothing is written to disk
        files = {posixpath.basename(i.filename): i for i in infos
                 if i.filename.lower().endswith(".xml")}

        manifests = [n for n in files if n.lower().endswith((".doc.fmx.xml", ".doc.xml"))]
        ordered = []
        if manifests:
            manifest = _parse(z.read(files[sorted(manifests)[0]]), "The manifest")
            ordered = [el.get("FILE") for el in manifest.iter("REF.PHYS") if el.get("FILE")]
        if not ordered:
            ordered = sorted(n for n in files if ".toc" not in n.lower() and n not in manifests)

        roots = []
        for name in ordered:
            name = posixpath.basename(name)
            if name in files and ".toc" not in name.lower():
                roots.append(_parse(z.read(files[name]), name))
        if not roots:
            raise CellarError(502, "The Formex package from Cellar contains no document files")
        return _combine(roots)


def fetch_formex(celex: str, lang: str = "ENG") -> bytes:
    """Download the Formex of one act from Cellar and return it as a COMBINED.FMX document."""
    celex = check_celex(celex)
    lang = check_lang(lang)
    return build_combined(_download(celex, lang))
