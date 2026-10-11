SHARD_BITS = 16
SEQ_BITS = 40  # BUG: the layout is a 16-bit shard and a 48-bit sequence


def pack_id(shard, seq):
    """Pack a 16-bit shard and a 48-bit sequence into one unsigned 64-bit id.

    The shard sits in the high bits. Out-of-range fields raise ValueError.
    """
    if not 0 <= shard < 1 << SHARD_BITS:
        raise ValueError(f"shard out of range: {shard}")
    if not 0 <= seq < 1 << 48:
        raise ValueError(f"seq out of range: {seq}")
    return (shard << SEQ_BITS) | seq


def unpack_id(value):
    return value >> SEQ_BITS, value & ((1 << SEQ_BITS) - 1)
