"""Compare the C crypto against independent implementations.

SHA-512: hashlib. Ed25519: the `cryptography` package (OpenSSL) plus RFC 8032
test 1-3. CRC32C: the RFC 3720 check value. BLAKE3: published vectors for ""
and "abc", plus a recursive Python model of the tree (structurally unlike the
C stack algorithm, so it catches tree-shape bugs; it shares the compression
definition, so it is not a fully independent oracle).
"""
import hashlib, os, random, subprocess, sys
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

exe = sys.argv[1]
p = subprocess.Popen([exe], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
def ask(*a):
    p.stdin.write(" ".join(x if x else "-" for x in a) + "\n"); p.stdin.flush()
    return p.stdout.readline().strip()

fails = 0; checks = 0
def check(name, got, want):
    global fails, checks
    checks += 1
    if got != want:
        fails += 1; print("FAIL", name, "got", got[:80], "want", want[:80])

# ---- BLAKE3 model (paper section 2) ----
IV = [0x6A09E667,0xBB67AE85,0x3C6EF372,0xA54FF53A,0x510E527F,0x9B05688C,0x1F83D9AB,0x5BE0CD19]
PERM = [2,6,3,10,7,0,4,13,1,11,12,5,9,14,15,8]
M32 = 0xffffffff
def rotr(x,n): return ((x>>n)|(x<<(32-n)))&M32
def g(s,a,b,c,d,x,y):
    s[a]=(s[a]+s[b]+x)&M32; s[d]=rotr(s[d]^s[a],16); s[c]=(s[c]+s[d])&M32; s[b]=rotr(s[b]^s[c],12)
    s[a]=(s[a]+s[b]+y)&M32; s[d]=rotr(s[d]^s[a],8);  s[c]=(s[c]+s[d])&M32; s[b]=rotr(s[b]^s[c],7)
def compress(cv,block,ctr,blen,flags):
    m=[int.from_bytes(block[4*i:4*i+4],'little') for i in range(16)]
    s=cv[:]+IV[:4]+[ctr&M32,ctr>>32,blen,flags]
    for r in range(7):
        g(s,0,4,8,12,m[0],m[1]); g(s,1,5,9,13,m[2],m[3]); g(s,2,6,10,14,m[4],m[5]); g(s,3,7,11,15,m[6],m[7])
        g(s,0,5,10,15,m[8],m[9]); g(s,1,6,11,12,m[10],m[11]); g(s,2,7,8,13,m[12],m[13]); g(s,3,4,9,14,m[14],m[15])
        m=[m[PERM[i]] for i in range(16)]
    return [s[i]^s[i+8] for i in range(8)]
def chunk_cv(data,ctr,root):
    blocks=[data[i:i+64] for i in range(0,len(data),64)] or [b""]
    cv=IV[:]
    for i,bk in enumerate(blocks):
        f=(1 if i==0 else 0)|(2 if i==len(blocks)-1 else 0)|(8 if root and i==len(blocks)-1 else 0)
        cv=compress(cv,bk.ljust(64,b"\0"),ctr,len(bk),f)
    return cv
def tree(data,ctr,root):
    n=max(1,(len(data)+1023)//1024)
    if n==1: return chunk_cv(data,ctr,root)
    left=1
    while left*2<n: left*=2          # left subtree: largest power of two < n chunks
    l=tree(data[:left*1024],ctr,False); r=tree(data[left*1024:],ctr+left,False)
    blk=b"".join(x.to_bytes(4,'little') for x in l+r)
    return compress(IV[:],blk,0,64,4|(8 if root else 0))
def b3(data): return b"".join(x.to_bytes(4,'little') for x in tree(data,0,True)).hex()

check("blake3 empty (published)", ask("blake3",""), "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262")
check("blake3 abc (published)", ask("blake3",b"abc".hex()), "6437b3ac38465133ffb63b75273a8db548c558465d79db03fd359c6cd5bd9d85")
check("python model empty", b3(b""), "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262")
lens=[0,1,63,64,65,127,128,1023,1024,1025,2047,2048,2049,3072,3073,4096,4097,5120,6144,7168,8192,8193,16384,31744,102400,102401]
for n in lens:
    d=bytes(i%251 for i in range(n))   # the official test-vector input pattern
    want=b3(d)
    check("blake3 len %d"%n, ask("blake3",d.hex()), want)
    check("blake3 incremental len %d"%n, ask("blake3inc",d.hex()), want)

for n in [0,1,111,112,127,128,129,239,240,255,256,1000,4096,10007]:
    d=os.urandom(n)
    check("sha512 len %d"%n, ask("sha512",d.hex()), hashlib.sha512(d).hexdigest())
check("crc32c check value", ask("crc32c",b"123456789".hex()), "e3069283")

# RFC 8032 section 7.1 tests 1-3
rfc=[("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60","",
      "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
      "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
     ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb","72",
      "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
      "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
     ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7","af82",
      "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
      "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a")]
for sk,msg,pk,sig in rfc:
    check("rfc8032 pub", ask("pub","",sk), pk)
    check("rfc8032 sig", ask("sign",msg,sk), sig)
    check("rfc8032 verify", ask("verify",msg,sig,pk), "0")
rng=random.Random(1085)
for i in range(60):
    seed=os.urandom(32); msg=os.urandom(rng.randrange(0,600))
    k=Ed25519PrivateKey.from_private_bytes(seed)
    pk=k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    sig=k.sign(msg).hex()
    check("ed25519 pub vs openssl", ask("pub","",seed.hex()), pk)
    check("ed25519 sign vs openssl", ask("sign",msg.hex(),seed.hex()), sig)
    check("ed25519 verify good", ask("verify",msg.hex(),sig,pk), "0")
    bad=bytearray(bytes.fromhex(sig)); bad[rng.randrange(64)]^=1<<rng.randrange(8)
    check("ed25519 verify flipped sig", ask("verify",msg.hex(),bad.hex(),pk), "-1")
    if msg:
        m2=bytearray(msg); m2[0]^=1
        check("ed25519 verify flipped msg", ask("verify",bytes(m2).hex(),sig,pk), "-1")
# a signature with S + L (non-canonical) must be refused
L=2**252+27742317777372353535851937790883648493
s=int.from_bytes(bytes.fromhex(rfc[0][3])[32:],'little')+L
nc=bytes.fromhex(rfc[0][3])[:32]+s.to_bytes(32,'little')
check("ed25519 rejects S >= L", ask("verify","",nc.hex(),rfc[0][2]), "-1")
p.stdin.close(); p.wait()
print("crypto: %d checks, %d failures" % (checks, fails))
sys.exit(1 if fails else 0)
