"""A small persistent graph store.

All graphs live in one rdflib Dataset (one named graph per IRI, for example
one per CELEX number). Every graph is also saved as a Turtle file in
GRAPH_DIR, so the data survives a restart. Mount that folder as a Docker
volume to keep it.
"""
import logging
import os
import pathlib
import re
import threading
from urllib.parse import quote, unquote

from rdflib import Dataset, Graph, URIRef

log = logging.getLogger("store")

GRAPH_DIR = pathlib.Path(os.environ.get("GRAPH_DIR", "data/graphs"))
IRI_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:[^\s<>\"{}|\\^`]+$")

# One lock for everything: the graphs are small and rdflib is not safe
# to read while another thread changes it.
lock = threading.RLock()

# default_union=True: a query without GRAPH sees the triples of all graphs
dataset = Dataset(default_union=True)


class StoreError(Exception):
    pass


def _file_for(iri: str) -> pathlib.Path:
    return GRAPH_DIR / (quote(iri, safe="") + ".ttl")


def check_iri(iri: str) -> str:
    if not IRI_RE.match(iri or "") or len(quote(iri, safe="")) > 200:
        raise StoreError(f"Not a usable graph IRI: {iri!r}")
    return iri


def load_all() -> int:
    """Read every saved graph into memory (called at startup)."""
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    with lock:
        for f in sorted(GRAPH_DIR.glob("*.ttl")):
            iri = unquote(f.stem)
            try:
                dataset.graph(URIRef(iri)).parse(str(f), format="turtle")
                count += 1
            except Exception as e:  # a broken file must not stop the service
                log.warning("Skipping %s: %s", f.name, e)
    return count


def put_graph(iri: str, data: str, fmt: str = "turtle") -> int:
    """Create or replace a named graph. Returns the number of triples."""
    check_iri(iri)
    tmp = Graph()
    try:
        tmp.parse(data=data, format=fmt)
    except Exception as e:
        raise StoreError(f"Could not parse the data as {fmt}: {e}")
    with lock:
        g = dataset.graph(URIRef(iri))
        g.remove((None, None, None))
        g += tmp
        GRAPH_DIR.mkdir(parents=True, exist_ok=True)
        path = _file_for(iri)
        part = path.with_suffix(".part")
        tmp.serialize(destination=str(part), format="turtle")
        os.replace(part, path)
    return len(tmp)


def delete_graph(iri: str) -> bool:
    check_iri(iri)
    with lock:
        uri = URIRef(iri)
        if uri not in {g.identifier for g in dataset.graphs()}:
            return False
        dataset.remove_graph(dataset.graph(uri))
        try:
            _file_for(iri).unlink()
        except FileNotFoundError:
            pass
        return True


def list_graphs() -> list:
    with lock:
        return [{"graph": str(g.identifier), "triples": len(g)}
                for g in dataset.graphs() if len(g)]


def view(default_graphs: list):
    """What a query runs on: all graphs together, or only the chosen ones."""
    if not default_graphs:
        return dataset
    g = Graph()
    for iri in default_graphs:
        g += dataset.graph(URIRef(iri))
    return g
