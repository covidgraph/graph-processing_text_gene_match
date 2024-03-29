import os
import sys
import logging
import py2neo
from time import sleep
import json

logging.basicConfig(level=logging.DEBUG)
logging.getLogger('py2neo.client.bolt').setLevel(logging.WARNING)
logging.getLogger('py2neo.client').setLevel(logging.WARNING)
logging.getLogger('graphio').setLevel(logging.WARNING)
logging.getLogger('neobolt').setLevel(logging.WARNING)

log = logging.getLogger(__name__)

NEO4J_CONFIG_STRING = os.getenv("NEO4J")

try:
    log.info(NEO4J_CONFIG_STRING)
    NEO4J_CONFIG_DICT = json.loads(NEO4J_CONFIG_STRING)
except json.decoder.JSONDecodeError:
    # try to replace single quotes with double quotes
    # JSON always expects double quotes, common mistake when writing JSON strings
    NEO4J_CONFIG_STRING = NEO4J_CONFIG_STRING.replace("'", '"')
    log.info(NEO4J_CONFIG_STRING)
    NEO4J_CONFIG_DICT = json.loads(NEO4J_CONFIG_STRING)

log.info(f'dict {NEO4J_CONFIG_DICT}')

RUN_MODE = os.getenv('RUN_MODE', 'prod')

FULLTEXT_INDEX_NAME = 'fragmentGeneSymbol'
CUSTOM_LUCENE_ANALYZER = 'synonym'

def get_lucene_analyzer_names(graph):
    """
    Return a list of Lucene analyzers available in DB.

    :param graph: py2neo.Graph instance
    :return: List of Lucene analyzer names
    """
    log.info("Get available Lucene analyzers")
    output = []
    for result_row in graph.run("call db.index.fulltext.listAvailableAnalyzers"):
        output.append(result_row["analyzer"])
    log.debug(output)
    return output


if __name__ == '__main__':
    log.info("Custom Lucene analyzer: {}".format(CUSTOM_LUCENE_ANALYZER))
    log.info("Fulltext index name: {}".format(FULLTEXT_INDEX_NAME))

    if RUN_MODE.lower() == 'test':
        log.info("There are no tests yet")
    else:
        graph = py2neo.Graph(**NEO4J_CONFIG_DICT)

        if CUSTOM_LUCENE_ANALYZER in get_lucene_analyzer_names(graph):

            query_create_fulltext_index = 'CALL db.index.fulltext.createNodeIndex("{0}", ["Fragment"], ["text"], {{analyzer: "{1}"}})'.format(
                FULLTEXT_INDEX_NAME, CUSTOM_LUCENE_ANALYZER)

            try:
                log.info("Create fulltext index, wait until ONLINE")
                graph.run(query_create_fulltext_index)
            except py2neo.ClientError:
                log.info("Error on index create, it likely exists already.")
                log.info("If the custom analyzer is not available the script will fail later")

            # wait until index is created
            index_populated = False
            while not index_populated:

                for row in graph.run("CALL db.indexes()"):
                    if 'indexName' in row.keys():
                        if row["indexName"] == FULLTEXT_INDEX_NAME:
                            log.debug("Index name found, result row: {}".format(row))
                            if row["state"] == 'ONLINE':
                                log.info("Index is populated")
                                index_populated = True
                                break
                    elif 'name' in row.keys():
                        if row["name"] == FULLTEXT_INDEX_NAME:
                            log.debug("Index name found, result row: {}".format(row))
                            if row["state"] == 'ONLINE':
                                log.info("Index is populated")
                                index_populated = True
                                break

                log.info("Wait 10 seconds and check for index again")
                sleep(10)

            # start creating data

            log.info("skip gene symbols with special characters in search")
            query_skip_special_char = """MATCH (gs:Gene {type: 'symbol'})
    WHERE gs.sid contains('(')
    OR gs.sid contains(')')
    OR gs.sid contains('/')
    OR gs.sid contains('*')
    OR gs.sid contains(' ')
    OR gs.sid contains('[')
    OR gs.sid contains(']')
    OR gs.sid contains(':')
    SET gs:OmitSpecialChar
    RETURN count(distinct gs)"""

            graph.run(query_skip_special_char)

            log.info("skip gene symbols of length 1")
            query_skip_length_one = """MATCH (gs:Gene {type: 'symbol'})
    WHERE size(gs.sid) = 1
    SET gs:OmitLength"""

            graph.run(query_skip_length_one)

            log.info("match gene symbols against word list to exclude symbols that are common words")

            query_skip_common_words = """MATCH (gs:Gene {type: 'symbol'}), (w:Word)
    WHERE toLower(gs.sid) = toLower(w.value)
    AND w.match11 = True
    SET gs:OmitWord"""

            graph.run(query_skip_common_words)

            log.info("match gene symbols against :Fragment fulltext index")
            query_match_genes_fragments = """CALL apoc.periodic.iterate(
        \"MATCH (gs:Gene {type: 'symbol'}) WHERE NOT gs:OmitWord AND NOT gs:OmitSpecialChar AND NOT gs:OmitLength RETURN gs\",
        \"CALL db.index.fulltext.queryNodes('fragmentGeneSymbol', gs.sid) YIELD node, score
        MERGE (gs)<-[r:MENTIONS]-(node) SET r.score = score\",
        {batchSize: 10, parallel: false, iterateList: true});"""

            graph.run(query_match_genes_fragments)

        else:
            log.debug("Custom Lucene analyzer not available!")
            sys.exit(1)
