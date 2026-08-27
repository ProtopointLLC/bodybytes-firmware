"""
Minimal YMODEM-1K sender, sized for U-Boot's `loady`.

U-Boot's receiver (common/xyzModem.c) is CRC-mode only and accepts 1K
(STX) data blocks, which is what makes this worth using: the recovery
image is ~13 MiB, so 128-byte blocks would cost ~107k round trips instead
of ~13.4k.

There is no hardware flow control on this board's UART2 test points, so
the per-block ACK is the only thing pacing the sender. That is exactly
why YMODEM works here where raw streaming would overrun the FIFO.
"""

import time

SOH = 0x01          # 128-byte block
STX = 0x02          # 1024-byte block
EOT = 0x04
ACK = 0x06
NAK = 0x15
CAN = 0x18
CRC = 0x43          # 'C' - receiver requests CRC mode

BLOCK = 1024
PAD = 0x1A          # YMODEM pads the final short block with SUB


class YmodemError(Exception):
    pass


def _crc16_table():
    tab = []
    for i in range(256):
        c = i << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
        tab.append(c)
    return tab


_TAB = _crc16_table()


def crc16(data: bytes, crc: int = 0) -> int:
    for b in data:
        crc = ((crc << 8) & 0xFFFF) ^ _TAB[((crc >> 8) ^ b) & 0xFF]
    return crc


def _read_byte(ser, timeout: float):
    """One byte, or None on timeout. Does not rely on ser.timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        b = ser.read(1)
        if b:
            return b[0]
    return None


def _wait_for(ser, accept: set, timeout: float, what: str) -> int:
    """Wait for one of `accept`. CAN from the receiver aborts immediately."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        b = _read_byte(ser, max(0.05, deadline - time.monotonic()))
        if b is None:
            continue
        if b in accept:
            return b
        if b == CAN:
            if _read_byte(ser, 0.5) == CAN:
                raise YmodemError(f"receiver cancelled while waiting for {what}")
    raise YmodemError(f"timeout after {timeout:.0f}s waiting for {what}")


def _packet(seq: int, payload: bytes) -> bytes:
    head = STX if len(payload) == BLOCK else SOH
    c = crc16(payload)
    return bytes([head, seq & 0xFF, (~seq) & 0xFF]) + payload + bytes([c >> 8, c & 0xFF])


def _send_packet(ser, pkt: bytes, retries: int, timeout: float, what: str) -> None:
    for attempt in range(retries):
        ser.write(pkt)
        ser.flush()
        b = _wait_for(ser, {ACK, NAK}, timeout, what)
        if b == ACK:
            return
    raise YmodemError(f"{what}: NAKed {retries} times")


def send(ser, data: bytes, name: str = "image.bin",
         progress=None, timeout: float = 15.0, retries: int = 10) -> None:
    """
    Send `data` to a waiting YMODEM receiver on the open serial port `ser`.

    `progress(sent, total)` is called after each accepted block.
    Raises YmodemError on protocol failure; the caller owns the port.
    """
    total = len(data)
    ser.reset_input_buffer()

    # The receiver announces CRC mode with 'C'. U-Boot emits this right
    # after the "## Ready for binary (ymodem) download" banner.
    _wait_for(ser, {CRC}, timeout, "initial 'C' from receiver")

    # Block 0: filename NUL, decimal length NUL, zero padded to 128.
    header = name.encode() + b"\0" + str(total).encode() + b"\0"
    _send_packet(ser, _packet(0, header.ljust(128, b"\0")),
                 retries, timeout, "header block")

    # Receiver asks again for the first data block.
    _wait_for(ser, {CRC}, timeout, "'C' before first data block")

    seq = 1
    sent = 0
    for off in range(0, total, BLOCK):
        chunk = data[off:off + BLOCK]
        if len(chunk) < BLOCK:
            chunk = chunk.ljust(BLOCK, bytes([PAD]))
        _send_packet(ser, _packet(seq, chunk), retries, timeout,
                     f"data block {seq}")
        seq = (seq + 1) & 0xFF
        sent = min(off + BLOCK, total)
        if progress:
            progress(sent, total)

    # EOT is NAKed once by convention, then ACKed.
    ser.write(bytes([EOT]))
    ser.flush()
    b = _wait_for(ser, {ACK, NAK}, timeout, "response to EOT")
    if b == NAK:
        ser.write(bytes([EOT]))
        ser.flush()
        _wait_for(ser, {ACK}, timeout, "ACK for second EOT")

    # Terminating null header ends the batch. U-Boot does not always ask
    # for it, so this is best effort - the transfer is already complete.
    try:
        _wait_for(ser, {CRC}, 2.0, "'C' before terminating block")
        ser.write(_packet(0, bytes(128)))
        ser.flush()
        _wait_for(ser, {ACK}, 2.0, "ACK for terminating block")
    except YmodemError:
        pass
