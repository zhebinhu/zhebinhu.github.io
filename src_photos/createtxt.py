# coding: utf-8
import os

src_dir = "./"

def list_img_file(directory):
    """列出目录下所有文件，并筛选出图片文件列表返回"""
    old_list = os.listdir(directory)
    # print old_list
    new_list = []
    for filename in old_list:
        name, fileformat = filename.split(".")
        if fileformat.lower() == "jpg" or fileformat.lower() == "png" or fileformat.lower() == "gif":
            new_list.append(filename)
    # print new_list
    return new_list

if __name__ == "__main__":
    file_list = list_img_file(src_dir)
    for i in range(len(file_list)):
        filename = file_list[i]
        file_text_name = filename.split('.')[0] + '.txt'
        if not os.path.exists(src_dir + file_text_name):
            open(src_dir + file_text_name,'w')