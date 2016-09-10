import mmap
import struct
import os

HEADER_BYTES = bytes([0x5A, 0xFE, 0xD7, 0x6D, 0xC8, 0x1D, 0x8F, 0x4A, 0x99, 0x22, 0xFA, 0xB1, 0x1C, 0x38, 0x14, 0x53])

ORIGINAL_BROADCAST_DATE_KEY = 'WM/MediaOriginalBroadcastDateTime'


def _check_header(mm):
    header = mm.read(len(HEADER_BYTES))
    return header == HEADER_BYTES


def extract_original_air_date(wtv_file, parse_from_filename=True, metadata=None):
    if metadata is None:
        metadata = extract_metadata(wtv_file)
    # WM/MediaOriginalBroadcastDateTime=2012-10-13T04:00:00Z
    air_date = None
    if ORIGINAL_BROADCAST_DATE_KEY in metadata:
        air_date = metadata[ORIGINAL_BROADCAST_DATE_KEY]
    if air_date is None or air_date == '0001-01-01T00:00:00Z':
        # Extract from filename
        if parse_from_filename:
            split = os.path.basename(wtv_file).split('_')
            air_date = split[2] + '-' + split[3] + '-' + split[4]
        else:
            air_date = None
    else:
        air_date = air_date.split('T')[0]
    return air_date


def extract_metadata(wtv_file):
    meta = {}
    with open(wtv_file, 'r+b') as file:
        mm = mmap.mmap(file.fileno(), 0)
        index = 0x12000
        mm.seek(index)
        while (_check_header(mm)):
            type = struct.unpack('<I', mm.read(4))[0]
            length = struct.unpack('<I', mm.read(4))[0]
            name = bytearray()
            while (True):
                b = mm.read(2)
                if b == bytes([0x00, 0x00]):
                    break
                name.append(b[0])
                name.append(b[1])
            name = name.decode('utf-16LE')
            if length > 0:
                data = mm.read(length)
                if type == 0:
                    # integer
                    meta[name] = struct.unpack('<i', data)[0]
                elif type == 1:
                    # string
                    meta[name] = data[0:len(data) - 2].decode('utf-16LE')
                elif type == 2:
                    # image
                    # TODO
                    meta[name] = data
                elif type == 3:
                    # boolean
                    meta[name] = bytes([0x00, 0x00, 0x00, 0x00]) != data
                elif type == 4:
                    # long
                    meta[name] = struct.unpack('<q', data)[0]
                elif type == 6:
                    meta[name] = data.hex()
                else:
                    # unknown
                    meta[name] = data
            else:
                meta[name] = None
    return meta

if __name__ == '__main__':
    import sys, json
    if len(sys.argv) > 1:
        meta = extract_metadata(sys.argv[1])
        print(json.dumps(meta))
    else:
        print('Too few args')