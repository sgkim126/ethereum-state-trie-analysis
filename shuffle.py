#!/usr/bin/env python3
import plyvel
import rlp
import sha3
import sys


if __name__ == '__main__':
    origin = plyvel.DB(sys.argv[1], create_if_missing=False)
    target = plyvel.DB(sys.argv[2], create_if_missing=True)
    iterator = origin.iterator()
    i = 0
    for key, value in iterator:
        i += 1
        k = sha3.keccak_256()
        k.update(key)
        shuffled = k.digest()
        pair = rlp.encode([key, value])
        target.put(shuffled, pair)
    print("%d nodes shuffled" % i)
