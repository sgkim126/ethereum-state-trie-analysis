#!/usr/bin/env python3
from itertools import takewhile
import copy
import plyvel
import rlp
import sha3
import sys


class DbWithCache(object):
    def __init__(self, db):
        self.db = db
        self.cache = {}
        self.dirty = {}

    def put(self, key, node):
        dirty = self.dirty.get(key)
        if dirty:
            assert dirty == node, "%s %s" % (dirty, node)
            return
        cache = self.cache.get(key)
        if cache:
            assert cache == node, "%s %s" % (cache, node)
            return
        self.dirty[key] = node

    def get(self, key):
        dirty = self.dirty.get(key)
        if dirty:
            return dirty
        cache = self.cache.get(key)
        if cache:
            return cache
        node = self.db.get(key)
        self.cache[key] = node
        return node

    def clear(self):
        self.dirty.clear()

    def reset(self):
        self.cache.clear()

    def commit(self, hash):
        if not hash:
            return
        dirty = self.dirty.get(hash)
        if not dirty:
            return
        self.cache[hash] = dirty
        self.db.put(hash, dirty)
        node = rlp.decode(dirty)
        if len(node) == 17:
            for hash in node[1:]:
                if not hash:
                    continue
                self.commit(hash)
            return
        assert len(node) == 2, "%d" % len(node)


def common_prefix(a, b):
    return bytes(ch[0] for ch in takewhile(lambda x: x[0] == x[1], zip(a, b)))


def nibbles_to_bytes(path):
    for i, b in enumerate(path):
        assert b < 16, "%d of path is %d\n%s" % (i, b, path.hex())
    if len(path) % 2:
        return bytes([0b10000 + path[0]] + [(i << 4) | j for i, j in zip(path[1::2], path[2::2])])
    else:
        return bytes([0x00] + [(i << 4) | j for i, j in zip(path[0::2], path[1::2])])


def bytes_to_nibbles(path):
    nibbles = []
    if path[0]:
        assert (path[0] >> 4) == 1, "Invalid prefix, %d, %s" % (
            (path[0] >> 4), path.hex())
        nibbles.append(path[0] & 0b1111)
    for b in path[1:]:
        nibbles.append(b >> 4)
        nibbles.append(b & 0b1111)
    return bytes(nibbles)


def insert(node, db):
    if len(node) == 17:
        for hash in node[1:]:
            if not hash:
                continue
            exist = db.get(hash)
            assert exist, "Child hash is not inserted"

    node = copy.copy(node)
    node[0] = nibbles_to_bytes(node[0])
    node_rlp = rlp.encode(node)
    k = sha3.keccak_256()
    k.update(node_rlp)
    node_hash = k.digest()
    assert len(
        k.hexdigest()) == 64, "Invlaid hash length for %s" % node_hash.hexdigest()
    exist = db.get(node_hash)
    assert not exist or exist == node_rlp, "Conflict insertion on %s(%s-%s)" %\
        (node_hash.hex(), exist.hex(), node_rlp.hex())
    db.put(node_hash, node_rlp)
    return node_hash


def make_leaf(path, value, db):
    node = [path, value]
    return insert(node, db)


def change_path_of_branch(node, path, db):
    node[0] = path
    return insert(node, db)


def number_of_non_null_children(node):
    return len([i for i in node[1:] if i])


def non_null_child(node):
    for i, child in enumerate(node[1:]):
        if child:
            return i, child
    assert False


def append_path(path, node, db):
    path = path + node[0]
    if len(node) == 2:
        return make_leaf(path, node[1], db)
    if len(node) == 17:
        return change_path_of_branch(node, path, db)
    assert False, "%d" % len(node)


def make(root_hash, path, value, db):
    assert root_hash, "%s" % root_hash.hex()
    assert path

    node_rlp = db.get(root_hash)
    node = rlp.decode(node_rlp)
    node[0] = bytes_to_nibbles(node[0])
    node_path = node[0]

    if len(node) == 17:
        common_path = common_prefix(node_path, path)
        if common_path != node_path:
            return False, root_hash
        index = path[len(node_path)]
        remain_path = path[len(node_path) + 1:]
        node = copy.copy(node)
        removed, node[1 +
                      index] = make(node[1 + index], remain_path, value, db)
        count = number_of_non_null_children(node)
        if count == 1:
            assert removed
            index, hash = non_null_child(node)
            node_rlp = db.get(hash)
            assert node_rlp, "%s" % hash.hex()
            node = rlp.decode(node_rlp)
            node[0] = bytes_to_nibbles(node[0])
            return removed, append_path(node_path + bytes([index]), node, db)
        return removed, insert(node, db)

    assert len(node) == 2, "%d" % len(node)

    if node_path != path:
        return False, root_hash

    assert node[1] == value, "Conflict on %s (%s-%s)" % (
        root_hash.hex(), node[1].hex(), value.hex())
    return True, b''


if __name__ == '__main__':
    origin = plyvel.DB(sys.argv[1], create_if_missing=False)
    target = plyvel.DB(sys.argv[2], create_if_missing=True)
    iterator = origin.iterator()
    hash = sys.argv[3]
    root_hash = bytes.fromhex(hash[2:] if hash.startswith('0x') else hash)
    i = 0
    number_of_removed = 0
    cache = DbWithCache(target)
    for key, value in iterator:
        key, value = rlp.decode(value)
        assert len(key) == 64, "Key must be 64 length but %d(%s)" % (
            len(key), key.hex())
        if not root_hash:
            break
        i += 1
        removed, root_hash = make(root_hash, key, value, cache)
        cache.commit(root_hash)
        cache.clear()
        if removed:
            number_of_removed += 1
        if i % 100000 == 0:
            cache.reset()
        if len(sys.argv) == 5 and i == int(sys.argv[4]):
            break
    print("%d/%d removed 0x%s" % (number_of_removed, i, root_hash.hex()))
