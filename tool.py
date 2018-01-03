# coding: utf-8
import json
import os
from datetime import datetime

from ImageProcess import Graphics
from PIL import Image

from qiniu import Auth, put_file

# 定义压缩比，数值越大，压缩越小
SIZE_normal = 1.0
SIZE_small = 1.5
SIZE_more_small = 2.0
SIZE_more_small_small = 3.0

# 上传图片列表
upload_list = []
# 原图和缩略图路径
src_dir, des_dir = "./src_photos/", "./min_photos/"


def make_directory(directory):
    """创建目录"""
    os.makedirs(directory)


def directory_exists(directory):
    """判断目录是否存在"""
    if os.path.exists(directory):
        return True
    else:
        return False


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


def print_help():
    print("""
    This program helps compress many image files
    you can choose which scale you want to compress your img(jpg/png/etc)
    1) normal compress(4M to 1M around)
    2) small compress(4M to 500K around)
    3) smaller compress(4M to 300K around)
    """)


def compress(choose, des_dir, src_dir, file_list):
    """压缩算法，img.thumbnail对图片进行压缩，

    参数
    -----------
    choose: str
            选择压缩的比例，有4个选项，越大压缩后的图片越小
    """
    if choose == '1':
        scale = SIZE_normal
    if choose == '2':
        scale = SIZE_small
    if choose == '3':
        scale = SIZE_more_small
    if choose == '4':
        scale = SIZE_more_small_small
    for infile in file_list:
        img = Image.open(src_dir + infile)
        # size_of_file = os.path.getsize(infile)
        w, h = img.size
        img.thumbnail((int(w / scale), int(h / scale)))
        img.save(des_dir + infile)


def compress_photo():
    '''调用压缩图片的函数
    '''
    if not directory_exists(src_dir):
        make_directory(src_dir)
    file_list_src = list_img_file(src_dir)

    if not directory_exists(des_dir):
        make_directory(des_dir)
    file_list_des = list_img_file(des_dir)
    '''如果已经压缩了，就不再压缩'''
    for i in range(len(file_list_des)):
        if file_list_des[i] in file_list_src:
            file_list_src.remove(file_list_des[i])
    global upload_list
    upload_list = file_list_src[:]
    print(upload_list)
    print()
    '''如果小于20KB，就不再压缩'''
    for i in range(len(upload_list)):
        if os.path.getsize(src_dir + upload_list[i]) < 20 * 1024:
            imge = Image.open(src_dir + upload_list[i])
            imge.save(des_dir + upload_list[i])
            file_list_src.remove(upload_list[i])
    compress('4', des_dir, src_dir, file_list_src)


def handle_photo():
    '''根据图片的文件名处理成需要的json格式的数据

    -----------
    最后将data.json文件存到博客的source/photos文件夹下
    '''
    file_list = list_img_file(src_dir)
    list_info = []
    for i in range(len(file_list)):
        filename = file_list[i]
        file_text_name = filename.split('.')[0] + '.txt'
        '''指定了日期则使用指定日期，未指定日期使用当前日期'''
        f_info = filename.split("__")
        if len(f_info) > 1:
            date_str = f_info[0]
            date = datetime.strptime(date_str, "%Y-%m-%d")
        else:
            date = datetime.now()
        year_month = str(date.year) + "-" + str(date.month)
        if os.path.exists(src_dir + file_text_name):
            info = open(src_dir + file_text_name, 'r').read()
        else:
            info = ""
        if i == 0:  # 处理第一个文件
            new_dict = {"date": year_month, "arr": {'year': date.year,
                                                    'month': date.month,
                                                    'link': [filename],
                                                    'text': [info],
                                                    'type': ['image']
                                                    }
                        }
            list_info.append(new_dict)
        elif year_month != list_info[-1]['date']:  # 不是最后的一个日期，就新建一个dict
            new_dict = {"date": year_month, "arr": {'year': date.year,
                                                    'month': date.month,
                                                    'link': [filename],
                                                    'text': [info],
                                                    'type': ['image']
                                                    }
                        }
            list_info.append(new_dict)
        else:  # 同一个日期
            list_info[-1]['arr']['link'].append(filename)
            list_info[-1]['arr']['text'].append(info)
            list_info[-1]['arr']['type'].append('image')
    list_info.reverse()  # 翻转
    final_dict = {"list": list_info}
    with open("./source/photos/ins.json", "w") as fp:
        json.dump(final_dict, fp)


def cut_photo():
    """裁剪算法

    ----------
    调用Graphics类中的裁剪算法，将src_dir目录下的文件进行裁剪（裁剪成正方形）
    """
    if directory_exists(src_dir):
        if not directory_exists(src_dir):
            make_directory(src_dir)
        # business logic
        file_list = list_img_file(src_dir)
        # print file_list
        if file_list:
            print_help()
            for infile in file_list:
                img = Image.open(src_dir + infile)
                Graphics(infile=src_dir + infile, outfile=src_dir + infile).cut_by_ratio()
        else:
            pass
    else:
        print("source directory not exist!")


def upload_qiniu():
    '''
    将生成的图片上传至七牛云
    '''
    global upload_list
    q = Auth('igvAaq6U-L4v7OZJY70uUqt9NNXTiERxClo-OsEi', 'Qvj4G2xiEH8JBYjS3wTW0Ex97ga_AS9l1NwBxByn')
    bucket_name = 'huzb'
    for file_name in upload_list:
        # 上传原图
        key = '/src_photos/' + file_name
        token = q.upload_token(bucket_name, key, 3600)
        localfile = src_dir + file_name
        put_file(token, key, localfile)
        # 上传缩略图
        key = '/min_photos/' + file_name
        token = q.upload_token(bucket_name, key, 3600)
        localfile = des_dir + file_name
        put_file(token, key, localfile)


if __name__ == "__main__":
    # metadata = pyexiv2.ImageMetadata("source/photos/img/headicon.jpg")
    # metadata.read()
    # print('Exif.Image.DateTime:'+metadata['Exif.Image.DateTime'].value.strftime('%A %d %B %Y, %H:%M:%S'))
    # print('Exif.Image.ImageDescription:'+metadata['Exif.Image.ImageDescription'].value)
    # print('Exif.Image.Software:'+metadata['Exif.Image.Software'].value)
    # print('Exif.Image.ExifTag'+metadata['Exif.Image.ExifTag'].value)
    # img = Image.open("source/photos/img/headicon.jpg")
    # print(img.info)
    cut_photo()  # 裁剪图片，裁剪成正方形，去中间部分
    compress_photo()  # 压缩图片，并保存到mini_photos文件夹下
    upload_qiniu()  # 提交到七牛云仓库
    handle_photo()  # 将文件处理成json格式，存到博客仓库中
