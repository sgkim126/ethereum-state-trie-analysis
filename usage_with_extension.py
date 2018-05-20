#!/usr/bin/env python3
import plyvel
import rlp
import sha3
import sys


def is_branch(node):
    return len(node) == 17


def is_leaf(node):
    if len(node) == 17:
        return False
    prefix = node[0][0] >> 4
    return prefix == 2 or prefix == 3


def is_extension(node):
    if len(node) == 17:
        return False
    prefix = node[0][0] >> 4
    return prefix == 0 or prefix == 1


def parse(value):
    size = len(value)
    node = rlp.decode(value)
    if is_branch(node):
        return 0, 0, size
    assert len(node) == 2, "%d" % len(node)
    if is_leaf(node):
        return size, 0, 0
    if is_extension(node):
        return 0, size, 0
    path = node[0]
    assert False, "%s" % path.hex()


if __name__ == '__main__':
    origin = plyvel.DB(sys.argv[1], create_if_missing=False)
    iterator = origin.iterator()
    i = 0
    leaf_size = 0
    extension_size = 0
    branch_size = 0
    leaf_count = 0
    extension_count = 0
    branch_count = 0
    for key, value in iterator:
        i += 1

        value = origin.get(key)
        k = sha3.keccak_256()
        k.update(value)
        assert key == k.digest(), "%s %s" % (key.hex(), k.hexdigest())
        leaf, extension, branch = parse(value)
        leaf_size += leaf
        extension_size += extension
        branch_size += branch

        leaf_count += 1 if leaf > 0 else 0
        extension_count += 1 if extension > 0 else 0
        branch_count += 1 if branch > 0 else 0

    size = leaf_size + extension_size + branch_size
    count = leaf_count + extension_count + branch_count
    assert count == i, "%d %d" % (count, i)
    print("size: %d\tleaf: %d\textension: %d\tbranch: %d" %
          (size, leaf_size, extension_size, branch_size))
    print("count: %d\tleaf: %d\textension: %d\tbranch: %d" %
          (count, leaf_count, extension_count, branch_count))
    print("average: %d\tleaf: %d\textension: %d\tbranch: %d" % (size / count, leaf_size /
                                                                leaf_count, extension_size / extension_count, branch_size / branch_count))
