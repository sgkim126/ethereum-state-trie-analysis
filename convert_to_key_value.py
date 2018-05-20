#!/usr/bin/env python3
import plyvel
import rlp
import sys


def parse(origin, target, hash, path):
    value = origin.get(hash)
    try:
        value = rlp.decode(value)
        if len(value) == 17:
            for i, hash in ((i, x) for i, x in enumerate(value[:16]) if x != b''):
                parse(origin, target, hash, path + [i])
            return
        if len(value) != 2:
            print("Invalid number of item", file=sys.stderr)
            return

        nibbles = []
        for byte in value[0]:
            nibbles.append(byte >> 4)
            nibbles.append(byte & 0b1111)
        if nibbles[0] == 2:
            path = path + nibbles[2:]
            assert len(path) == 64
            target.put(bytes(path), value[1])
            return
        if nibbles[0] == 3:
            path = path + nibbles[1:]
            assert len(path) == 64
            target.put(bytes(path), value[1])
            return
        if nibbles[0] == 0:
            parse(origin, target, value[1], path + nibbles[2:])
            return
        if nibbles[0] == 1:
            parse(origin, target, value[1], path + nibbles[1:])
            return
    except Exception as e:
        print("error %s" % e, file=sys.stderr)
        raise e
    return


if __name__ == '__main__':
    origin = plyvel.DB(sys.argv[1], create_if_missing=False)
    target = plyvel.DB(sys.argv[2], create_if_missing=True)
    hash = sys.argv[3]
    root_hash = bytes.fromhex(hash[2:] if hash.startswith('0x') else hash)
    parse(origin, target, root_hash, [])
