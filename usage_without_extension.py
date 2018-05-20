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
    size = len(value)
    node = rlp.decode(value)
    if is_branch(node):
        return 0, size
    assert len(node) == 2, "%d" % len(node)
    if is_leaf(node):
        return size, 0
    path = node[0]
    assert False, "%s" % path.hex()


if __name__ == '__main__':
    origin = plyvel.DB(sys.argv[1], create_if_missing=False)
    iterator = origin.iterator()
    i = 0
    leaf_size = 0
    branch_size = 0
    leaf_count = 0
    branch_count = 0
    for key, value in iterator:
        i += 1

        value = origin.get(key)
        k = sha3.keccak_256()
        k.update(value)
        assert key == k.digest(), "%s %s" % (key.hex(), k.hexdigest())
        leaf, branch = parse(value)
        leaf_size += leaf
        branch_size += branch

        leaf_count += 1 if leaf > 0 else 0
        branch_count += 1 if branch > 0 else 0

    size = leaf_size + branch_size
    count = leaf_count + branch_count
    assert count == i, "%d %d" % (count, i)
    print("size: %d\tleaf: %d\tbranch: %d" % (size, leaf_size, branch_size))
    print("count: %d\tleaf: %d\tbranch: %d" %
          (count, leaf_count, branch_count))
    print("average: %d\tleaf: %d\tbranch: %d" %
          (size / count, leaf_size / leaf_count, branch_size / branch_count))
