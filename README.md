

# Queries to match :GeneSymbol - :Fragment

- name of fulltext index: `fragmentGeneSymbol`

## create index with custom analyzer on :Fragment nodes
- custom Lucene analyzer from Stefan Armbruster: https://github.com/covidgraph/neo4j-additional-analyzers
```cypher
CALL db.index.fulltext.createNodeIndex("fragmentGeneSymbol", ["Fragment"], ["text"], {analyzer: "synonym"});
```

## skip some GeneSymbols (with whitespace, slash or star)
- skip gene symbols with special characters in search
- set an additional label to filter them
```cypher
MATCH (gs:GeneSymbol)
WHERE gs.sid contains('(')
OR gs.sid contains(')')
OR gs.sid contains('/')
OR gs.sid contains('*')
OR gs.sid contains(' ')
OR gs.sid contains('[')
OR gs.sid contains(']')
OR gs.sid contains(':')
SET gs:OmitSpecialChar
RETURN count(distinct gs)
```

## skip gene symbols of length 1

```cypher
MATCH (gs:GeneSymbol)
WHERE size(gs.sid) = 1
SET gs:OmitLength
```

## skip gene symbols that are english words
- match gene symbols against word list to exclude symbols that are common words
- set an additional label to filter them

```cypher
MATCH (gs:GeneSymbol), (w:Word)
WHERE toLower(gs.sid) = toLower(w.value)
AND w.match11 = True
SET gs:OmitWord
```

## run the text match
- match gene symbols against `:Fragment` fulltext index
- use `MERGE` to be able to rerun the query

```cypher
CALL apoc.periodic.iterate(
    "MATCH (gs:GeneSymbol) WHERE NOT gs:OmitWord AND NOT gs:OmitSpecialChar AND NOT gs:OmitLength RETURN gs",
    "CALL db.index.fulltext.queryNodes('fragmentGeneSymbol', gs.sid) YIELD node, score
    MERGE (gs)<-[r:MENTIONS]-(node) SET r.score = score",
    {batchSize: 10, parallel: false, iterateList: true});
```

## count number of gene symbols with MENTIONS relationship

```cypher
MATCH (gs:GeneSymbol)<-[r:MENTIONS]-(:Fragment)
RETURN count(r)
```