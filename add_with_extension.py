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
    for (i, b) in enumerate(path):
        assert b < 16, "%d of path is %d" % (i, b)
    if len(path) % 2:
        if is_leaf:
            return bytes([0x30 | path[0]] + [(i << 4) | j for i, j in zip(path[1::2], path[2::2])])
        return bytes([0x10 | path[0]] + [(i << 4) | j for i, j in zip(path[1::2], path[2::2])])
    else:
        if is_leaf:
            return bytes([0x20] + [(i << 4) | j for i, j in zip(path[0::2], path[1::2])])
        return bytes([0x00] + [(i << 4) | j for i, j in zip(path[0::2], path[1::2])])


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


def change_child_of_branch(node, b, h, db):
    assert 0 <= b < 16, 'Invalid b %d' % b
    assert len(h) == 0 or len(h) == 32, 'Invalid h size %d' % len(h)
    node[b] = h
    return insert(node, db, is_leaf=False)


def make_two_children_branch(b0, h0, b1, h1, db):
    node = [b'' for i in range(17)]
    assert 0 <= b0 < 16, 'Invalid b0 %d' % b0
    assert 0 <= b1 < 16, 'Invalid b1 %d' % b1
    assert len(h0) == 0 or len(h0) == 32, 'Invalid h0 size %d' % len(h0)
    assert len(h1) == 0 or len(h1) == 32, 'Invalid h1 size %d' % len(h1)
    node[b0] = h0
    node[b1] = h1
    return insert(node, db, is_leaf=False)


def make(root_hash, path, value, db):
    if root_hash == b'':
        # Add leaf
        hash = make_leaf(path, value, db)
        return len(path), hash

    assert 0 < len(path), "Unreachable"

    node_rlp = db.get(root_hash)
    node = rlp.decode(node_rlp)

    if len(node) == 17:
        # B[C, ...] -> B[C', ...]
        assert 1 < len(path), "Invalid path of branch node %s" % path.hex()

        index = path[0]
        assert 0 <= index < 16, "Invalid child index %d" % index
        old_child_hash = node[index]

        size, new_child_hash = make(old_child_hash, path[1:], value, db)

        return 1 + size, change_child_of_branch(node, index, new_child_hash, db)

    assert len(node) == 2, "Invalid node len:%d" % len(node)

    node[0], is_leaf = bytes_to_nibbles(node[0])
    node_path = node[0]

    if node_path == path:
        # Duplicated path
        assert is_leaf, "It must be leaf"
        assert node[1] == value, "Conflict on %s (%s-%s)" % (
            root_hash.hex(), node[1].hex(), value.hex())
        return len(path), root_hash

    common_path = common_prefix(node_path, path)

    if is_leaf:
        new_leaf_path = path[len(common_path) + 1:]
        old_leaf_path = node_path[len(common_path) + 1:]

        new_leaf_index = path[len(common_path)]
        old_leaf_index = node_path[len(common_path)]
        assert new_leaf_index != old_leaf_index, "Index conflict %d %d" % (
            new_leaf_index, old_leaf_index)

        new_leaf = make_leaf(new_leaf_path, value, db)
        old_leaf = make_leaf(old_leaf_path, node[1], db)

        assert len(path) == len(node_path), "Two leaves must have the same length(%d %d)" %\
            (len(path), len(node_path))
        hash = make_two_children_branch(
            new_leaf_index, new_leaf, old_leaf_index, old_leaf, db)
        if len(common_path) == 0:
            # L1 -> B[L1', L2, ...]
            return 1 + len(new_leaf_path), hash
        # L1 -> E.B[L1', L2, ...]
        hash = make_extension(common_path, hash, db)
        return len(common_path) + 1 + len(new_leaf_path), hash

    assert len(node_path) > 0
    if len(common_path) == 0:
        if len(node_path) == 1:
            # E(B1) -> B2[B1', L, ...]
            b1_index = node_path[0]
            assert 0 <= b1_index < 16, "Invalid index %d" % b1_index
            b1 = node[1]

            l_index = path[0]
            assert 0 <= l_index < 16, "Invalid index %d" % l_index
            l = make_leaf(path[1:], value, db)

            hash = make_two_children_branch(b1_index, b1, l_index, l, db)
            return len(path), hash

        l_index = path[0]
        assert 0 <= l_index < 16, "Invalid index %d" % l_index
        l = make_leaf(path[1:], value, db)

        e_index = node_path[0]
        assert 0 <= e_index < 16, "Invalid index %d" % e_index
        e = make_extension(node_path[1:], node[1], db)

        hash = make_two_children_branch(l_index, l, e_index, e, db)
        # E(B1) -> B2[E'(B1), L, ...]
        return len(path), hash

    if len(node_path) == len(common_path) + 1:
        # E(B1) -> E''.B2[B1, L, ...]
        l_index = path[len(common_path)]
        l_path = path[len(common_path) + 1:]
        l = make_leaf(l_path, value, db)

        b1_index = node_path[len(common_path)]
        b1 = node[1]

        b2 = make_two_children_branch(l_index, l, b1_index, b1, db)
        hash = make_extension(common_path, b2, db)
        return len(common_path) + 1 + len(l_path), hash

    if len(node_path) > len(common_path):
        l_index = path[len(common_path)]
        l_path = path[len(common_path) + 1:]
        l = make_leaf(l_path, value, db)

        e_index = node_path[len(common_path)]
        e_path = node_path[len(common_path) + 1:]
        e = make_extension(e_path, node[1], db)

        b_hash = make_two_children_branch(l_index, l, e_index, e, db)
        hash = make_extension(common_path, b_hash, db)
        # E(B1) -> E''.B2[E'(B1), L, ...]
        return len(common_path) + 1 + len(l_path), hash

    assert len(node_path) == len(common_path), "It must be the same length %d==%d" % (
        len(node_path), len(common_path))
    # E(B) -> E'(make(B))
    old_hash = node[1]
    new_path = path[len(common_path):]

    size, new_hash = make(old_hash, new_path, value, db)
    assert size == len(new_path)
    hash = make_extension(common_path, new_hash, db)
    return len(common_path) + size, hash


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
        if i % 100000 == 0:
            cache.reset()
        if len(sys.argv) == 4 and i == int(sys.argv[3]):
            break
    print("%d 0x%s" % (i, root_hash.hex()))
