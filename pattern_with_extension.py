#!/usr/bin/env python3
import plyvel
import rlp
import sys
from collections import defaultdict

BRANCH = 0
BRANCH_WITH_VALUE = 0
BRANCH_COUNT = defaultdict(lambda: 0)
BRANCH_DEPTH = defaultdict(lambda: 0)
FIRST_NON_NULL_BRANCH_NODE = defaultdict(lambda: 0)
LAST_NON_NULL_BRANCH_NODE = defaultdict(lambda: 0)
LEAF_EVEN = 0
LEAF_ODD = 0
LEAF = defaultdict(lambda: 0)
LEAF_DEPTH = defaultdict(lambda: 0)
EXTENSION_EVEN = 0
EXTENSION_ODD = 0
EXTENSION = defaultdict(lambda: 0)
EXTENSION_DEPTH = defaultdict(lambda: 0)
EMPTY_HASH = 0


def parse(key, value, depth):
    global BRANCH, BRANCH_COUNT, BRANCH_WITH_VALUE, ERROR, EXTENSION, EXTENSION_EVEN, EXTENSION_ODD, FIRST_NON_NULL_BRANCH_NODE, LAST_NON_NULL_BRANCH_NODE, LEAF, LEAF_EVEN, LEAF_ODD, BRANCH_DEPTH, LEAF_DEPTH, EXTENSION_DEPTH
    value = rlp.decode(value)
    if len(value) == 17:
        BRANCH += 1
        node_count = 16 - value[:16].count(b'')
        BRANCH_COUNT[node_count] += 1
        index = next((i for i, x in enumerate(value[:16]) if x != b''))
        FIRST_NON_NULL_BRANCH_NODE[index] += 1
        index = next((i for i, x in enumerate(
            reversed(value[:16])) if x != b''))
        LAST_NON_NULL_BRANCH_NODE[index] += 1
        if value[16] != b'':
            BRANCH_WITH_VALUE += 1
        BRANCH_DEPTH[depth] += 1
        return [(depth + 1, x) for x in value[:16] if x != b'']

    assert len(value) == 2

    path = value[0]
    prefix = path[0] >> 4
    if prefix == 2:
        LEAF_EVEN += 1
        LEAF[len(path) * 2 - 2] += 1
        LEAF_DEPTH[depth] += 1
        return []
    if prefix == 3:
        LEAF_ODD += 1
        LEAF[len(path) * 2 - 1] += 1
        LEAF_DEPTH[depth] += 1
        return []
    if prefix == 0:
        EXTENSION_EVEN += 1
        EXTENSION[len(path) * 2 - 2] += 1
        EXTENSION_DEPTH[depth] += 1
        return [(depth + 1, value[1])]
    if prefix == 1:
        EXTENSION_ODD += 1
        EXTENSION[len(path) * 2 - 1] += 1
        EXTENSION_DEPTH[depth] += 1
        return [(depth + 1, value[1])]
    assert False


def print_dictionary(dict, file):
    for i in range(16):
        file.write("\t%d: %d" % (i, dict[i]))
    print("", file=file)


def print_counts(file=sys.stdout):
    global BRANCH, BRANCH_COUNT, BRANCH_WITH_VALUE, ERROR, EXTENSION, EXTENSION_EVEN, EXTENSION_ODD, FIRST_NON_NULL_BRANCH_NODE, LAST_NON_NULL_BRANCH_NODE, LEAF, LEAF_EVEN, LEAF_ODD, BRANCH_DEPTH, LEAF_DEPTH, EXTENSION_DEPTH
    print("Extension odd %d, even %d" %
          (EXTENSION_ODD, EXTENSION_EVEN), file=file)
    print("%s" % EXTENSION, file=file)
    print("depth %s" % EXTENSION_DEPTH, file=file)
    print("Leaf odd %d, even %d" % (LEAF_ODD, LEAF_EVEN), file=file)
    print("%s" % LEAF, file=file)
    print("depth %s" % LEAF_DEPTH, file=file)
    print("Branch total %d, with value %d" %
          (BRANCH, BRANCH_WITH_VALUE), file=file)
    print("depth %s" % BRANCH_DEPTH, file=file)
    print("number of branch:", file=file)
    print_dictionary(BRANCH_COUNT, file)
    print("index of first non-null branch:", file=file)
    print_dictionary(FIRST_NON_NULL_BRANCH_NODE, file)
    print("index of last non-null branch:", file=file)
    print_dictionary(LAST_NON_NULL_BRANCH_NODE, file)


if __name__ == '__main__':
    db = plyvel.DB(sys.argv[1], create_if_missing=False)
    i = 0
    hash = sys.argv[2]
    root_hash = bytes.fromhex(hash[2:] if hash.startswith('0x') else hash)
    keys = [(0, root_hash)]
    while keys:
        depth, key = keys.pop()
        value = db.get(key)
        if value:
            keys.extend(parse(key, value, depth))
        else:
            EMPTY_HASH += 1

        i += 1
        if len(sys.argv) == 4 and i == int(sys.argv[3]):
            break
    print_counts()
