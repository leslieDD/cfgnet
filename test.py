#!/usr/bin/python3
import re

s = r'成功用 "ens47f135bac001-e2xx66-4b36-b947-05dbe2257ede" 激活了设备 ""。'

o = re.findall(r'([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})', s)
print(len(o))

