#!/usr/bin/env python3
import plyvel
import rlp
import sha3
import sys


def is_branch(node):
    return len(node) == 17


def is_leaf(node):
    return len(node) == 2


def parse(value):
    node = rlp.decode(value)
    if is_branch(node):
        return [x for x in node[1:] if x != b'']
    if is_leaf(node):
        return []
    assert False


if __name__ == '__main__':
    origin = plyvel.DB(sys.argv[1], create_if_missing=False)
    target = plyvel.DB(sys.argv[2], create_if_missing=True)
    hash = sys.argv[3]
    root_hash = bytes.fromhex(hash[2:] if hash.startswith('0x') else hash)
    keys = [root_hash]
    i = 0
    while keys:
        key = keys.pop()
        value = origin.get(key)
        assert value

        k = sha3.keccak_256()
        k.update(value)
        assert key == k.digest()

        target.put(key, value)
        keys.extend(parse(value))

        i += 1
    print("%d nodes copied" % i)
