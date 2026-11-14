# Minimal pure-python Keccak-256 (original Keccak padding, NOT NIST SHA3).
# Verified against known vectors in __main__.
def _rol(x, n):
    return ((x << n) | (x >> (64 - n))) & 0xFFFFFFFFFFFFFFFF

_RC = [0x0000000000000001,0x0000000000008082,0x800000000000808A,0x8000000080008000,
0x000000000000808B,0x0000000080000001,0x8000000080008081,0x8000000000008009,
0x000000000000008A,0x0000000000000088,0x0000000080008009,0x000000008000000A,
0x000000008000808B,0x800000000000008B,0x8000000000008089,0x8000000000008003,
0x8000000000008002,0x8000000000000080,0x000000000000800A,0x800000008000000A,
0x8000000080008081,0x8000000000008080,0x0000000080000001,0x8000000080008008]
_R = [[0,36,3,41,18],[1,44,10,45,2],[62,6,43,15,61],[28,55,25,21,56],[27,20,39,8,14]]

def keccak_256(data: bytes) -> bytes:
    rate = 136  # bytes (1088 bits) for Keccak-256
    # pad10*1 with domain 0x01
    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % rate != rate - 1:
        padded.append(0x00)
    padded.append(0x80)
    st = [0]*25
    for off in range(0, len(padded), rate):
        block = padded[off:off+rate]
        for i in range(rate // 8):
            st[i] ^= int.from_bytes(block[i*8:(i+1)*8], 'little')
        for rnd in range(24):
            # Theta
            C = [st[x] ^ st[x+5] ^ st[x+10] ^ st[x+15] ^ st[x+20] for x in range(5)]
            D = [C[(x+4)%5] ^ _rol(C[(x+1)%5], 1) for x in range(5)]
            for x in range(5):
                for y in range(5):
                    st[x+5*y] ^= D[x]
            # Rho + Pi
            B = [0]*25
            for x in range(5):
                for y in range(5):
                    B[y+5*((2*x+3*y)%5)] = _rol(st[x+5*y], _R[x][y])
            # Chi
            for x in range(5):
                for y in range(5):
                    st[x+5*y] = B[x+5*y] ^ ((~B[(x+1)%5+5*y]) & B[(x+2)%5+5*y])
            # Iota
            st[0] ^= _RC[rnd]
    return b''.join(st[i].to_bytes(8, 'little') for i in range(4))

def selector(sig: str) -> str:
    return '0x' + keccak_256(sig.encode()).hex()[:8]

if __name__ == '__main__':
    assert keccak_256(b'').hex() == 'c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470', 'empty vector'
    assert selector('owner()') == '0x8da5cb5b', selector('owner()')
    assert selector('totalSupply()') == '0x18160ddd', selector('totalSupply()')
    assert selector('balanceOf(address)') == '0x70a08231'
    assert selector('transfer(address,uint256)') == '0xa9059cbb'
    for s in ['mintPrice()','cost()','PRICE()','mintPrice(uint256)','quote(address,uint256)',
              'claimRewards()','claimable(address)','maxSupply()','paused()','name()','symbol()',
              'tokenURI(uint256)','ownerOf(uint256)','mint(uint256)','mint()','getReserves()',
              'getPair(address,address)']:
        print(f'{s:28s} {selector(s)}')
    print('ALL VECTORS OK')
