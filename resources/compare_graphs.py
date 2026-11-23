"""Compare two Turtle files as RDF graphs: python compare_graphs.py a.ttl b.ttl"""
import sys
from rdflib import Graph
from rdflib.compare import isomorphic, to_isomorphic, graph_diff

a = Graph().parse(sys.argv[1], format="turtle")
b = Graph().parse(sys.argv[2], format="turtle")
print(f"{sys.argv[1]}: {len(a)} triples")
print(f"{sys.argv[2]}: {len(b)} triples")
print("same graph:", isomorphic(a, b))
both, only_a, only_b = graph_diff(to_isomorphic(a), to_isomorphic(b))
print(f"in both: {len(both)}   only in first: {len(only_a)}   only in second: {len(only_b)}")
for t in list(only_a)[:10]:
    print("  only first :", tuple(str(x)[:80] for x in t))
for t in list(only_b)[:10]:
    print("  only second:", tuple(str(x)[:80] for x in t))
