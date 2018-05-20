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
        assert b < 16, "%d of path is %d" % (i, b)
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
        k.hexdigest()) == 64, "Invalid hash length for %s" % node_hash.hexdigest()
    exist = db.get(node_hash)
    assert not exist or exist == node_rlp, "Conflict insertion on %s(%s-%s)" %\
        (node_hash.hex(), exist.hex(), node_rlp.hex())
    db.put(node_hash, node_rlp)
    return node_hash


def make_leaf(path, value, db):
    node = [path, value]
    return insert(node, db)


def change_path_of_branch(node, path, db):
    assert common_prefix(node[0], path) != '', 'Path must be changed'
    assert len(path) < len(node[0]), 'Path must be smaller than original'
    node[0] = path
    return insert(node, db)


def change_child_of_branch(node, b, h, db):
    assert 0 <= b < 16, 'Invalid b %d' % b
    assert len(h) == 0 or len(h) == 32, 'Invalid h size %d' % len(h)
    node[b + 1] = h
    return insert(node, db)


def make_two_children_branch(path, b0, h0, b1, h1, db):
    node = [b'' for i in range(17)]
    assert 0 <= b0 < 16, 'Invalid b0 %d' % b0
    assert 0 <= b1 < 16, 'Invalid b1 %d' % b1
    assert len(h0) == 0 or len(h0) == 32, 'Invalid h0 size %d' % len(h0)
    assert len(h1) == 0 or len(h1) == 32, 'Invalid h1 size %d' % len(h1)
    node[0] = path
    node[b0 + 1] = h0
    node[b1 + 1] = h1
    return insert(node, db)


def make(root_hash, path, value, db):
    if root_hash == b'':
        # Add leaf
        hash = make_leaf(path, value, db)
        # print("leaf", hash.hex(), file=sys.stderr)
        return len(path), hash

    assert 0 < len(path), "Unreachable"

    node_rlp = db.get(root_hash)
    node = rlp.decode(node_rlp)
    node[0] = bytes_to_nibbles(node[0])
    node_path = node[0]

    if node_path == path:
        # Duplicated path
        assert len(node) == 2, "Must be leaf"
        assert node[1] == value, "Conflict on %s (%s-%s)" % (
            root_hash.hex(), node[1].hex(), value.hex())
        # print("duplicate", root_hash.hex(), file=sys.stderr)
        return len(path), root_hash

    if len(node) == 17:
        assert len(node_path) < len(path), "path must be shorter than node_path (%d:%s %d:%s) %d" %\
            (len(node_path), node_path.hex(), len(path), path.hex(), len(node))
        common_path = common_prefix(node_path, path)
        branch_index = path[len(common_path)]

        if node_path == common_path:
            # B1.[..., C, ...]-> B1'.[..., make(C, Ln), ...]
            child_index = path[len(common_path)]
            child_path = path[len(common_path) + 1:]
            old_child_hash = node[child_index + 1]
            size, new_child_hash = make(old_child_hash, child_path, value, db)
            assert size == len(child_path), "Expected size: %d actual: %d" % (
                len(child_path), size)

            hash = change_child_of_branch(
                node, child_index, new_child_hash, db)
            # print("set one child of branch", hash.hex(), file=sys.stderr)
            return len(node_path) + 1 + size, hash

        # B1 -> B2.[B1',..., Ln]
        new_leaf_index = path[len(common_path)]
        old_branch_index = node_path[len(common_path)]
        assert new_leaf_index != old_branch_index, "Index conlfict %d %d" % (
            new_leaf_index, old_branch_index)

        new_leaf_path = path[len(common_path) + 1:]
        new_leaf = make_leaf(new_leaf_path, value, db)

        old_branch_path = node_path[len(common_path) + 1:]
        old_branch = change_path_of_branch(node, old_branch_path, db)

        hash = make_two_children_branch(
            common_path, new_leaf_index, new_leaf, old_branch_index, old_branch, db)
        # print("branch to branch and leaf", hash.hex(), file=sys.stderr)
        return len(common_path) + 1 + len(new_leaf_path), hash

    assert len(node) == 2, "2 or 17 but %d" % len(node)

    # L1 -> B.[L1', ..., Ln]
    common_path = common_prefix(node_path, path)

    new_leaf_path = path[len(common_path) + 1:]
    old_leaf_path = node_path[len(common_path) + 1:]
    assert len(old_leaf_path) == len(new_leaf_path), "Two leaves must have the same length(%d %d)" %\
        (len(old_leaf_path), len(new_leaf_path))

    new_leaf_index = path[len(common_path)]
    old_leaf_index = node_path[len(common_path)]
    assert new_leaf_index != old_leaf_index, "Index conflict %d %d" % (
        new_leaf_index, old_leaf_index)

    new_leaf = make_leaf(new_leaf_path, value, db)
    old_leaf = make_leaf(old_leaf_path, node[1], db)
    hash = make_two_children_branch(
        common_path, new_leaf_index, new_leaf, old_leaf_index, old_leaf, db)
    # print("leaf to branch", hash.hex(), file=sys.stderr)
    return len(common_path) + 1 + len(new_leaf_path), hash


if __name__ == '__main__':
    origin = plyvel.DB(sys.argv[1], create_if_missing=False)
    target = plyvel.DB(sys.argv[2], create_if_missing=True)
    iterator = origin.iterator()
    root_hash = b''
    i = 0
    cache = DbWithCache(target)
    for key, value in iterator:
        i += 1
        key, value = rlp.decode(value)
        assert len(key) == 64, "Key must be 64 length but %d(%s)" % (
            len(key), key.hex())
        size, root_hash = make(root_hash, key, value, cache)
        cache.commit(root_hash)
        cache.clear()
        assert size == 64, "Size must be 64 but %d" % size
        if len(sys.argv) == 4 and i == int(sys.argv[3]):
            break
    print("%d 0x%s" % (i, root_hash.hex()))
