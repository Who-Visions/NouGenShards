import sys
sys.path.insert(0, '/Users/kushboygroup/.nougen/src/nougenshards/src')
from nougen_shards.keymaker import get_secret
print("PHOEBUS_TOKEN=" + str(get_secret("NGS_NODE_TOKEN")))
