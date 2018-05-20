### Result
#### 4207410 (Aug-26-2017 11:15:25 PM +UTC)
```
$python main.py ~/.ethereum/geth/chaindata/ 0x1dad76e8980f29e6275e7ab7c2fda5f4c09c3b59c7ff6bab6cb06e5e4e8acda0
Extension odd 60163, even 8732
defaultdict(<function <lambda> at 0x7f64715eeb70>, {1: 52070, 4: 2787, 5: 7464, 6: 2679, 2: 3257, 7: 188, 3: 441, 8: 9})
depth defaultdict(<function <lambda> at 0x7f64715eebf8>, {6: 60021, 7: 5194, 5: 3354, 8: 319, 9: 7})
Leaf odd 1848140, even 4452207
defaultdict(<function <lambda> at 0x7f64715eea60>, {58: 4296320, 56: 136138, 57: 1816425, 52: 18704, 59: 15507, 51: 7502, 55: 8640, 54: 543, 50: 500, 49: 24, 53: 42, 48: 2})
depth defaultdict(<function <lambda> at 0x7f64715eeae8>, {6: 4296320, 8: 160437, 7: 1816858, 9: 10573, 5: 15507, 10: 638, 11: 14})
Branch total 2053732, with value 0
depth defaultdict(<function <lambda> at 0x7f6476087730>, {0: 1, 1: 16, 2: 256, 3: 4096, 4: 65536, 5: 1027090, 7: 80182, 6: 870939, 8: 5290, 9: 319, 10: 7})
number of branch:
        0: 0    1: 0    2: 928151       3: 223773       4: 209795       5: 221755       6: 184380       7: 119615       8: 61263        9: 24874        10: 7850        11: 1940        12: 362 13: 58  14: 60  15: 2527
index of first non-null branch:
        0: 521972       1: 339830       2: 260243       3: 202823       4: 160495       5: 129117       6: 104220       7: 84520        8: 69093        9: 55458        10: 44149       11: 33692       12: 24572       13: 15743       14: 7805        15: 0
index of last non-null branch:
        0: 521524       1: 340255       2: 260068       3: 203518       4: 160023       5: 128715       6: 104432       7: 84328        8: 68877        9: 55839        10: 44343       11: 33849       12: 24319       13: 15839       14: 7803        15: 0
Unexpected prefix 0, length 0, error: 0, none: 0
```

#### Shuffle
```
$python ./convert_to_key_value.py ~/.ethereum/geth/chaindata/ ./data-key-value 0x1dad76e8980f29e6275e7ab7c2fda5f4c09c3b59c7ff6bab6cb06e5e4e8acda0
$python ./shuffle.py data-key-value/ data-shuffled
6300347 nodes shuffled
```
