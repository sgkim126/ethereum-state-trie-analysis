#!/usr/bin/env python3
from itertools import takewhile
import copy
import plyvel
import rlp
import sha3
import sys


def is_extension(path):
    prefix = path[0] >> 4
    return prefix == 0 or prefix == 1


def is_leaf(path):
    prefix = path[0] >> 4
    return prefix == 2 or prefix == 3


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
            for hash in node[:16]:
                if not hash:
                    continue
                self.commit(hash)
            return
        assert len(node) == 2, "%d" % len(node)
        path = node[0]
        if is_extension(path):
            self.commit(node[1])
            return
        assert is_leaf(path)


def common_prefix(a, b):
    return bytes(ch[0] for ch in takewhile(lambda x: x[0] == x[1], zip(a, b)))


def nibbles_to_bytes(path, is_leaf):
    for i, b in enumerate(path):
        assert b < 16, "%d of path is %d" % (i, b)
    if len(path) % 2:
        if is_leaf:
            return bytes([0x30 | path[0]] + [(i << 4) | j for i, j in zip(path[1::2], path[2::2])])
        return bytes([0x10 | path[0]] + [(i << 4) | j for i, j in zip(path[1::2], path[2::2])])
    else:
        if is_leaf:
            return bytes([0x20] + [(i << 4) | j for i, j in zip(path[0::2], path[1::2])])
        return bytes([0x00] + [(i << 4) | j for i, j in zip(path[0::2], path[1::2])])


def is_branch_node(node):
    return len(node) == 17


def bytes_to_nibbles(path):
    nibbles = []
    prefix = path[0] >> 4
    assert is_leaf(path) or is_extension(
        path), "Invalid prefix, %d, %s" % (prefix, path.hex())
    if prefix == 0b0001 or prefix == 0b0011:
        nibbles.append(path[0] & 0b1111)
    for b in path[1:]:
        nibbles.append(b >> 4)
        nibbles.append(b & 0b1111)
    return bytes(nibbles), is_leaf(path)


def insert(node, db, is_leaf):
    if len(node) == 17:
        for hash in node[:16]:
            if not hash:
                continue
            exist = db.get(hash)
            assert exist, "Child hash is not inserted"

    node = copy.copy(node)
    if len(node) == 2:
        node[0] = nibbles_to_bytes(node[0], is_leaf)
    node_rlp = rlp.encode(node)
    k = sha3.keccak_256()
    k.update(node_rlp)
    node_hash = k.digest()
    assert len(
        k.hexdigest()) == 64, "Invalid hash length for %s" % node_hash.hexdigest()
    exist = db.get(node_hash)
    assert not exist or exist == node_rlp, "Conflict insertion on %s(%s-%s)" %\
        (node_hash.hex(), exist.hex(), node_rlp.hex())
    db.put(node_hash, node_rlp)
    return node_hash


def make_leaf(path, value, db):
    node = [path, value]
    return insert(node, db, is_leaf=True)


def make_extension(path, hash, db):
    assert len(path) > 0
    node = [path, hash]
    return insert(node, db, is_leaf=False)


def number_of_non_null_children(node):
    return len([i for i in node[:16] if i])


def append_path(path, node, db):
    assert len(node) == 2, "%d" % len(node)
    node_path, is_leaf = bytes_to_nibbles(node[0])

    if is_leaf:
        return make_leaf(path + node_path, node[1], db)
    return make_extension(path + node_path, node[1], db)


def non_null_child(node):
    for i, child in enumerate(node[:16]):
        if child:
            return i, child
    assert False


def make(root_hash, path, value, db):
    assert root_hash, "%s" % root_hash.hex()
    assert path

    node_rlp = db.get(root_hash)
    node = rlp.decode(node_rlp)

    if len(node) == 17:
        index = path[0]
        node = copy.copy(node)
        removed, hash = make(node[index], path[1:], value, db)
        node[index] = hash
        if not hash:
            assert removed
            count = number_of_non_null_children(node)
            if count == 1:
                index, hash = non_null_child(node)
                node_rlp = db.get(hash)
                assert node_rlp, "%s" % hash.hex()
                node = rlp.decode(node_rlp)
                if is_branch_node(node):
                    return removed, make_extension(bytes([index]), hash, db)

                return removed, append_path(bytes([index]), node, db)
        return removed, insert(node, db, is_leaf=False)

    assert len(node) == 2, "Invalid node len:%d" % len(node)

    node[0], is_leaf = bytes_to_nibbles(node[0])
    node_path = node[0]

    if node_path == path:
        # Duplicated path
        assert is_leaf, "It must be leaf"
        assert node[1] == value, "Conflict on %s (%s-%s)" % (
            root_hash.hex(), node[1].hex(), value.hex())
        return True, b''

    if is_leaf:
        return False, root_hash

    common_path = common_prefix(node_path, path)

    if common_path != node_path:
        return False, root_hash

    remain_path = path[len(common_path):]
    old_hash = node[1]
    removed, new_hash = make(old_hash, remain_path, value, db)
    if not new_hash:
        assert removed
        return True, b''

    node_rlp = db.get(new_hash)
    node = rlp.decode(node_rlp)
    if is_branch_node(node):
        return removed, make_extension(common_path, new_hash, db)
    return removed, append_path(common_path, node, db)


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
        removed, root_hash = make(root_hash, key, value, target)
        cache.commit(root_hash)
        cache.clear()
        if removed:
            number_of_removed += 1
        if len(sys.argv) == 5 and i == int(sys.argv[4]):
            break
    print("%d/%d removed 0x%s" % (number_of_removed, i, root_hash.hex()))
