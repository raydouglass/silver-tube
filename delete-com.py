import os
import sys

if __name__ == '__main__':
    wtv_dir = sys.argv[1]
    com_dir = sys.argv[2]
    count = 0
    for file in os.listdir(com_dir):
        if file.endswith('xml'):
			wtv_file = os.path.join(wtv_dir, file)
			com_file = os.path.join(com_dir, file)
			if not os.path.isfile(wtv_file):
				#os.remove(com_file)
				print(com_file)
				count += 1
	print(count)